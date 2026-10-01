import hashlib
import importlib.util
import io
import json
from pathlib import Path
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


def test_erasure_ledger_uses_separate_restic_credentials(monkeypatch):
    monkeypatch.setenv('RESTIC_REPOSITORY', 's3:https://backup.invalid/data')
    monkeypatch.setenv('RESTIC_PASSWORD_FILE', '/secret/data')
    monkeypatch.setenv('ADS_ERASURE_LEDGER_REPOSITORY', 's3:https://archive.invalid/ledger')
    monkeypatch.setenv('ADS_ERASURE_LEDGER_PASSWORD_FILE', '/secret/ledger')
    env = backup.erasure_ledger_restic_env()
    assert env['RESTIC_REPOSITORY'] == 's3:https://archive.invalid/ledger'
    assert env['RESTIC_PASSWORD_FILE'] == '/secret/ledger'
