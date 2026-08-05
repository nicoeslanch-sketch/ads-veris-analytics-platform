"""Trabajos recuperables para métricas interactivas pesadas."""

from __future__ import annotations

import copy
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import HTTPException

from .config import Settings
from .shared_analysis import SharedAnalysisCoordinator, coordinator_for, shared_key_digest

TERMINAL = {"completed", "failed", "cancelled"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AnalysisJobManager:
    def __init__(
        self,
        settings: Settings,
        *,
        coordinator: SharedAnalysisCoordinator | None = None,
        max_jobs: int = 32,
    ) -> None:
        self.coordinator = coordinator or coordinator_for(settings)
        self.max_jobs = max_jobs
        self.jobs: "OrderedDict[tuple[str, str], dict[str, Any]]" = OrderedDict()
        self.producers: dict[tuple[str, str], Callable[[], dict[str, Any]]] = {}
        self.lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="analysis-job")

    def _remember(self, user_id: str, job: dict[str, Any]) -> dict[str, Any]:
        identity = (user_id, str(job["job_id"]))
        with self.lock:
            self.jobs[identity] = copy.deepcopy(job)
            self.jobs.move_to_end(identity)
            while len(self.jobs) > self.max_jobs:
                removed, _value = self.jobs.popitem(last=False)
                self.producers.pop(removed, None)
        self.coordinator.store_job(user_id, str(job["job_id"]), job)
        return copy.deepcopy(job)

    def get(self, user_id: str, job_id: str) -> dict[str, Any] | None:
        shared = self.coordinator.get_job(user_id, job_id)
        if shared is not None:
            return self._remember(user_id, shared)
        with self.lock:
            job = self.jobs.get((user_id, job_id))
            return copy.deepcopy(job) if job is not None else None

    def submit(
        self,
        user_id: str,
        idempotency_key: tuple[Any, ...],
        producer: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        job_id = shared_key_digest(idempotency_key)[:32]
        existing = self.get(user_id, job_id)
        identity = (user_id, job_id)
        with self.lock:
            owned_by_this_process = identity in self.producers
        if existing and existing.get("status") == "completed":
            return existing
        if (
            existing
            and existing.get("status") in {"queued", "running"}
            and owned_by_this_process
        ):
            return existing
        job = {
            "job_id": job_id,
            "status": "queued",
            "phase": "queued",
            "completed_phases": 0,
            "total_phases": 1,
            "attempt": int(existing.get("attempt", 0)) + 1 if existing else 1,
            "created_at": existing.get("created_at", _now()) if existing else _now(),
            "updated_at": _now(),
            "cancel_requested": False,
            "result": None,
            "error": None,
        }
        with self.lock:
            self.producers[identity] = producer
        self._remember(user_id, job)
        self.executor.submit(self._run, user_id, job_id)
        return copy.deepcopy(job)

    def _run(self, user_id: str, job_id: str) -> None:
        identity = (user_id, job_id)
        job = self.get(user_id, job_id)
        with self.lock:
            producer = self.producers.get(identity)
        if job is None or producer is None:
            return
        if job.get("cancel_requested"):
            job.update(status="cancelled", phase="cancelled", updated_at=_now())
            self._remember(user_id, job)
            return
        job.update(status="running", phase="analysis", updated_at=_now())
        self._remember(user_id, job)
        try:
            result = producer()
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else "El análisis no pudo completarse."
            job.update(status="failed", phase="failed", error=detail, updated_at=_now())
        except Exception:
            # El detalle técnico queda en logs del servidor; la API no expone
            # pandas, SQL, rutas ni infraestructura al usuario final.
            job.update(
                status="failed",
                phase="failed",
                error="El análisis no pudo completarse con los datos disponibles.",
                updated_at=_now(),
            )
        else:
            current = self.get(user_id, job_id) or job
            if current.get("cancel_requested"):
                job.update(status="cancelled", phase="cancelled", result=None, updated_at=_now())
            else:
                job.update(
                    status="completed",
                    phase="completed",
                    completed_phases=1,
                    result=result,
                    updated_at=_now(),
                )
        self._remember(user_id, job)

    def cancel(self, user_id: str, job_id: str) -> dict[str, Any] | None:
        job = self.get(user_id, job_id)
        if job is None:
            return None
        if job.get("status") not in TERMINAL:
            job.update(cancel_requested=True, phase="cancelling", updated_at=_now())
            self._remember(user_id, job)
        return job

    def retry(self, user_id: str, job_id: str) -> dict[str, Any] | None:
        job = self.get(user_id, job_id)
        identity = (user_id, job_id)
        with self.lock:
            producer = self.producers.get(identity)
        if job is None or producer is None or job.get("status") not in {"failed", "cancelled"}:
            return job
        job.update(
            status="queued",
            phase="queued",
            completed_phases=0,
            attempt=int(job.get("attempt", 1)) + 1,
            cancel_requested=False,
            result=None,
            error=None,
            updated_at=_now(),
        )
        self._remember(user_id, job)
        self.executor.submit(self._run, user_id, job_id)
        return job


_MANAGERS: dict[tuple[str, int, int], AnalysisJobManager] = {}
_MANAGERS_LOCK = threading.Lock()


def manager_for(settings: Settings) -> AnalysisJobManager:
    key = (
        settings.analysis_redis_url,
        settings.analysis_cache_ttl_seconds,
        settings.analysis_lock_ttl_seconds,
    )
    with _MANAGERS_LOCK:
        if key not in _MANAGERS:
            _MANAGERS[key] = AnalysisJobManager(settings)
        return _MANAGERS[key]
