import json
import threading
from copy import deepcopy
from unittest.mock import Mock

import httpx
import pytest
from fastapi import HTTPException

from app import durable_analysis as durable
from app.analysis_jobs import report_job_progress
from app.analysis_worker import AnalysisWorker, LeaseLost, execute_job
from app.auth import AuthenticatedUser, get_current_user
from app.config import Settings, get_settings
from app.main import app
from app.processing_capacity import HEAVY_WORK_SLOT
from app.routes import pipeline
from app.version import ENGINE_VERSION

OWNER = '00000000-0000-4000-8000-000000000001'
DATASET = '00000000-0000-4000-8000-000000000002'
PATH = OWNER + '/source.csv'


def settings(**kwargs):
    return Settings(_env_file=None, analysis_durable_mode='external', plan_enforcement=False,
                    supabase_url='https://synthetic.invalid', supabase_service_role_key='test', **kwargs)


def job():
    return dict(job_id='dq_' + 'a'*32, user_id=OWNER, dataset_id=DATASET, source_path=PATH,
                engine_version=ENGINE_VERSION, kind='metrics', options={}, lease_token='lease-1',
                status='running', cancel_requested=False)


class FakeRepository:
    def __init__(self):
        self.job = job()
        self.finished = []
        self.calls = []
        self.stale = False

    def call(self, action, user_id=None, job_id=None, payload=None, token=None):
        self.calls.append(action)
        if action == 'finish':
            if self.stale:
                return None
            self.finished.append(payload)
        if action != 'claim' and self.stale:
            return None
        return deepcopy(self.job)


def test_reference_identity_is_canonical_and_has_no_workbook_bytes(monkeypatch):
    repo = durable.DurableAnalysisRepository(settings())
    calls = []
    def call(action, user, identifier, payload):
        calls.append((identifier, payload))
        return {**job(), 'job_id': identifier}
    monkeypatch.setattr(repo, 'call', call)
    one = repo.enqueue(OWNER, DATASET, PATH, 'metrics', {'rules': {}, 'revision': 2})
    two = repo.enqueue(OWNER, DATASET, PATH, 'metrics', {'revision': 2, 'rules': {}})
    assert one['job_id'] == two['job_id']
    assert 'lease_token' not in one and 'source_path' not in one
    assert len(json.dumps(calls[0][1])) < 500
    assert not any(callable(value) for value in calls[0][1].values())


def test_cross_owner_path_and_oversize_options_rejected_before_rpc(monkeypatch):
    repo = durable.DurableAnalysisRepository(settings())
    monkeypatch.setattr(repo, 'call', Mock(side_effect=AssertionError('Unexpected RPC')))
    for path, options in [('another/source.csv', {}), (PATH, {'large': 'x'*262144})]:
        with pytest.raises(HTTPException):
            repo.enqueue(OWNER, DATASET, path, 'metrics', options)


def test_rpc_fails_closed_and_does_not_requeue_locally(monkeypatch):
    def unavailable(*args, **kwargs):
        raise httpx.ReadTimeout('private infrastructure')
    monkeypatch.setattr(durable.httpx, 'post', unavailable)
    with pytest.raises(HTTPException) as error:
        durable.DurableAnalysisRepository(settings()).get(OWNER, job()['job_id'])
    assert error.value.status_code == 503
    assert 'private' not in error.value.detail


def test_quota_error_preserves_retry_after(monkeypatch):
    monkeypatch.setattr(durable.httpx, 'post', lambda *a, **kw: httpx.Response(200,
        json={'rejected': 429, 'detail': 'Queue full'}, request=httpx.Request('POST', 'https://synthetic.invalid')))
    with pytest.raises(HTTPException) as error:
        durable.DurableAnalysisRepository(settings()).get(OWNER, job()['job_id'])
    assert error.value.headers['Retry-After'] == '10'


def test_worker_executes_and_publishes_only_with_current_lease():
    repo = FakeRepository()
    assert AnalysisWorker(settings(), repo, lambda *_: {'total': 42}).run_once()
    assert repo.finished == [{'status': 'completed', 'result': {'total': 42}}]
    assert repo.calls.count('source') == 2


def test_worker_cannot_publish_after_lease_loss():
    repo = FakeRepository()
    def execute(*_):
        repo.stale = True
        return {'total': 42}
    assert AnalysisWorker(settings(), repo, execute).run_once()
    assert repo.finished == []


