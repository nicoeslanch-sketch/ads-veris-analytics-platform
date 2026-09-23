import json
from concurrent.futures import ThreadPoolExecutor

from fastapi import HTTPException
import pytest

from app import operational_health as ops
from app.routes import admin


def healthy():
    return {'http': {'instances': 1, 'requests': 100, 'errors': 0, 'limited': 0, 'slow': 0},
            'queue': {'queued': 0, 'running': 0, 'max_active': 32},
            'storage': {'used_bytes': 10, 'reserved_bytes': 0, 'limit_bytes': 100}}


def test_window_is_bounded_expires_and_counts_threads():
    clock = [0]
    window = ops.RequestWindow(clock=lambda: clock[0])
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: window.record(503, 6000), range(100)))
    assert window.snapshot() == {'requests': 100, 'errors': 100, 'limited': 0, 'slow': 100}
    clock[0] = 300
    assert window.snapshot()['requests'] == 0
    for second in range(1000):
        clock[0] = second + 301
        window.record(429, 3)
    assert len(window.buckets) == 300
    assert window.snapshot() == {'requests': 300, 'errors': 0, 'limited': 300, 'slow': 0}


@pytest.mark.parametrize('section,changes,code', [
    ('http', {'instances': 0}, 'MONITOR_STALE'),
    ('http', {'errors': 5}, 'HTTP_ERRORS'),
    ('http', {'limited': 10}, 'HTTP_LIMITED'),
    ('http', {'slow': 20}, 'HTTP_SLOW'),
    ('queue', {'expired_leases': 1}, 'WORKER_STALLED'),
    ('queue', {'long_running': 1}, 'WORKER_STALLED'),
    ('queue', {'oldest_wait_seconds': 120}, 'QUEUE_WAIT'),
    ('queue', {'queued': 26}, 'QUEUE_PRESSURE'),
    ('queue', {'failed_retained_15m': 3}, 'JOBS_FAILED'),
    ('storage', {'reserved_bytes': 70}, 'STORAGE_PRESSURE'),
    ('storage', {'stale_reservations': 1}, 'STORAGE_PENDING'),
    ('storage', {'unknown_sizes': 1}, 'STORAGE_UNKNOWN'),
])
def test_actionable_alert_thresholds(section, changes, code):
    data = healthy()
    assert ops.alerts_for(data) == []
    data[section].update(changes)
    assert [a['code'] for a in ops.alerts_for(data)] == [code]


def test_tiny_windows_do_not_trigger_error_rate_alert():
    data = healthy()
    data['http'].update(requests=1, errors=1)
    assert not ops.alerts_for(data)


def test_monitor_only_logs_transitions_and_never_exception_payload(monkeypatch, caplog):
    def unavailable(*args):
        raise ValueError('secret-token customer@example.invalid')
    monkeypatch.setattr(ops, 'commercial_rpc', unavailable)
    monitor = ops.OperationalMonitor(None)
    with caplog.at_level('INFO', logger='uvicorn.error'):
        monitor.poll()
        monitor.poll()
        monkeypatch.setattr(ops, 'commercial_rpc', lambda *args: healthy())
        monitor.poll()
    records = [json.loads(r.message) for r in caplog.records]
    assert [r['state'] for r in records] == ['active', 'resolved']
    assert 'secret-token' not in caplog.text and '@' not in caplog.text


def test_operations_fail_closed_for_non_admin(client, auth_headers, monkeypatch):
    def denied(*args):
        raise HTTPException(403, 'Admin required')
    monkeypatch.setattr(admin, '_require_admin_sync', denied)
    monkeypatch.setattr(admin, 'health_snapshot', lambda *args: pytest.fail('must not read'))
    assert client.get('/admin/operations', headers=auth_headers).status_code == 403


def test_operations_admin_gets_aggregate_snapshot(client, auth_headers, monkeypatch):
    monkeypatch.setattr(admin, '_require_admin_sync', lambda *args: None)
    monkeypatch.setattr(admin, 'health_snapshot', lambda *args: {**healthy(), 'alerts': []})
    r = client.get('/admin/operations', headers=auth_headers)
    assert r.status_code == 200 and r.json()['http']['requests'] == 100
