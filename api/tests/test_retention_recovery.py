from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import HTTPException

from app.config import Settings
from app.routes import retention as mod
from app import maintenance


@pytest.fixture
def state(monkeypatch):
    old = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    new = datetime.now(timezone.utc).isoformat()
    data = dict(files=[dict(id='new', name='new.csv', created_at=new),
                       dict(id='old', name='old.csv', created_at=old)], jobs={}, deleted=[], unlinked=[])
    monkeypatch.setattr(mod, 'get_profile_flags', lambda *a, **k: ('basico', False))
    monkeypatch.setattr(mod, '_list_user_files', lambda *a: [dict(x) for x in data['files']])
    monkeypatch.setattr(mod, 'commercial_rpc', lambda *a: 'lease')
    monkeypatch.setattr(mod, '_prune_activity', lambda *a: 0)
    def journal(action, user, settings, **p):
        if action == 'list':
            return [dict(j) for j in data['jobs'].values() if j['stage'] in ('pending', 'storage_deleted')]
        if action == 'begin':
            key = p['p_name']
            data['jobs'].setdefault(key, dict(id=key, stage='pending', object_name=key,
                                            object_id=p['p_object_id'], object_stamp=p['p_stamp']))
            return dict(data['jobs'][key])
        data['jobs'][p['p_id']]['stage'] = p['p_stage']
    def delete(user, names, settings):
        data['deleted'].extend(names)
        data['files'] = [f for f in data['files'] if f['name'] not in names]
    monkeypatch.setattr(mod, '_journal', journal)
    monkeypatch.setattr(mod, '_delete_files', delete)
    monkeypatch.setattr(mod, '_unlink_datasets', lambda u, n, s: data['unlinked'].extend(n))
    return data, Settings(_env_file=None, storage_keep_last=1)


def test_audit_never_mutates_or_claims(state, monkeypatch):
    data, settings = state
    monkeypatch.setattr(mod, 'commercial_rpc', lambda *a: pytest.fail('read-only scan'))
    result = mod._retention_sync('owner', settings, dry_run=True)
    assert result['candidatos'] == 1 and result['simulacion']
    assert not data['jobs'] and not data['deleted'] and not data['unlinked']


def test_unlink_failure_retries_without_deleting_again(state, monkeypatch):
    data, settings = state
    def fail(*a):
        raise httpx.ConnectError('unavailable')
    monkeypatch.setattr(mod, '_unlink_datasets', fail)
    with pytest.raises(httpx.ConnectError):
        mod._retention_sync('owner', settings)
    assert data['jobs']['old.csv']['stage'] == 'storage_deleted'
    monkeypatch.setattr(mod, '_unlink_datasets', lambda u, n, s: data['unlinked'].extend(n))
    mod._retention_sync('owner', settings)
    assert data['deleted'] == ['old.csv'] and data['unlinked'] == ['old.csv']
    assert data['jobs']['old.csv']['stage'] == 'completed'


def test_journal_failure_stops_before_delete(state, monkeypatch):
    data, settings = state
    def fail(*a, **kw):
        raise HTTPException(503, 'unavailable')
    monkeypatch.setattr(mod, '_journal', fail)
    with pytest.raises(HTTPException):
        mod._retention_sync('owner', settings)
    assert not data['deleted']


@pytest.mark.parametrize('change', ['id', 'last_accessed_at'])
def test_changed_object_is_cancelled(state, monkeypatch, change):
    data, settings = state
    listing = mod._list_user_files
    calls = []
    def changing(*args):
        calls.append(1)
        if len(calls) == 2:
            data['files'][1][change] = 'replacement' if change == 'id' else datetime.now(timezone.utc).isoformat()
        return listing(*args)
    monkeypatch.setattr(mod, '_list_user_files', changing)
    mod._retention_sync('owner', settings)
    assert not data['deleted'] and not data['unlinked']
    assert data['jobs']['old.csv']['stage'] == 'cancelled'


def test_unknown_timestamp_is_protected(state):
    data, settings = state
    data['files'].append(dict(id='unknown', name='unknown.csv', created_at='bad'))
    result = mod._retention_sync('owner', settings)
    assert result['eliminados'] == 1
    assert 'unknown.csv' not in data['deleted']
    assert mod._parse_ts('2026-01-01').tzinfo == timezone.utc


@pytest.mark.parametrize('lease', [None, 'expired'])
def test_no_lease_or_expired_lease_prevents_deletion(state, monkeypatch, lease):
    data, settings = state
    monkeypatch.setattr(mod, 'commercial_rpc', lambda n, p, s: lease if p['p_action'] == 'claim' else None)
    with pytest.raises(HTTPException) as exc:
        mod._retention_sync('owner', settings)
    assert exc.value.status_code == 409 and not data['deleted']


def test_storage_pagination_and_virtual_directories(monkeypatch):
    rows = [dict(id=str(i), name=f'{i}.csv') for i in range(1000)]
    calls = []
    def post(url, **kw):
        calls.append(kw['json']['offset'])
        return httpx.Response(200, request=httpx.Request('POST', url),
            json=rows if len(calls) == 1 else [dict(id=None, name='virtual'), dict(id='tail', name='tail.csv')])
    monkeypatch.setattr(mod.httpx, 'post', post)
    assert len(mod._list_user_files('owner', Settings(_env_file=None))) == 1001
    assert calls == [0, 1000]


@pytest.mark.parametrize('payload', [[], {}, [{'name': 'other/old.csv'}]])
def test_storage_delete_requires_explicit_confirmation(monkeypatch, payload):
    monkeypatch.setattr(mod.httpx, 'request', lambda *a, **kw: httpx.Response(200,
        request=httpx.Request('DELETE', 'https://example.test'), json=payload))
    with pytest.raises(HTTPException):
        mod._delete_files('owner', ['old.csv'], Settings(_env_file=None))


def test_scheduler_is_bounded_read_only_and_reports_no_identifiers(monkeypatch):
    calls = []
    def rpc(name, payload, settings):
        calls.append(payload)
        if payload['p_action'] == 'claim':
            return dict(lease='test-lease', users=['owner-private'])
        return {'acknowledged': True}
    def scan(user, settings, *, dry_run):
        assert dry_run
        return dict(candidatos=2, eliminados=0)
    monkeypatch.setattr(maintenance, 'commercial_rpc', rpc)
    monkeypatch.setattr(maintenance, '_retention_sync', scan)
    maintenance.RetentionScheduler(Settings(_env_file=None)).poll()
    assert calls[-1]['p_report'] == dict(mode='audit', accounts=1, candidates=2, deleted=0, errors=0)
    assert 'owner-private' not in str(calls[-1])