def test_cancel_stops_at_progress_boundary():
    repo = FakeRepository()
    later = []
    def execute(*_):
        repo.job['cancel_requested'] = True
        report_job_progress('cleaning', 1, 3, 'Ventas')
        later.append(True)
    AnalysisWorker(settings(), repo, execute).run_once()
    assert not later
    assert repo.finished == [{'status': 'cancelled'}]


def test_shutdown_does_not_publish_and_job_can_be_recovered():
    repo = FakeRepository()
    worker = AnalysisWorker(settings(), repo)
    def execute(*_):
        worker.shutdown()
        report_job_progress('saving', 1, 1)
    worker.execute = execute
    worker.run_once()
    assert not repo.finished


def test_worker_does_not_claim_while_legacy_work_owns_memory_slot():
    repo = FakeRepository()
    with HEAVY_WORK_SLOT:
        assert not AnalysisWorker(settings(), repo).run_once()
    assert not repo.calls


@pytest.mark.parametrize('kind,helper', [
    ('relationship_catalog', '_relationship_catalog_cached_sync'),
    ('relationship_dashboard', '_relationship_dashboard_cached_sync'),
])
def test_worker_uses_same_relationship_engine_and_checks_access(monkeypatch, kind, helper):
    from app import capabilities, storage
    access = Mock()
    compute = Mock(return_value={'available': True, 'total': 42})
    monkeypatch.setattr(capabilities, 'require_capability_for_user', access)
    monkeypatch.setattr(storage, 'download_from_storage', lambda _: b'synthetic')
    monkeypatch.setattr(pipeline, helper, compute)
    current = job()
    current.update(kind=kind, options={'manifest': {'hojas': []}, 'relationship': {'left_sheet': 'Ventas'}})
    assert execute_job(current, settings())['total'] == 42
    assert access.call_args.args[0] == OWNER
    assert compute.call_args.args[-1] == OWNER
    assert kind in durable.KINDS


@pytest.mark.parametrize('outcomes,expected', [
    ([False] * 12, [5] * 12),
    ([RuntimeError(), RuntimeError(), False, False], [7.5, 11.25, 5, 5]),
    ([RuntimeError()] * 12, [7.5, 11.25, 16.875, 25.3125, 37.96875, 56.953125] + [60] * 6),
])
def test_worker_only_backs_off_on_queue_failure(monkeypatch, outcomes, expected):
    from app import analysis_worker as module
    worker = AnalysisWorker(settings(analysis_worker_poll_seconds=5), FakeRepository())
    pending = iter(outcomes)
    waits = []

    def run_once():
        value = next(pending)
        if isinstance(value, Exception):
            raise value
        return value

    def wait(delay):
        waits.append(delay)
        if len(waits) == len(outcomes):
            worker.stop.set()

    monkeypatch.setattr(worker, 'run_once', run_once)
    monkeypatch.setattr(module, 'WAKE', Mock(wait=wait))
    worker.run()
    assert waits == expected


def test_worker_hides_unexpected_exception_details():
    repo = FakeRepository()
    def execute(*_):
        raise RuntimeError('database password private')
    AnalysisWorker(settings(), repo, execute).run_once()
    assert repo.finished[0]['status'] == 'failed'
    assert 'password' not in repo.finished[0]['error']


def test_worker_reuses_existing_metric_engine_without_changing_options(monkeypatch):
    from app import capabilities, storage
    original = job()
    original['options'] = {'mapping': {'monto': 'Venta'}, 'rules': {'trim': False},
                            'eliminar_duplicados': False, 'date_from': '2026-01-01', 'sheet': 'Ventas'}
    gate = Mock()
    monkeypatch.setattr(capabilities, 'require_capability_for_user', gate)
    monkeypatch.setattr(storage, 'download_from_storage', lambda *_: b'monto\n42')
    engine = Mock(return_value={'total': 42})
    monkeypatch.setattr(pipeline, '_metrics_sync', engine)
    assert execute_job(original, settings()) == {'total': 42}
    args = engine.call_args.args
    assert args[2] == {'monto': 'Venta'} and args[6] is False and args[7] == {'trim': False}
    assert args[-1] == OWNER
    gate.assert_called_once()


