import threading
import time

import pytest
from fastapi import HTTPException

from app.analysis_jobs import AnalysisJobManager, report_job_progress
from app.config import Settings
from app.shared_analysis import SharedAnalysisCoordinator
from tests.test_shared_analysis import FakeRedis


def _manager() -> AnalysisJobManager:
    coordinator = SharedAnalysisCoordinator(
        "redis://test",
        cache_ttl_seconds=60,
        lock_ttl_seconds=30,
        client=FakeRedis(),
    )
    return AnalysisJobManager(Settings(), coordinator=coordinator)


def _wait(manager: AnalysisJobManager, user: str, job_id: str):
    deadline = time.time() + 2
    while time.time() < deadline:
        job = manager.get(user, job_id)
        if job and job["status"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.01)
    raise AssertionError("job timeout")


def test_job_is_idempotent_and_result_is_recoverable():
    manager = _manager()
    calls = 0

    def producer():
        nonlocal calls
        calls += 1
        return {"value": 42}

    first = manager.submit("user", ("metrics", "same"), producer)
    second = manager.submit("user", ("metrics", "same"), producer)
    completed = _wait(manager, "user", first["job_id"])
    assert first["job_id"] == second["job_id"]
    assert completed["result"] == {"value": 42}
    assert calls == 1


def test_job_can_be_cancelled_and_retried_without_duplicate_running_work():
    manager = _manager()
    release = threading.Event()

    def producer():
        release.wait(timeout=1)
        return {"ok": True}

    job = manager.submit("user", ("metrics", "cancel"), producer)
    manager.cancel("user", job["job_id"])
    release.set()
    cancelled = _wait(manager, "user", job["job_id"])
    assert cancelled["status"] == "cancelled"
    retried = manager.retry("user", job["job_id"])
    assert retried and retried["attempt"] == 2
    assert _wait(manager, "user", job["job_id"])["status"] == "completed"


def test_job_reports_real_sheet_progress_and_stops_at_cancel_boundary():
    manager = _manager()
    reached = threading.Event()
    release = threading.Event()
    later = []

    def producer():
        report_job_progress("cleaning", 1, 4, "Ventas")
        reached.set()
        release.wait(timeout=2)
        report_job_progress("cleaning", 2, 4, "Compras")
        later.append(True)
        return {"ok": True}

    job = manager.submit("user", ("batch", "progress"), producer)
    assert reached.wait(timeout=1)
    current = manager.get("user", job["job_id"])
    assert current["current_sheet"] == "Ventas"
    assert current["completed_phases"] == 1
    assert current["total_phases"] == 4
    assert manager.get("other-user", job["job_id"]) is None
    manager.cancel("user", job["job_id"])
    release.set()
    assert _wait(manager, "user", job["job_id"])["status"] == "cancelled"
    assert later == []


def test_job_completion_keeps_total_progress_and_does_not_evict_active_jobs():
    manager = _manager()
    manager.max_jobs = 2
    release = threading.Event()

    def producer():
        release.wait(timeout=2)
        report_job_progress("saving", 3, 4)
        return {"ok": True}

    first = manager.submit("user", ("batch", "first"), producer)
    second = manager.submit("user", ("batch", "second"), producer)
    with manager.lock:
        assert len(manager.producers) == 2
    with pytest.raises(HTTPException) as overloaded:
        manager.submit("user", ("batch", "third"), producer)
    assert overloaded.value.status_code == 429
    release.set()
    for job in (first, second):
        complete = _wait(manager, "user", job["job_id"])
        assert complete["completed_phases"] == complete["total_phases"] == 4
    manager.executor.shutdown(wait=True)
    assert not manager.producers
