import json
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest

from app import analysis_timing as timing


def captured(monkeypatch):
    emit = Mock()
    monkeypatch.setattr(timing.logger, 'info', emit)
    return emit


def test_stage_timings_aggregate_and_exclude_sensitive_labels(monkeypatch):
    emit = captured(monkeypatch)
    clock = iter([0, 1, 3, 4, 7, 10])
    monkeypatch.setattr(timing, 'perf_counter', lambda: next(clock))
    with timing.analysis_timing('metrics'):
        with timing.analysis_stage('prepare_sheets'):
            pass
        with timing.analysis_stage('prepare_sheets'):
            pass
        with timing.analysis_stage('private-customer/source.xlsx'):
            pass
    row = json.loads(emit.call_args.args[0])
    assert row['stages'] == {'prepare_sheets': {'calls': 2, 'duration_ms': 5000.0}}
    assert row['duration_ms'] == 10000.0
    assert row['outcome'] == 'returned'
    assert row['operation'] == 'metrics'
    assert len(row['trace_id']) == 32
    assert 'private-customer' not in emit.call_args.args[0]
    assert timing._ACTIVE.get() is None


def test_stage_without_active_execution_is_a_noop(monkeypatch):
    emit = captured(monkeypatch)
    monkeypatch.setattr(timing, 'perf_counter', Mock(side_effect=AssertionError('No clock needed')))
    with timing.analysis_stage('compute_metrics'):
        pass
    emit.assert_not_called()


def test_failure_is_rethrown_without_exception_contents_in_log(monkeypatch):
    emit = captured(monkeypatch)
    error = ValueError('private-account-token')
    with pytest.raises(ValueError) as result:
        with timing.analysis_timing('private-workbook-name'):
            with timing.analysis_stage('compute_metrics'):
                raise error
    assert result.value is error
    row = json.loads(emit.call_args.args[0])
    assert row['outcome'] == 'raised'
    assert row['operation'] == 'other'
    assert row['stages']['compute_metrics']['calls'] == 1
    assert 'private-' not in emit.call_args.args[0]
    assert timing._ACTIVE.get() is None


@pytest.mark.parametrize('raise_inside', [False, True])
def test_logging_failure_cannot_change_job_result(monkeypatch, raise_inside):
    monkeypatch.setattr(timing.logger, 'info', Mock(side_effect=OSError('sink unavailable')))
    error = ValueError('original')
    def work():
        with timing.analysis_timing('metrics'):
            if raise_inside:
                raise error
            return 42
    if raise_inside:
        with pytest.raises(ValueError) as result:
            work()
        assert result.value is error
    else:
        assert work() == 42
    assert timing._ACTIVE.get() is None


def test_nested_executions_restore_parent_and_do_not_share_stages(monkeypatch):
    emit = captured(monkeypatch)
    with timing.analysis_timing('metrics'):
        parent = timing._ACTIVE.get()
        with timing.analysis_timing('clean_batch'):
            with timing.analysis_stage('source_download'):
                pass
        assert timing._ACTIVE.get() is parent
        with timing.analysis_stage('compute_metrics'):
            pass
    rows = [json.loads(call.args[0]) for call in emit.call_args_list]
    assert set(rows[0]['stages']) == {'source_download'}
    assert set(rows[1]['stages']) == {'compute_metrics'}
    assert rows[0]['trace_id'] != rows[1]['trace_id']


def test_simultaneous_threads_do_not_mix_timings(monkeypatch):
    emit = captured(monkeypatch)
    barrier = threading.Barrier(2)
    def work(stage):
        with timing.analysis_timing('metrics'):
            with timing.analysis_stage(stage):
                barrier.wait(timeout=5)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(work, ['source_download', 'compute_metrics']))
    rows = [json.loads(call.args[0]) for call in emit.call_args_list]
    assert len(rows) == 2
    assert {tuple(row['stages']) for row in rows} == {('source_download',), ('compute_metrics',)}


def test_decorator_preserves_results_signature_and_exception(monkeypatch):
    emit = captured(monkeypatch)
    @timing.analysis_stage('compute_metrics')
    def sample(value):
        return value
    with timing.analysis_timing('metrics'):
        assert sample(42) == 42
        assert sample(value=7) == 7
    row = json.loads(emit.call_args.args[0])
    assert row['stages']['compute_metrics']['calls'] == 2
    assert sample.__name__ == 'sample'