@pytest.fixture
def durable_client(client, monkeypatch):
    app.dependency_overrides[get_settings] = lambda: settings()
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(OWNER, None, {})
    monkeypatch.setattr(pipeline, 'require_capability_for_user', lambda *_: None)
    monkeypatch.setattr(pipeline, 'reserve_restore_snapshot_revision', lambda *_: 7)
    monkeypatch.setattr(pipeline, '_read_input', Mock(side_effect=AssertionError('API must not download source')))
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.parametrize('endpoint,fields,kind', [
    ('/analysis/jobs/metrics', {}, 'metrics'),
    ('/standardize/jobs', {}, 'standardize'),
    ('/standardize/batch/jobs', {'sheets': '["Ventas"]'}, 'standardize_batch'),
    ('/clean/batch/jobs', {'manifest': '{"hojas":[{"nombre":"Ventas","procesar":true}]}'}, 'clean_batch'),
    ('/clean/export/jobs', {'manifest': '{"hojas":[{"nombre":"Ventas","procesar":true}]}'}, 'clean_export'),
])
def test_routes_enqueue_references_without_loading_excel(durable_client, monkeypatch, endpoint, fields, kind):
    enqueue = Mock(return_value={'job_id': job()['job_id'], 'status': 'queued'})
    monkeypatch.setattr(durable.DurableAnalysisRepository, 'enqueue', enqueue)
    response = durable_client.post(endpoint, data={'storage_path': PATH, 'dataset_id': DATASET, **fields})
    assert response.status_code == 202, response.text
    assert enqueue.call_args.args[3] == kind


def test_queue_poll_hides_other_account_and_does_not_leak_options(durable_client, monkeypatch):
    monkeypatch.setattr(durable.DurableAnalysisRepository, 'call', lambda *_args: None)
    assert durable_client.get('/analysis/jobs/' + job()['job_id']).status_code == 404


def test_auto_mode_only_enables_production():
    assert durable.durable_mode(Settings(_env_file=None)) == 'off'
    assert durable.durable_mode(Settings(_env_file=None, app_env='production')) == 'embedded'


def test_user_retry_reuses_failed_durable_identity(monkeypatch):
    repo = durable.DurableAnalysisRepository(settings())
    call = Mock(side_effect=[{**job(), 'status': 'failed'}, {**job(), 'status': 'queued'}])
    monkeypatch.setattr(repo, 'call', call)
    assert repo.enqueue(OWNER, DATASET, PATH, 'metrics', {})['status'] == 'queued'
    assert call.call_args_list[1].args[0] == 'retry'


@pytest.mark.parametrize('kind,engine_name', [('standardize', '_standardize_import_sync'),
                                             ('standardize_batch', '_standardize_batch_sync'),
                                             ('clean_batch', '_clean_batch_sync')])
def test_worker_preserves_snapshot_revision_and_cleaning_rules(monkeypatch, kind, engine_name):
    from app import capabilities, storage
    monkeypatch.setattr(capabilities, 'require_capability_for_user', lambda *_: None)
    monkeypatch.setattr(storage, 'download_from_storage', lambda *_: b'amount\n42')
    engine = Mock(return_value={'revision': 7, 'rows': 1})
    monkeypatch.setattr(pipeline, engine_name, engine)
    row = job()
    manifest = {'hojas': [{'nombre': 'Ventas', 'procesar': True, 'eliminar_duplicados': False}]}
    row.update(kind=kind, options={'sheet': 'Ventas', 'sheets': ['Ventas'], 'manifest': manifest, 'revision': 7,
                                  'restore_state': {'selected': 'Ventas'}})
    assert execute_job(row, settings()) == {'revision': 7, 'rows': 1}
    args = engine.call_args.args
    assert args[2] == ('Ventas' if kind == 'standardize' else ['Ventas'] if kind == 'standardize_batch' else manifest)
    assert args[3:] == (DATASET, OWNER, 7, {'selected': 'Ventas'})


def test_initial_import_is_admitted_while_heavy_slot_is_busy(durable_client, monkeypatch):
    enqueue = Mock(return_value={'job_id': job()['job_id'], 'status': 'queued'})
    monkeypatch.setattr(durable.DurableAnalysisRepository, 'enqueue', enqueue)
    with HEAVY_WORK_SLOT:
        response = durable_client.post('/standardize/jobs', data={'storage_path': PATH, 'dataset_id': DATASET})
        assert response.status_code == 202, response.text
        assert response.json()['status'] == 'queued'
        assert durable_client.post('/standardize').status_code == 429
    assert enqueue.call_args.args[:4] == (OWNER, DATASET, PATH, 'standardize')


