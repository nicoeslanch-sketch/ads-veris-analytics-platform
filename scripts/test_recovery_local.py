"""Destructive recovery drill exclusively on fresh, disposable loopback data."""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from uuid import uuid4
from urllib.parse import urlsplit

import httpx

from recovery_backup import check_database_client, database_env, sql_json
from recovery_restore_local import require_local, restore


def run(status, checks):
    require_local(status['DB_URL'])
    require_local(status['API_URL'])
    env = database_env(status['DB_URL'])
    check_database_client(env)
    assert sql_json('select to_json(count(*)) from auth.users;', env) == 0, 'Refusing populated lab'
    base = status['API_URL'].rstrip('/')
    key = status['SERVICE_ROLE_KEY']
    headers = {'apikey': key, 'Authorization': 'Bearer ' + key}
    uid, dataset = str(uuid4()), str(uuid4())
    email, password = uid + '@example.invalid', str(uuid4()) + 'aA1!'
    contents = b'ID,Fecha,Venta\nA,2026-01-01,669700\nB,2026-01-02,330300\n'
    object_path = uid + '/synthetic.csv'
    with httpx.Client(timeout=30, trust_env=False) as http, tempfile.TemporaryDirectory(prefix='ads-recovery-lab-') as folder:
        folder = Path(folder)
        account = http.post(base + '/auth/v1/admin/users', headers=headers,
                            json={'id': uid, 'email': email, 'password': password, 'email_confirm': True})
        assert account.status_code in (200, 201), ('synthetic account', account.status_code)
        uid = account.json()['id']
        object_path = uid + '/synthetic.csv'
        uploaded = http.post(base + '/storage/v1/object/datasets/' + object_path,
                             headers={**headers, 'Content-Type': 'text/csv'}, content=contents)
        assert uploaded.status_code in (200, 201), ('synthetic upload', uploaded.status_code)
        sql_json(f"update storage.objects set owner='{uid}',owner_id='{uid}' "
                 f"where bucket_id='datasets' and name='{object_path}'; select 'true'::json;", env)
        original_ownership = sql_json("select json_build_object('id',id,'owner',owner,'owner_id',owner_id) "
                                      f"from storage.objects where bucket_id='datasets' and name='{object_path}';", env)
        sql_json(f"insert into public.datasets(id,user_id,name,storage_path) values('{dataset}','{uid}',"
                 f"'Synthetic recovery','{object_path}'); select 'true'::json;", env)
        expected = sql_json(f"select row_to_json(d) from public.datasets d where id='{dataset}';", env)
        password_file = folder / 'restic-password'
        password_file.write_text(str(uuid4()) + str(uuid4()), encoding='utf-8')
        password_file.chmod(0o600)
        backup_env = {**os.environ, 'ADS_BACKUP_DB_URL': status['DB_URL'],
                      'ADS_BACKUP_STORAGE_URL': base, 'ADS_BACKUP_SERVICE_KEY': key,
                      'RESTIC_REPOSITORY': str(folder / 'encrypted'), 'RESTIC_PASSWORD_FILE': str(password_file)}
        def command(args, **kwargs):
            result = subprocess.run(args, env=backup_env, capture_output=True, timeout=300, **kwargs)
            codes = re.findall(rb'RECOVERY_ERROR:([A-Z_]+)', result.stderr)
            assert result.returncode == 0, ('recovery command failed', args[0], result.returncode, codes)
            return result.stdout
        command(['restic', 'init', '--quiet'])
        started = time.monotonic()
        command([sys.executable, str(Path(__file__).with_name('recovery_backup.py')), 'backup'])
        checks['encrypted_backup_seconds'] = round(time.monotonic() - started, 3)
        command(['restic', 'check', '--read-data', '--quiet'])
        checks['encrypted_repository_integrity'] = True
        original_snapshots = json.loads(command(['restic', 'snapshots', '--json']))
        failed = subprocess.run(['restic', 'backup', '--quiet', '--stdin-from-command', '--',
                                 sys.executable, '-c', 'print("partial"); raise SystemExit(1)'],
                                env=backup_env, capture_output=True, timeout=60)
        assert failed.returncode != 0
        assert json.loads(command(['restic', 'snapshots', '--json'])) == original_snapshots
        checks['failed_producer_does_not_publish_snapshot'] = True
        archive = folder / 'ads-recovery.zip'
        with archive.open('wb') as target:
            result = subprocess.run(['restic', 'dump', 'latest', '/ads-recovery.zip'], env=backup_env,
                                    stdout=target, stderr=subprocess.DEVNULL, timeout=300)
        assert result.returncode == 0
        archive.chmod(0o600)
        command([sys.executable, str(Path(__file__).with_name('recovery_backup.py')), 'verify', '--archive', str(archive)])
        # Only the synthetic object/account just created in this disposable lab.
        deleted = http.request('DELETE', base + '/storage/v1/object/datasets', headers=headers, json={'prefixes': [object_path]})
        assert deleted.status_code == 200
        deleted_user = http.delete(base + '/auth/v1/admin/users/' + uid, headers=headers)
        assert deleted_user.status_code == 200
        assert sql_json('select to_json(count(*)) from public.datasets;', env) == 0
        # The disposable image owns provider tables with supabase_admin.
        # No production role is altered or granted additional permissions.
        parsed_db = urlsplit(status['DB_URL'])
        local_admin_url = parsed_db._replace(netloc='supabase_admin:' + (parsed_db.password or '')
                                             + '@' + parsed_db.netloc.rsplit('@', 1)[1]).geturl()
        os.environ.update(ADS_RESTORE_DB_URL=local_admin_url, ADS_RESTORE_STORAGE_URL=base, ADS_RESTORE_SERVICE_KEY=key)
        started = time.monotonic()
        result = restore(archive)
        checks['restore_seconds'] = round(time.monotonic() - started, 3)
        assert result['objects_verified'] == 1
        assert sql_json(f"select row_to_json(d) from public.datasets d where id='{dataset}';", env) == expected
        restored = http.get(base + '/storage/v1/object/datasets/' + object_path, headers=headers)
        assert restored.status_code == 200 and restored.content == contents
        checks['dataset_metadata_and_file_bytes_restored'] = True
        restored_ownership = sql_json("select json_build_object('id',id,'owner',owner,'owner_id',owner_id) "
                                      f"from storage.objects where bucket_id='datasets' and name='{object_path}';", env)
        assert restored_ownership == original_ownership
        checks['storage_ownership_preserved'] = True
        login = http.post(base + '/auth/v1/token?grant_type=password', headers={'apikey': status['ANON_KEY']},
                          json={'email': email, 'password': password})
        assert login.status_code == 200, ('restored password login', login.status_code)
        jwt = login.json()['access_token']
        visible = http.get(base + '/rest/v1/datasets?select=id', headers={'apikey': status['ANON_KEY'], 'Authorization': 'Bearer ' + jwt})
        assert visible.status_code == 200 and visible.json() == [{'id': dataset}]
        owned_file = http.get(base + '/storage/v1/object/authenticated/datasets/' + object_path,
                              headers={'apikey': status['ANON_KEY'], 'Authorization': 'Bearer ' + jwt})
        assert owned_file.status_code == 200 and owned_file.content == contents
        anonymous = http.get(base + '/storage/v1/object/authenticated/datasets/' + object_path,
                             headers={'apikey': status['ANON_KEY'], 'Authorization': 'Bearer ' + status['ANON_KEY']})
        assert anonymous.status_code in (400, 401, 403, 404)
        checks['restored_private_file_owner_only'] = True
        checks['restored_password_login_and_owner_access'] = True
        assert sql_json("select to_json(not has_function_privilege('authenticated','public.analysis_queue(text,uuid,text,jsonb,uuid)','execute'));", env)
        checks['private_queue_remains_inaccessible'] = True
        try:
            restore(archive)
            raise AssertionError('Populated destination accepted')
        except ValueError:
            checks['populated_destination_rejected'] = True
        checks['csv_sha256'] = hashlib.sha256(contents).hexdigest()
    return checks


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--status-file', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'scope': 'disposable Supabase, same provider base schema and encryption root',
              'production_requests': 0, 'customer_files': 0, 'passed': False, 'checks': {}}
    try:
        run(json.loads(args.status_file.read_text(encoding='utf-8-sig')), report['checks'])
        report['passed'] = True
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))
