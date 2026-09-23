"""Restore a verified archive into EMPTY loopback Supabase only.

The destination must already run the matching Supabase schema and repository
migrations. Production restore intentionally has no automatic command here.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import quote, urlsplit
import zipfile

import httpx

from recovery_backup import CHUNK, SCHEMAS, EXCLUDED_DATA, database_env, sql_json, storage_base, verify_archive


def require_local(value):
    if urlsplit(value).hostname not in {'127.0.0.1', '::1'}:
        raise ValueError('Only literal loopback recovery targets are allowed')


def restore(path):
    db = os.environ['ADS_RESTORE_DB_URL']
    base = storage_base(os.environ['ADS_RESTORE_STORAGE_URL'])
    require_local(db)
    require_local(base)
    env = database_env(db)
    manifest = verify_archive(path)
    versions = sql_json("select coalesce(json_agg(version order by version),'[]') from supabase_migrations.schema_migrations;", env)
    if versions != manifest.get('migration_versions'):
        raise ValueError('Destination migrations do not match the backup')
    empty = sql_json("select json_build_object('users',(select count(*) from auth.users),"
                     "'datasets',(select count(*) from public.datasets),"
                     "'objects',(select count(*) from storage.objects));", env)
    if any(empty.values()):
        raise ValueError('Destination contains accounts or files; no data was changed')
    schemas = ','.join("'" + name + "'" for name in SCHEMAS)
    excluded = ','.join("'" + name + "'" for name in EXCLUDED_DATA)
    # Matching migrations initialize seed rows. Clear them only on an empty,
    # explicitly selected disposable stack, never on a remote database.
    # DELETE avoids resetting sequences owned by Supabase's internal roles.
    clear = sql_json("select to_json(string_agg(format('delete from %I.%I;',schemaname,tablename),' '))"
                     " from pg_tables where schemaname in (" + schemas + ")"
                     " and schemaname || '.' || tablename not in (" + excluded + ");", env)
    sql_json("begin; set local session_replication_role=replica; " + clear + " commit; select 'true'::json;", env)
    env['PGOPTIONS'] = '-c session_replication_role=replica'
    with zipfile.ZipFile(path) as archive:
        with subprocess.Popen(['pg_restore', '--data-only', '--no-owner',
                               '--exit-on-error', '--single-transaction', '--dbname', env['PGDATABASE']],
                              env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL) as process:
            try:
                with archive.open('database.dump') as source:
                    for block in iter(lambda: source.read(CHUNK), b''):
                        process.stdin.write(block)
                process.stdin.close()
                if process.wait(timeout=1800):
                    raise RuntimeError('Local database restore failed')
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
        key = os.environ['ADS_RESTORE_SERVICE_KEY']
        headers = {'apikey': key, 'Authorization': 'Bearer ' + key, 'x-upsert': 'true'}
        with httpx.Client(timeout=120, trust_env=False, follow_redirects=False) as client:
            for row in manifest['objects']:
                metadata = row.get('metadata') or {}
                url = base + '/storage/v1/object/' + quote(row['bucket_id'], safe='') + '/' + quote(row['name'], safe='/')
                with archive.open(row['member']) as source:
                    response = client.post(url, headers={**headers, 'Content-Type': metadata.get('mimetype', 'application/octet-stream')},
                                           content=iter(lambda: source.read(CHUNK), b''))
                if response.status_code not in (200, 201):
                    raise RuntimeError('Local object restore failed')
                import hashlib
                digest = hashlib.sha256()
                with client.stream('GET', url, headers=headers) as response:
                    if response.status_code != 200:
                        raise RuntimeError('Restored object unreadable')
                    for block in response.iter_bytes(CHUNK):
                        digest.update(block)
                if digest.hexdigest() != manifest['members'][row['member']]['sha256']:
                    raise RuntimeError('Restored object checksum mismatch')
    return {'restored': True, 'objects_verified': len(manifest['objects']), 'target': 'isolated-loopback'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--confirm-empty-local', action='store_true', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(restore(args.archive)))
    except Exception:
        print('Local recovery failed. Destination may require a fresh isolated stack. No remote restore is permitted.', file=sys.stderr)
        raise SystemExit(1)