def test_initial_import_local_queue_waits_then_matches_legacy_result(client, auth_headers, monkeypatch):
    from tests.test_analysis_jobs import _manager, _wait
    manager = _manager()
    monkeypatch.setattr(pipeline, 'manager_for', lambda _: manager)
    source = b'Producto,Venta\nA,100\nB,200\n'
    try:
        with HEAVY_WORK_SLOT:
            response = client.post('/standardize/jobs', headers=auth_headers,
                                   files={'file': ('initial.csv', source, 'text/csv')})
            assert response.status_code == 202, response.text
            queued = response.json()
            assert queued['status'] == 'queued'
            assert manager.get('user-test-123', queued['job_id'])['status'] == 'queued'
        completed = _wait(manager, 'user-test-123', queued['job_id'])
        assert completed['status'] == 'completed'
        legacy = client.post('/standardize', headers=auth_headers,
                             files={'file': ('initial.csv', source, 'text/csv')})
        assert legacy.status_code == 200
        assert completed['result'] == legacy.json()
    finally:
        manager.executor.shutdown(wait=True)


@pytest.mark.parametrize('denied', ['capability', 'revision', 'ownership'])
def test_initial_import_fails_closed_before_computing(durable_client, monkeypatch, denied):
    rpc = Mock(side_effect=AssertionError('Denied import must not reach RPC'))
    monkeypatch.setattr(durable.DurableAnalysisRepository, 'call', rpc)
    fields = {'storage_path': PATH, 'dataset_id': DATASET}
    expected = 403
    if denied == 'capability':
        monkeypatch.setattr(pipeline, 'require_capability_for_user', Mock(side_effect=HTTPException(403, 'Denied')))
    elif denied == 'revision':
        monkeypatch.setattr(pipeline, 'reserve_restore_snapshot_revision', lambda *_: None)
        expected = 503
    else:
        fields['storage_path'] = '00000000-0000-4000-8000-000000000009/source.csv'
    response = durable_client.post('/standardize/jobs', data=fields)
    assert response.status_code == expected, response.text
    rpc.assert_not_called()


def test_initial_standardization_persists_the_same_result_and_honors_cancellation(monkeypatch):
    from app.analysis_jobs import JobCancelled
    compute = Mock(return_value={'filas': 2})
    save = Mock()
    progress = Mock()
    monkeypatch.setattr(pipeline, '_standardize_sync', compute)
    monkeypatch.setattr(pipeline, '_store_standardization_restore_snapshot', save)
    monkeypatch.setattr(pipeline, 'report_job_progress', progress)
    state = {'selected': 'Ventas'}
    result = pipeline._standardize_import_sync('book.xlsx', b'book', 'Ventas', DATASET, OWNER, 7, state)
    assert result == {'filas': 2, 'revision': 7}
    save.assert_called_once_with(DATASET, OWNER, b'book', result, 'Ventas', 7, state)
    save.reset_mock()
    progress.side_effect = [None, JobCancelled()]
    with pytest.raises(JobCancelled):
        pipeline._standardize_import_sync('book.xlsx', b'book', 'Ventas', DATASET, OWNER, 8, state)
    save.assert_not_called()


def test_external_export_never_reports_ready_if_only_in_memory(monkeypatch):
    from app import capabilities, storage
    monkeypatch.setattr(capabilities, 'require_capability_for_user', lambda *_: None)
    monkeypatch.setattr(storage, 'download_from_storage', lambda *_: b'amount\n42')
    monkeypatch.setattr(pipeline, '_prune_caches_for_export', lambda *_: None)
    monkeypatch.setattr(pipeline, '_clean_download_book_sync', lambda *_: (b'xlsx', 'clean.xlsx', 'application/xlsx'))
    monkeypatch.setattr(pipeline, 'download_export_cache', lambda *_: None)
    row = job()
    row.update(kind='clean_export', options={'manifest': {'hojas': []}, 'format': 'xlsx'})
    with pytest.raises(HTTPException) as error:
        execute_job(row, settings())
    assert error.value.status_code == 503
    assert 'cuota' in error.value.detail
