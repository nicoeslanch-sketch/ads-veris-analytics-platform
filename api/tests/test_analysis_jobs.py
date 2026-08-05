import threading
import time

from app.analysis_jobs import AnalysisJobManager
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
