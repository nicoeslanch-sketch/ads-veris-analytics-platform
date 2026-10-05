import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import zipfile

import pytest

spec = importlib.util.spec_from_file_location('recovery_backup', Path(__file__).resolve().parents[2] / 'scripts/recovery_backup.py')
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


def archive(path, tamper=False, unsafe=False):
    data = b'synthetic database'
    name = '../outside' if unsafe else 'database.dump'
    manifest = {'format': 1, 'objects': [], 'members': {
        name: {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}}}
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr(name, data + b'bad' if tamper else data)
        z.writestr('manifest.json', json.dumps(manifest))


def test_recovery_checks_every_member(tmp_path):
    path = tmp_path / 'backup.zip'
    archive(path)
    assert backup.verify_archive(path)['format'] == 1
    archive(path, tamper=True)
    with pytest.raises(ValueError, match='checksum'):
        backup.verify_archive(path)
    archive(path, unsafe=True)
    with pytest.raises(ValueError):
        backup.verify_archive(path)


def test_storage_paths_cannot_control_archive_names():
    name = backup.object_member('datasets', '../../private')
    assert name.startswith('objects/') and '..' not in name
    assert name != backup.object_member('other', '../../private')


def test_backup_connections_protect_secrets_and_tls():
    env = backup.database_env('postgresql://operator:secret@db.example.invalid/postgres')
    assert env['PGSSLMODE'] == 'verify-full'
    assert env['PGPASSWORD'] == 'secret'
    with pytest.raises(ValueError):
        backup.storage_base('http://remote.invalid')
    with pytest.raises(ValueError):
        backup.storage_base('https://user:secret@remote.invalid')
    with pytest.raises(ValueError):
        backup.database_env('postgresql://operator:secret@db.invalid/postgres?sslmode=disable')


def test_streaming_digest_preserves_data():
    out = io.BytesIO()
    result = backup.copy_hashed([b'a', b'b'], out)
    assert out.getvalue() == b'ab'
    assert result == {'bytes': 2, 'sha256': hashlib.sha256(b'ab').hexdigest()}


def test_erasure_ledger_requires_an_independent_repository(monkeypatch):
    monkeypatch.setenv('RESTIC_REPOSITORY', 's3:https://backup.invalid/company')
    monkeypatch.setenv('ADS_ERASURE_LEDGER_REPOSITORY', 's3:https://backup.invalid/company/')
    monkeypatch.setenv('ADS_ERASURE_LEDGER_PASSWORD_FILE', '/secret/ledger')
    with pytest.raises(backup.RecoveryError, match='NOT_INDEPENDENT'):
        backup.erasure_ledger_restic_env()


def test_erasure_ledger_requires_an_independent_key(monkeypatch):
    monkeypatch.setenv('RESTIC_REPOSITORY', 's3:https://backup.invalid/data')
    monkeypatch.setenv('ADS_ERASURE_LEDGER_REPOSITORY', 's3:https://archive.invalid/ledger')
    monkeypatch.setenv('RESTIC_PASSWORD_FILE', '/secret/shared')
    monkeypatch.setenv('ADS_ERASURE_LEDGER_PASSWORD_FILE', '/secret/shared')
    with pytest.raises(backup.RecoveryError, match='KEY_NOT_INDEPENDENT'):
        backup.erasure_ledger_restic_env()


@pytest.fixture
def independent_credentials(monkeypatch, tmp_path):
    for name, value in [('data-key', 'synthetic-data-key'), ('ledger-key', 'synthetic-ledger-key')]:
        (tmp_path / name).write_text(value, encoding='utf-8')
    monkeypatch.setenv('RESTIC_REPOSITORY', 's3:https://backup.invalid/data')
    monkeypatch.setenv('RESTIC_PASSWORD_FILE', str(tmp_path / 'data-key'))
    monkeypatch.setenv('ADS_ERASURE_LEDGER_REPOSITORY', 's3:https://archive.invalid/ledger')
    monkeypatch.setenv('ADS_ERASURE_LEDGER_PASSWORD_FILE', str(tmp_path / 'ledger-key'))
    return tmp_path


def test_erasure_ledger_uses_separate_restic_credentials(independent_credentials):
    env = backup.erasure_ledger_restic_env()
    assert env['RESTIC_REPOSITORY'] == 's3:https://archive.invalid/ledger'
    assert env['RESTIC_PASSWORD_FILE'] == str(independent_credentials / 'ledger-key')


def test_equal_passwords_in_different_files_are_not_independent(independent_credentials):
    (independent_credentials / 'ledger-key').write_text('synthetic-data-key\n', encoding='utf-8')
    with pytest.raises(backup.RecoveryError, match='KEY_NOT_INDEPENDENT'):
        backup.erasure_ledger_restic_env()


@pytest.mark.parametrize('value', [b'', b' \n', b'x' * 4097, b'one\ntwo', b'\0'])
def test_invalid_password_files_are_rejected(independent_credentials, value):
    (independent_credentials / 'ledger-key').write_bytes(value)
    with pytest.raises(backup.RecoveryError, match='KEY_FILE_INVALID'):
        backup.erasure_ledger_restic_env()


def test_unreadable_key_has_no_path_in_error(independent_credentials):
    (independent_credentials / 'ledger-key').unlink()
    with pytest.raises(backup.RecoveryError, match='^BACKUP_KEY_FILE_UNREADABLE$'):
        backup.erasure_ledger_restic_env()


