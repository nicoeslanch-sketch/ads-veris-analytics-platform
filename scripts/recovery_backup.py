"""Stream PostgreSQL and Storage into restic encryption; never persist plaintext.

Operator dependencies: PostgreSQL client tools, restic >= 0.17, httpx.
Credentials are environment-only. This command cannot restore production.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from urllib.parse import quote, unquote, urlsplit
import zipfile

import httpx

SCHEMAS = ('public', 'app_private', 'auth', 'storage')
# Provider migration history belongs to the matching empty target, not its data.
EXCLUDED_DATA = ('auth.schema_migrations', 'storage.migrations')
CHUNK = 1024 * 1024
MAX_OBJECTS = 100_000
MAX_TOTAL_BYTES = 50 * 1024**3
INVENTORY_SQL = """select coalesce(json_agg(t order by bucket_id,name),'[]') from
 (select id,bucket_id,name,updated_at,metadata,owner_id from storage.objects) t;"""


class RecoveryError(RuntimeError):
    """A fixed diagnostic code, never provider output or customer data."""


def check_database_client(env):
    server = int(sql_json("select to_json(current_setting('server_version_num')::int);", env)) // 10000
    result = subprocess.run(['pg_dump', '--version'], capture_output=True, timeout=15)
    match = re.search(rb'PostgreSQL\) (\d+)', result.stdout)
    if result.returncode or not match or int(match[1]) < server:
        raise RecoveryError('POSTGRES_CLIENT_TOO_OLD')


def database_env(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ('postgres', 'postgresql') or not parsed.hostname or not parsed.username:
        raise ValueError('Invalid PostgreSQL connection configuration')
    if parsed.query or parsed.fragment:
        raise ValueError('Configure TLS through PGSSL* environment variables, not URL query parameters')
    local = parsed.hostname in ('127.0.0.1', '::1', 'localhost')
    return {**os.environ, 'PGHOST': parsed.hostname, 'PGPORT': str(parsed.port or 5432),
            'PGUSER': unquote(parsed.username), 'PGPASSWORD': unquote(parsed.password or ''),
            'PGDATABASE': unquote(parsed.path.lstrip('/')), 'PGCONNECT_TIMEOUT': '15',
            'PGSSLMODE': 'disable' if local else 'verify-full'}


def sql_json(query, env):
    result = subprocess.run(['psql', '-X', '-q', '-A', '-t', '-v', 'ON_ERROR_STOP=1', '-v', 'VERBOSITY=sqlstate', '-c', query],
                            env=env, capture_output=True, timeout=90)
    if result.returncode:
        state = re.search(rb'(?:ERROR|FATAL):\s+([A-Z0-9]{5})\b', result.stderr)
        raise RecoveryError('DATABASE_QUERY_' + (state[1].decode('ascii') if state else 'FAILED'))
    return json.loads(result.stdout)


def storage_base(value):
    parsed = urlsplit(value)
    local = parsed.hostname in ('127.0.0.1', '::1', 'localhost')
    if (parsed.scheme != 'https' and not (local and parsed.scheme == 'http')) or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Storage requires HTTPS or an isolated loopback target')
    if parsed.path not in ('', '/'):
        raise ValueError('Use the project API origin without a path')
    return value.rstrip('/')


def object_member(bucket, name):
    return 'objects/' + hashlib.sha256(json.dumps([bucket, name], ensure_ascii=True).encode()).hexdigest()


def copy_hashed(chunks, target):
    digest, size = hashlib.sha256(), 0
    for chunk in chunks:
        size += len(chunk)
        if size > MAX_TOTAL_BYTES:
            raise ValueError('Backup stream exceeds the safety limit')
        digest.update(chunk)
        target.write(chunk)
    return {'sha256': digest.hexdigest(), 'bytes': size}


def stream_backup(output):
    env = database_env(os.environ['ADS_BACKUP_DB_URL'])
    check_database_client(env)
    base = storage_base(os.environ['ADS_BACKUP_STORAGE_URL'])
    key = os.environ['ADS_BACKUP_SERVICE_KEY']
    headers = {'apikey': key, 'Authorization': 'Bearer ' + key}
    before = sql_json(INVENTORY_SQL, env)
    if len(before) > MAX_OBJECTS:
        raise ValueError('Too many objects for this backup profile')
    if sum(int((row.get('metadata') or {}).get('size') or 0) for row in before) > MAX_TOTAL_BYTES:
        raise ValueError('Storage exceeds the backup safety limit')
    manifest = {'format': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
                'schemas': SCHEMAS, 'objects': [], 'members': {},
                'migration_versions': sql_json("select coalesce(json_agg(version order by version),'[]') from supabase_migrations.schema_migrations;", env),
                'limitations': ['Provider settings, passwords for database roles and provider encryption root keys require a separate recovery runbook.']}
    # ZIP is only a streaming container. Restic provides authenticated encryption.
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        command = ['pg_dump', '--format=custom', '--no-owner', '--compress=0']
        for schema in SCHEMAS:
            command += ['--schema', schema]
        for table in EXCLUDED_DATA:
            command += ['--exclude-table-data', table]
        with subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as dump:
            try:
                with archive.open('database.dump', 'w', force_zip64=True) as target:
                    manifest['members']['database.dump'] = copy_hashed(iter(lambda: dump.stdout.read(CHUNK), b''), target)
                if dump.wait(timeout=1800) != 0:
                    raise RecoveryError('POSTGRES_DUMP_FAILED')
            finally:
                if dump.poll() is None:
                    dump.kill()
                    dump.wait()
        total = 0
        with httpx.Client(timeout=120, trust_env=False, follow_redirects=False) as client:
            for row in before:
                bucket, name = row['bucket_id'], row['name']
                member = object_member(bucket, name)
                url = base + '/storage/v1/object/' + quote(bucket, safe='') + '/' + quote(name, safe='/')
                with client.stream('GET', url, headers=headers) as response:
                    if response.status_code != 200:
                        raise RecoveryError('STORAGE_DOWNLOAD_FAILED')
                    with archive.open(member, 'w', force_zip64=True) as target:
                        info = copy_hashed(response.iter_bytes(CHUNK), target)
                total += info['bytes']
                if total > MAX_TOTAL_BYTES or info['bytes'] != int((row.get('metadata') or {}).get('size', -1)):
                    raise RecoveryError('STORAGE_SIZE_MISMATCH')
                manifest['members'][member] = info
                manifest['objects'].append({**row, 'member': member})
        if before != sql_json(INVENTORY_SQL, env):
            raise RecoveryError('STORAGE_CHANGED_DURING_BACKUP')
        archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=True))


def verify_archive(path):
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > MAX_OBJECTS + 2 or sum(item.file_size for item in members) > 2 * MAX_TOTAL_BYTES:
            raise ValueError('Archive exceeds recovery safety limits')
        if len(members) != len({item.filename for item in members}):
            raise ValueError('Duplicate archive member')
        manifest_entry = archive.getinfo('manifest.json')
        if manifest_entry.file_size > 64 * 1024**2:
            raise ValueError('Manifest too large')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('format') != 1 or set(archive.namelist()) != {'manifest.json', *manifest['members']}:
            raise ValueError('Incomplete recovery archive')
        if 'database.dump' not in manifest['members']:
            raise ValueError('Missing database dump')
        for name, expected in manifest['members'].items():
            if name != 'database.dump' and not re.fullmatch(r'objects/[0-9a-f]{64}', name):
                raise ValueError('Unsafe archive member')
            digest, size = hashlib.sha256(), 0
            with archive.open(name) as stream:
                for block in iter(lambda: stream.read(CHUNK), b''):
                    digest.update(block)
                    size += len(block)
                    if size > MAX_TOTAL_BYTES:
                        raise ValueError('Member too large')
            if expected != {'sha256': digest.hexdigest(), 'bytes': size}:
                raise ValueError('Recovery checksum mismatch')
        for row in manifest['objects']:
            if row['member'] != object_member(row['bucket_id'], row['name']) or row['member'] not in manifest['members']:
                raise ValueError('Object identity mismatch')
        return manifest


def readiness():
    return {'tools': {name: bool(shutil.which(name)) for name in ('psql', 'pg_dump', 'pg_restore', 'restic')},
            'configured': {name: bool(os.environ.get(name)) for name in
                          ('ADS_BACKUP_DB_URL', 'ADS_BACKUP_STORAGE_URL', 'ADS_BACKUP_SERVICE_KEY',
                           'RESTIC_REPOSITORY', 'RESTIC_PASSWORD_FILE')}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'backup', 'stream', 'verify'])
    parser.add_argument('--archive', type=Path)
    args = parser.parse_args()
    if args.action == 'check':
        print(json.dumps(readiness()))
    elif args.action == 'stream':
        stream_backup(sys.stdout.buffer)
    elif args.action == 'verify':
        if not args.archive:
            raise ValueError('An archive path is required')
        manifest = verify_archive(args.archive)
        print(json.dumps({'verified': True, 'objects': len(manifest['objects']), 'members': len(manifest['members'])}))
    else:
        state = readiness()
        if not all(state['tools'].values()) or not all(state['configured'].values()):
            raise RecoveryError('MISSING_BACKUP_CONFIGURATION')
        # A failed producer must never publish a seemingly successful snapshot.
        result = subprocess.run(['restic', 'backup', '--quiet', '--tag', 'ads-recovery-v1',
                                 '--stdin-filename', 'ads-recovery.zip', '--stdin-from-command', '--',
                                 sys.executable, str(Path(__file__).resolve()), 'stream'], timeout=7200)
        if result.returncode:
            raise RecoveryError('ENCRYPTED_BACKUP_FAILED')
        print(json.dumps({'backup_completed': True, 'restore_verified': False}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Do not emit provider URLs, object paths, credentials, or database diagnostics.
        code = str(exc) if isinstance(exc, RecoveryError) else 'BACKUP_OPERATION_FAILED'
        print('RECOVERY_ERROR:' + code, file=sys.stderr)
        raise SystemExit(1)
