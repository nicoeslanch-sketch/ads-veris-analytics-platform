from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app.analysis_jobs import AnalysisJobManager
from app.config import Settings


def manager():
    result = AnalysisJobManager(Settings(analysis_queue_input_bytes=32, analysis_user_input_bytes=16))
    result.executor.shutdown(wait=True)
    result.executor = Mock()
    return result


def test_per_user_and_total_budget_includes_queued_files():
    jobs = manager()
    a = jobs.submit('a', ('a', 1), lambda: {}, retained_input_bytes=15)
    with pytest.raises(HTTPException) as error:
        jobs.submit('a', ('a', 2), lambda: {}, retained_input_bytes=2)
    assert error.value.status_code == 429
    jobs.submit('b', ('b', 1), lambda: {}, retained_input_bytes=15)
    with pytest.raises(HTTPException):
        jobs.submit('c', ('c', 1), lambda: {}, retained_input_bytes=3)
    assert sum(jobs.input_bytes.values()) == 30
    # Reusing a queued request must not reserve its bytes twice.
    assert jobs.submit('a', ('a', 1), lambda: {}, retained_input_bytes=15)['job_id'] == a['job_id']
    assert sum(jobs.input_bytes.values()) == 30
    jobs._execute('a', a['job_id'])
    assert sum(jobs.input_bytes.values()) == 15
    jobs.submit('c', ('c', 1), lambda: {}, retained_input_bytes=16)
    assert sum(jobs.input_bytes.values()) == 31


def test_failed_payload_retained_for_retry_then_reclaimed(monkeypatch):
    jobs = manager()
    def fail():
        raise HTTPException(422, 'invalid data')
    job = jobs.submit('a', ('a', 1), fail, retained_input_bytes=15)
    jobs._execute('a', job['job_id'])
    assert sum(jobs.input_bytes.values()) == 15
    retried = jobs.retry('a', job['job_id'])
    assert retried['status'] == 'queued'
    assert not jobs.retry_deadlines
    jobs._execute('a', job['job_id'])
    deadline = max(jobs.retry_deadlines.values())
    monkeypatch.setattr('app.analysis_jobs.monotonic', lambda: deadline + 1)
    jobs.submit('a', ('a', 2), lambda: {}, retained_input_bytes=16)
    assert ('a', job['job_id']) not in jobs.producers
    assert sum(jobs.input_bytes.values()) == 16


def test_terminal_eviction_releases_payload():
    jobs = manager()
    jobs.max_jobs = 1
    first = jobs.submit('a', ('one',), lambda: {}, retained_input_bytes=10)
    jobs.cancel('a', first['job_id'])
    jobs._execute('a', first['job_id'])
    jobs.submit('b', ('two',), lambda: {}, retained_input_bytes=10)
    assert len(jobs.producers) == 1
    assert sum(jobs.input_bytes.values()) == 10