def test_restic_overrides_are_removed_from_both_environments(independent_credentials, monkeypatch):
    overrides = ('RESTIC_PASSWORD', 'RESTIC_PASSWORD_COMMAND', 'RESTIC_REPOSITORY_FILE', 'RESTIC_KEY_HINT')
    for name in overrides:
        monkeypatch.setenv(name, 'unexpected-override')
    for env in (backup.data_restic_env(), backup.erasure_ledger_restic_env()):
        assert not set(overrides).intersection(env)


def test_repository_aliases_are_rejected_before_backup(independent_credentials, monkeypatch):
    monkeypatch.setattr(backup, 'restic_repository_id', lambda env: 'a' * 64)
    with pytest.raises(backup.RecoveryError, match='REPOSITORY_NOT_INDEPENDENT'):
        backup.independent_restic_environments()


def test_distinct_repository_identities_are_accepted(independent_credentials, monkeypatch):
    ids = iter(['a' * 64, 'b' * 64])
    monkeypatch.setattr(backup, 'restic_repository_id', lambda env: next(ids))
    data_env, ledger_env = backup.independent_restic_environments()
    assert data_env['RESTIC_REPOSITORY'] != ledger_env['RESTIC_REPOSITORY']


@pytest.mark.parametrize('output', [b'{}', b'[]', b'invalid', b'{"id":"short"}', b'{"id":null}'])
def test_repository_id_must_be_valid_json_identity(monkeypatch, output):
    monkeypatch.setattr(backup, 'run_restic', lambda *args: output)
    with pytest.raises(backup.RecoveryError, match='^RESTIC_REPOSITORY_CONFIG_INVALID$'):
        backup.restic_repository_id({})


@pytest.mark.parametrize('failure', ['status', 'timeout', 'missing'])
def test_restic_failure_does_not_print_provider_secrets(monkeypatch, capsys, failure):
    def fail(command, **kwargs):
        assert kwargs['capture_output'] is True
        if failure == 'timeout':
            raise subprocess.TimeoutExpired(command, 1, output=b'sensitive', stderr=b'provider-secret')
        if failure == 'missing':
            raise OSError('private-path')
        return SimpleNamespace(returncode=1, stdout=b'sensitive', stderr=b'provider-secret')
    monkeypatch.setattr(backup.subprocess, 'run', fail)
    with pytest.raises(backup.RecoveryError, match='^SAFE_FAILURE$'):
        backup.run_restic(['cat', 'config'], {}, 1, 'SAFE_FAILURE')
    captured = capsys.readouterr()
    assert not captured.out and not captured.err


def test_backup_all_checks_independence_before_writing(monkeypatch):
    monkeypatch.setattr(backup.sys, 'argv', ['recovery_backup.py', 'backup-all'])
    monkeypatch.setattr(backup, 'readiness', lambda: {'tools': {'all': True}, 'configured': {'all': True},
                                                     'erasure_ledger_configured': {'all': True}})
    monkeypatch.setattr(backup, 'data_restic_env', lambda: {})
    def fail():
        raise backup.RecoveryError('ERASURE_LEDGER_REPOSITORY_NOT_INDEPENDENT')
    monkeypatch.setattr(backup, 'independent_restic_environments', fail)
    monkeypatch.setattr(backup, 'encrypted_data_backup', lambda env: pytest.fail('Data backup started before validation'))
    with pytest.raises(backup.RecoveryError, match='NOT_INDEPENDENT'):
        backup.main()


def test_backup_all_ledger_failure_never_reports_success(monkeypatch, capsys):
    monkeypatch.setattr(backup.sys, 'argv', ['recovery_backup.py', 'backup-all'])
    monkeypatch.setattr(backup, 'readiness', lambda: {'tools': {'all': True}, 'configured': {'all': True},
                                                     'erasure_ledger_configured': {'all': True}})
    monkeypatch.setattr(backup, 'data_restic_env', lambda: {})
    monkeypatch.setattr(backup, 'independent_restic_environments', lambda: ({'data': True}, {'ledger': True}))
    events = []
    monkeypatch.setattr(backup, 'encrypted_data_backup', lambda env: events.append('data'))
    def fail(env):
        events.append('ledger')
        raise backup.RecoveryError('ENCRYPTED_ERASURE_LEDGER_BACKUP_FAILED')
    monkeypatch.setattr(backup, 'encrypted_erasure_ledger_backup', fail)
    with pytest.raises(backup.RecoveryError, match='LEDGER_BACKUP_FAILED'):
        backup.main()
    assert events == ['data', 'ledger']
    assert not capsys.readouterr().out


def test_ledger_only_does_not_require_or_run_data_export(monkeypatch, capsys):
    monkeypatch.setattr(backup.sys, 'argv', ['recovery_backup.py', 'backup-ledger'])
    monkeypatch.setenv('ADS_BACKUP_DB_URL', 'postgresql://synthetic@localhost/test')
    monkeypatch.delenv('ADS_BACKUP_STORAGE_URL', raising=False)
    monkeypatch.delenv('ADS_BACKUP_SERVICE_KEY', raising=False)
    monkeypatch.setattr(backup.shutil, 'which', lambda tool: tool)
    monkeypatch.setattr(backup, 'independent_restic_environments', lambda: ({}, {'ledger': True}))
    monkeypatch.setattr(backup, 'encrypted_data_backup', lambda env: pytest.fail('Unnecessary data export'))
    events = []
    monkeypatch.setattr(backup, 'encrypted_erasure_ledger_backup', lambda env: events.append(env))
    backup.main()
    assert events == [{'ledger': True}]
    assert json.loads(capsys.readouterr().out) == {
        'backup_completed': False, 'erasure_ledger_completed': True, 'restore_verified': False}
