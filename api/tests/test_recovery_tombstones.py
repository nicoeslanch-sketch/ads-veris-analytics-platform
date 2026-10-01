import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(SCRIPTS))

from recovery_backup import LEDGER_FORMAT  # noqa: E402
from recovery_restore_local import _object_subject_digest, verify_erasure_ledger  # noqa: E402


USER_ID = '00000000-0000-0000-0000-000000000001'
DIGEST = hashlib.sha256(USER_ID.encode()).hexdigest()


def _write_ledger(path, generated_at, tombstones=None):
    path.write_text(json.dumps({
        'format': LEDGER_FORMAT,
        'generated_at': generated_at.isoformat(),
        'tombstones': tombstones if tombstones is not None else [
            {'subject_digest': DIGEST, 'erased_at': generated_at.isoformat()},
        ],
    }), encoding='utf-8')


def test_restore_requires_ledger_newer_than_backup(tmp_path):
    backup_time = datetime.now(timezone.utc)
    ledger = tmp_path / 'ledger.json'
    _write_ledger(ledger, backup_time - timedelta(seconds=1))
    with pytest.raises(ValueError, match='predates'):
        verify_erasure_ledger(ledger, backup_time.isoformat())
    _write_ledger(ledger, backup_time + timedelta(seconds=1))
    assert verify_erasure_ledger(ledger, backup_time.isoformat())['tombstones'][0]['subject_digest'] == DIGEST


@pytest.mark.parametrize('mutation', [
    lambda data: data.update(format='wrong'),
    lambda data: data['tombstones'][0].update(subject_digest='not-a-digest'),
    lambda data: data['tombstones'].append(dict(data['tombstones'][0])),
    lambda data: data.update(extra='not allowed'),
])
def test_restore_rejects_malformed_or_duplicate_ledger(tmp_path, mutation):
    now = datetime.now(timezone.utc)
    ledger = tmp_path / 'ledger.json'
    _write_ledger(ledger, now)
    data = json.loads(ledger.read_text(encoding='utf-8'))
    mutation(data)
    ledger.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError):
        verify_erasure_ledger(ledger, (now - timedelta(seconds=1)).isoformat())


def test_storage_subject_matching_uses_uuid_not_arbitrary_prefix():
    assert _object_subject_digest({'bucket_id': 'datasets', 'name': USER_ID + '/file.csv'}) == DIGEST
    assert _object_subject_digest({'bucket_id': 'other', 'name': USER_ID + '/file.csv', 'owner_id': USER_ID}) == DIGEST
    assert _object_subject_digest({'bucket_id': 'datasets', 'name': '../foreign/file.csv'}) is None
