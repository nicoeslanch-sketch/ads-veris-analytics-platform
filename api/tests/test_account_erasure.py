import httpx
import pytest
from fastapi import HTTPException

from app import account_erasure
from app.config import Settings

TARGET = '00000000-0000-0000-0000-000000000001'


def _settings():
    return Settings(
        _env_file=None,
        supabase_url='https://project.supabase.co',
        supabase_service_role_key='service-role-test-key',
    )


def test_erasure_orders_block_storage_cache_auth_and_receipt(monkeypatch):
    events = []
    states = {
        'prepare': {'id': 'job', 'target_user_id': TARGET, 'status': 'deleting_storage'},
        'ready': {'ready': True},
        'storage_deleted': {'id': 'job', 'target_user_id': TARGET, 'status': 'deleting_account'},
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
        'prepare', ('ban', TARGET), 'ready', ('storage', TARGET), 'storage_deleted',
        ('purge', TARGET), ('purge_legacy_account_snapshot', {'p_user_id': TARGET}),
        ('auth', TARGET), 'complete',
    ]


def test_storage_failure_never_deletes_auth_or_claims_success(monkeypatch):
    events = []
    monkeypatch.setattr(account_erasure, '_control', lambda _a, _r, action, _s, payload=None:
                        events.append((action, payload)) or {
                            'id': 'job', 'target_user_id': TARGET, 'status': 'deleting_storage', 'ready': True,
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


@pytest.mark.parametrize('failure_at', ['ban', 'ready', 'storage_deleted', 'purge', 'legacy', 'auth', 'complete'])
def test_each_failure_keeps_retry_receipt_and_releases_capacity(monkeypatch, failure_at):
    events = []
    def step(name):
        events.append(name)
        if name == failure_at:
            raise HTTPException(503, 'Synthetic outage')
        return {'id': 'job', 'target_user_id': TARGET, 'ready': True, 'status': 'deleting_storage'}
    monkeypatch.setattr(account_erasure, '_control', lambda _a, _r, action, _s, payload=None: step(action))
    monkeypatch.setattr(account_erasure, '_ban_account', lambda *_: step('ban'))
    monkeypatch.setattr(account_erasure, '_purge_runtime', lambda *_: step('purge'))
    monkeypatch.setattr(account_erasure, 'commercial_rpc', lambda *_: step('legacy'))
    monkeypatch.setattr(account_erasure, '_delete_auth_account', lambda *_: step('auth'))
    with pytest.raises(HTTPException) as failure:
        account_erasure.execute_account_erasure('admin', 'request', _settings(), storage_delete=lambda *_: 1)
    assert failure.value.status_code == 503
    assert events[-1] == 'fail'
    assert account_erasure.HEAVY_WORK_SLOT.acquire(blocking=False)
    account_erasure.HEAVY_WORK_SLOT.release()


def test_failed_receipt_does_not_hide_original_error(monkeypatch):
    def control(_a, _r, action, _s, payload=None):
        if action == 'fail':
            raise RuntimeError('Receipt offline')
        return {'id': 'job', 'target_user_id': TARGET, 'ready': False}
    monkeypatch.setattr(account_erasure, '_control', control)
    monkeypatch.setattr(account_erasure, '_ban_account', lambda *_: None)
    with pytest.raises(HTTPException) as failure:
        account_erasure.execute_account_erasure('admin', 'request', _settings(), storage_delete=lambda *_: pytest.fail())
    assert failure.value.status_code == 409


def test_inflight_local_work_blocks_erasure(monkeypatch):
    monkeypatch.setattr(account_erasure, '_control', lambda *_args, **_kwargs:
                        {'id': 'job', 'target_user_id': TARGET, 'ready': True})
    monkeypatch.setattr(account_erasure, '_ban_account', lambda *_: None)
    assert account_erasure.HEAVY_WORK_SLOT.acquire(blocking=False)
    try:
        with pytest.raises(HTTPException) as failure:
            account_erasure.execute_account_erasure('admin', 'request', _settings(), storage_delete=lambda *_: pytest.fail())
        assert failure.value.status_code == 409
        assert not account_erasure.HEAVY_WORK_SLOT.acquire(blocking=False)
    finally:
        account_erasure.HEAVY_WORK_SLOT.release()


@pytest.mark.parametrize('entry', [{'name': '../other'}, {'name': 'a/b'}, {'name': 'a\\b'}, {'name': ''}])
def test_storage_listing_rejects_unsafe_entries(monkeypatch, entry):
    monkeypatch.setattr(account_erasure, '_storage_entries', lambda *_: [entry])
    with pytest.raises(ValueError):
        account_erasure.list_user_storage_objects(TARGET, _settings())


def test_storage_only_traverses_canonical_owner(monkeypatch):
    def listing(prefix, _settings):
        if prefix == TARGET:
            return [{'name': 'raw.csv', 'id': '1'}, {'name': 'derived', 'id': None}]
        assert prefix == TARGET + '/derived'
        return [{'name': 'clean.xlsx', 'id': '2'}]
    monkeypatch.setattr(account_erasure, '_storage_entries', listing)
    assert account_erasure.list_user_storage_objects(TARGET, _settings()) == [TARGET + '/raw.csv', TARGET + '/derived/clean.xlsx']
    with pytest.raises(ValueError):
        account_erasure.list_user_storage_objects('../someone-else', _settings())


@pytest.mark.parametrize('page', [[None], {'error': 'bad response'}])
def test_malformed_storage_response_fails_closed(monkeypatch, page):
    monkeypatch.setattr(httpx, 'post', lambda *_args, **_kwargs:
                        httpx.Response(200, json=page, request=httpx.Request('POST', 'https://test.invalid')))
    with pytest.raises(ValueError):
        account_erasure._storage_entries(TARGET, _settings())


def test_auth_deletion_requires_independent_confirmation(monkeypatch):
    methods = []
    def request(method, *_args, **_kwargs):
        methods.append(method)
        return httpx.Response(200, json={}, request=httpx.Request(method, 'https://test.invalid'))
    monkeypatch.setattr(account_erasure, '_auth_request', request)
    with pytest.raises(RuntimeError, match='Auth still contains'):
        account_erasure._delete_auth_account(TARGET, _settings())
    assert methods == ['DELETE', 'GET']


def test_auth_already_absent_can_be_retried(monkeypatch):
    monkeypatch.setattr(account_erasure, '_auth_request', lambda *_args, **_kwargs: httpx.Response(404))
    account_erasure._delete_auth_account(TARGET, _settings())
