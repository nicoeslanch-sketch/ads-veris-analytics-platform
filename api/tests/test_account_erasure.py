import httpx
import pytest
from fastapi import HTTPException

from app import account_erasure
from app.config import Settings


def _settings():
    return Settings(
        _env_file=None,
        supabase_url='https://project.supabase.co',
        supabase_service_role_key='service-role-test-key',
    )


def test_erasure_orders_block_storage_cache_auth_and_receipt(monkeypatch):
    events = []
    states = {
        'prepare': {'id': 'job', 'target_user_id': 'target', 'status': 'deleting_storage'},
        'storage_deleted': {'id': 'job', 'target_user_id': 'target', 'status': 'deleting_account'},
        'complete': {'id': 'job', 'status': 'completed', 'storage_objects_deleted': 3},
    }
    monkeypatch.setattr(account_erasure, '_control',
                        lambda _admin, _request, action, _settings, payload=None: events.append(action) or states[action])
    monkeypatch.setattr(account_erasure, '_ban_account', lambda user, _settings: events.append(('ban', user)))
    monkeypatch.setattr(account_erasure, '_purge_runtime', lambda user, _settings: events.append(('purge', user)))
    monkeypatch.setattr(account_erasure, '_delete_auth_account', lambda user, _settings: events.append(('auth', user)))
    monkeypatch.setattr(account_erasure, 'commercial_rpc',
                        lambda name, payload, _settings: events.append((name, payload)) or 4)

    result = account_erasure.execute_account_erasure(
        'admin', 'request', _settings(),
        storage_delete=lambda user, _settings: events.append(('storage', user)) or 3,
    )
    assert result == {'status': 'completed', 'idempotent': False, 'receipt': 'job',
                      'storage_objects_deleted': 3, 'legacy_rows_deleted': 4}
    assert events == [
        'prepare', ('ban', 'target'), ('storage', 'target'), 'storage_deleted',
        ('purge', 'target'), ('purge_legacy_account_snapshot', {'p_user_id': 'target'}),
        ('auth', 'target'), 'complete',
    ]


def test_storage_failure_never_deletes_auth_or_claims_success(monkeypatch):
    events = []
    monkeypatch.setattr(account_erasure, '_control', lambda _a, _r, action, _s, payload=None:
                        events.append((action, payload)) or {
                            'id': 'job', 'target_user_id': 'target', 'status': 'deleting_storage',
                        })
    monkeypatch.setattr(account_erasure, '_ban_account', lambda *_args: events.append(('ban', None)))
    monkeypatch.setattr(account_erasure, '_delete_auth_account', lambda *_args: pytest.fail('Auth must not be deleted'))
    with pytest.raises(HTTPException) as failure:
        account_erasure.execute_account_erasure(
            'admin', 'request', _settings(),
            storage_delete=lambda *_args: (_ for _ in ()).throw(httpx.ConnectError('offline')),
        )
    assert failure.value.status_code == 502
    assert any(action == 'fail' for action, _payload in events if isinstance(action, str))


def test_completed_erasure_is_idempotent(monkeypatch):
    monkeypatch.setattr(account_erasure, '_control', lambda *_args, **_kwargs:
                        {'id': 'receipt', 'target_user_id': None, 'status': 'completed'})
    assert account_erasure.execute_account_erasure('admin', 'request', _settings()) == {
        'status': 'completed', 'idempotent': True, 'receipt': 'receipt',
    }
