"""Restore a verified archive into EMPTY loopback Supabase only.

The destination must already run the matching Supabase schema and repository
migrations. Production restore intentionally has no automatic command here.
"""

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import quote, urlsplit
import zipfile

import httpx

from recovery_backup import (CHUNK, SCHEMAS, EXCLUDED_DATA, LEDGER_FORMAT,
                             RecoveryError, database_env, sql_json, storage_base,
                             verify_archive)


def require_local(value):
    if urlsplit(value).hostname not in {'127.0.0.1', '::1'}:
        raise ValueError('Only literal loopback recovery targets are allowed')


def _timestamp(value):
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Ledger timestamps require a timezone')
    return parsed


def verify_erasure_ledger(path, backup_created_at):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 64 * 1024**2:
        raise ValueError('Invalid erasure ledger')
    payload = json.loads(path.read_text(encoding='utf-8'))
    if set(payload) != {'format', 'generated_at', 'tombstones'} or payload['format'] != LEDGER_FORMAT:
        raise ValueError('Invalid erasure ledger format')
    if _timestamp(payload['generated_at']) < _timestamp(backup_created_at):
        raise ValueError('Erasure ledger predates the selected backup')
    seen = set()
    for row in payload['tombstones']:
        if set(row) != {'subject_digest', 'erased_at'}:
            raise ValueError('Invalid erasure ledger entry')
        digest = row['subject_digest']
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('Invalid erasure digest')
        _timestamp(row['erased_at'])
        if digest in seen:
            raise ValueError('Duplicate erasure digest')
        seen.add(digest)
    return payload


def _object_subject_digest(row):
    candidates = [row.get('owner_id'), row.get('owner')]
    if row.get('bucket_id') == 'datasets':
        candidates.append(str(row.get('name') or '').split('/', 1)[0])
    for candidate in candidates:
        try:
            from uuid import UUID
            canonical = str(UUID(str(candidate)))
        except (TypeError, ValueError):
            continue
        return hashlib.sha256(canonical.encode()).hexdigest()
    return None


def _restore_stage(name, query, env):
    """Expose only a fixed recovery stage when an isolated purge fails."""
    try:
        return sql_json(query, env)
    except RecoveryError as exc:
        code = str(exc).removeprefix('DATABASE_QUERY_')
        raise RecoveryError(f'ERASURE_PURGE_{name}_{code}') from None


def restore(path, erasure_ledger_path):
    db = os.environ['ADS_RESTORE_DB_URL']
    base = storage_base(os.environ['ADS_RESTORE_STORAGE_URL'])
    require_local(db)
    require_local(base)
    env = database_env(db)
    if not sql_json("select to_json(rolsuper) from pg_roles where rolname=current_user;", env):
        raise ValueError('The isolated restore requires its local database administrator, not a hosted application role')
    manifest = verify_archive(path)
    ledger = verify_erasure_ledger(erasure_ledger_path, manifest['created_at'])
    tombstone_digests = {row['subject_digest'] for row in ledger['tombstones']}
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
        env.pop('PGOPTIONS', None)
        encoded = json.dumps(ledger['tombstones']).encode('utf-8').hex()
        ledger_rows = ("jsonb_to_recordset(convert_from(decode('" + encoded
                       + "','hex'),'UTF8')::jsonb) as x(subject_digest text,erased_at timestamptz)")
        erased_accounts = ("select u.id from auth.users u join " + ledger_rows
                           + " on encode(extensions.digest(u.id::text,'sha256'),'hex')=x.subject_digest")
        _restore_stage('LEDGER',
            "begin; "
            "insert into app_private.erasure_tombstones(subject_digest,erased_at,receipt_id) "
            "select x.subject_digest,x.erased_at,gen_random_uuid() from " + ledger_rows + " "
            "on conflict(subject_digest) do update set erased_at=greatest(app_private.erasure_tombstones.erased_at,excluded.erased_at); "
            "commit; select 'true'::json;", env)
        _restore_stage('AUDIT',
            "begin; update public.admin_audit set target_user_id=null where target_user_id in("
            + erased_accounts + "); commit; select 'true'::json;", env)
        key = os.environ['ADS_RESTORE_SERVICE_KEY']
        headers = {'apikey': key, 'Authorization': 'Bearer ' + key, 'x-upsert': 'true'}
        suppressed_objects = [row for row in manifest['objects']
                              if _object_subject_digest(row) in tombstone_digests]
        # Provider-owned storage tables reject direct SQL deletion. The local
        # Storage service is the supported authority for removing its metadata.
        by_bucket = {}
        for row in suppressed_objects:
            by_bucket.setdefault(row['bucket_id'], []).append(row['name'])
        with httpx.Client(timeout=120, trust_env=False, follow_redirects=False) as client:
            for bucket, names in by_bucket.items():
                for offset in range(0, len(names), 100):
                    response = client.request(
                        'DELETE', base + '/storage/v1/object/' + quote(bucket, safe=''),
                        headers=headers, json={'prefixes': names[offset:offset + 100]})
                    if response.status_code != 200:
                        raise RecoveryError('ERASURE_PURGE_STORAGE_API')
        purged = _restore_stage('AUTH',
            "begin; with removed as (delete from auth.users where id in(" + erased_accounts
            + ") returning id) select json_build_object('accounts',count(*)) from removed; commit;", env)
        ownership = sql_json("select coalesce(json_agg(t),'[]') from "
                             "(select id,owner,owner_id from storage.objects) t;", env)
        with httpx.Client(timeout=120, trust_env=False, follow_redirects=False) as client:
            restored_count = 0
            suppressed_count = 0
            for row in manifest['objects']:
                if _object_subject_digest(row) in tombstone_digests:
                    suppressed_count += 1
                    continue
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
                restored_count += 1
        # Storage upserts with service_role can replace ownership. Restore only
        # the original authorization fields, not the new physical object version.
        encoded = json.dumps(ownership).encode('utf-8').hex()
        restored_owners = sql_json(
            "with source as (select * from jsonb_to_recordset(convert_from(decode('" + encoded
            + "','hex'),'UTF8')::jsonb) as x(id uuid,owner uuid,owner_id text)), "
            "restored as (update storage.objects o set owner=s.owner,owner_id=s.owner_id "
            "from source s where o.id=s.id returning o.id) select to_json(count(*)) from restored;", env)
        if restored_owners != len(ownership):
            raise RuntimeError('Restored object ownership mismatch')
    return {'restored': True, 'objects_verified': restored_count,
            'objects_suppressed': suppressed_count, 'accounts_suppressed': purged['accounts'],
            'target': 'isolated-loopback'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--erasure-ledger', required=True, type=Path)
    parser.add_argument('--confirm-empty-local', action='store_true', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(restore(args.archive, args.erasure_ledger)))
    except Exception:
        print('Local recovery failed. Destination may require a fresh isolated stack. No remote restore is permitted.', file=sys.stderr)
        raise SystemExit(1)
