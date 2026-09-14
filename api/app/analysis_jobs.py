"""Trabajos recuperables para métricas interactivas pesadas."""

from __future__ import annotations

import copy
import logging
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Callable

from fastapi import HTTPException

from .config import Settings
from .processing_capacity import HEAVY_WORK_SLOT
from .shared_analysis import SharedAnalysisCoordinator, coordinator_for, shared_key_digest

TERMINAL = {"completed", "failed", "cancelled"}
logger = logging.getLogger(__name__)
_PROGRESS: ContextVar[Callable | None] = ContextVar("analysis_job_progress", default=None)


class JobCancelled(Exception):
    """Cooperative cancellation between bounded processing phases."""


def report_job_progress(
    phase: str, completed: int, total: int, sheet: str | None = None,
) -> None:
    reporter = _PROGRESS.get()
    if reporter is not None:
        reporter(phase, completed, total, sheet)


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
        self.max_jobs_per_user = settings.analysis_max_jobs_per_user
        self.max_input_bytes = settings.analysis_queue_input_bytes
        self.max_user_input_bytes = settings.analysis_user_input_bytes
        self.retry_retention_seconds = settings.analysis_retry_retention_seconds
        self.input_bytes: dict[tuple[str, str], int] = {}
        self.retry_deadlines: dict[tuple[str, str], float] = {}
        self.jobs: "OrderedDict[tuple[str, str], dict[str, Any]]" = OrderedDict()
        self.producers: dict[tuple[str, str], Callable[[], dict[str, Any]]] = {}
        self.lock = threading.Lock()
        # Render usa una instancia de memoria acotada. Dos cálculos pandas/XLSX
        # simultáneos pueden dejar sin respuesta incluso al health check. Los
        # trabajos siguen siendo asíncronos, pero el proceso ejecuta uno pesado
        # a la vez y mantiene libre el event loop para estado y navegación.
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="analysis-job")

    def _release_input_locked(self, identity: tuple[str, str]) -> None:
        self.producers.pop(identity, None)
        self.input_bytes.pop(identity, None)
        self.retry_deadlines.pop(identity, None)

    def _prune_input_locked(self) -> None:
        expired = [key for key, deadline in self.retry_deadlines.items() if deadline <= monotonic()]
        for key in expired:
            self._release_input_locked(key)

    def _remember(self, user_id: str, job: dict[str, Any]) -> dict[str, Any]:
        identity = (user_id, str(job["job_id"]))
        with self.lock:
            self._prune_input_locked()
            self.jobs[identity] = copy.deepcopy(job)
            if job.get("status") == "completed":
                self._release_input_locked(identity)
            elif job.get("status") in {"failed", "cancelled"} and identity in self.producers:
                self.retry_deadlines.setdefault(identity, monotonic() + self.retry_retention_seconds)
            self.jobs.move_to_end(identity)
            while len(self.jobs) > self.max_jobs:
                removed = next((key for key, value in self.jobs.items()
                                if value.get("status") in TERMINAL), None)
                if removed is None:
                    break
                self.jobs.pop(removed)
                self._release_input_locked(removed)
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
        *,
        retained_input_bytes: int = 0,
    ) -> dict[str, Any]:
        if retained_input_bytes < 0:
            raise ValueError("retained_input_bytes must be nonnegative")
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
            # Recheck and reserve atomically: concurrent requests must not all
            # pass the cap before _remember registers their queued jobs.
            current = self.jobs.get(identity)
            if current and identity in self.producers and current.get("status") not in TERMINAL:
                return copy.deepcopy(current)
            if current and current.get("status") == "completed":
                return copy.deepcopy(current)
            self._check_capacity_locked(user_id)
            self._prune_input_locked()
            retained = sum(size for key, size in self.input_bytes.items() if key != identity)
            user_retained = sum(size for key, size in self.input_bytes.items() if key != identity and key[0] == user_id)
            if retained + retained_input_bytes > self.max_input_bytes or user_retained + retained_input_bytes > self.max_user_input_bytes:
                raise HTTPException(status_code=429, detail="La cola alcanzo su presupuesto de archivos en memoria. Espera a que termine un proceso y vuelve a intentar.", headers={"Retry-After": "10"})
            self.input_bytes[identity] = retained_input_bytes
            self.retry_deadlines.pop(identity, None)
            self.producers[identity] = producer
            self.jobs[identity] = copy.deepcopy(job)
        self._remember(user_id, job)
        self.executor.submit(self._run, user_id, job_id)
        return copy.deepcopy(job)

    def _check_capacity_locked(self, user_id: str) -> None:
        active = [key for key, value in self.jobs.items() if value.get("status") not in TERMINAL]
        if len(active) >= self.max_jobs:
            raise HTTPException(status_code=429, detail="Hay demasiados procesos pendientes. Espera a que termine uno y vuelve a intentar.", headers={"Retry-After": "10"})
        if sum(key[0] == user_id for key in active) >= self.max_jobs_per_user:
            raise HTTPException(status_code=429, detail="Ya tienes varios procesos pendientes. Espera a que termine uno antes de iniciar otro.", headers={"Retry-After": "10"})

    def _run(self, user_id: str, job_id: str) -> None:
        # Legacy HTTP calls and background jobs share the same memory budget.
        # Waiting here does not consume an ASGI/threadpool worker or reject jobs.
        with HEAVY_WORK_SLOT:
            self._execute(user_id, job_id)

    def _execute(self, user_id: str, job_id: str) -> None:
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

        def progress(phase: str, completed: int, total: int, sheet: str | None) -> None:
            current = self.get(user_id, job_id) or job
            if current.get("cancel_requested"):
                raise JobCancelled()
            job.update(current)
            job.update(phase=phase, completed_phases=completed,
                       total_phases=total, current_sheet=sheet, updated_at=_now())
            self._remember(user_id, job)

        token = _PROGRESS.set(progress)
        try:
            result = producer()
        except JobCancelled:
            job.update(status="cancelled", phase="cancelled", updated_at=_now())
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else "El análisis no pudo completarse."
            job.update(status="failed", phase="failed", error=detail, updated_at=_now())
        except Exception:
            logger.exception("analysis_job_failed job_id=%s", job_id)
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
                    completed_phases=job.get("total_phases", 1),
                    result=result,
                    updated_at=_now(),
                )
        finally:
            _PROGRESS.reset(token)
        self._remember(user_id, job)

        if job.get("status") == "completed":
            # Completed closures can retain entire uploaded workbooks.
            with self.lock:
                self._release_input_locked(identity)

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
            self._prune_input_locked()
            producer = self.producers.get(identity)
            current = self.jobs.get(identity)
            if current is not None:
                job = copy.deepcopy(current)
            if job is None or producer is None or job.get("status") not in {"failed", "cancelled"}:
                return job
            self._check_capacity_locked(user_id)
            self.retry_deadlines.pop(identity, None)
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
            self.jobs[identity] = copy.deepcopy(job)
        self._remember(user_id, job)
        self.executor.submit(self._run, user_id, job_id)
        return job


_MANAGERS: dict[tuple[Any, ...], AnalysisJobManager] = {}
_MANAGERS_LOCK = threading.Lock()


def manager_for(settings: Settings) -> AnalysisJobManager:
    key = (
        settings.analysis_redis_url,
        settings.analysis_cache_ttl_seconds,
        settings.analysis_lock_ttl_seconds,
        settings.analysis_max_jobs_per_user,
        settings.analysis_queue_input_bytes,
        settings.analysis_user_input_bytes,
        settings.analysis_retry_retention_seconds,
    )
    with _MANAGERS_LOCK:
        if key not in _MANAGERS:
            _MANAGERS[key] = AnalysisJobManager(settings)
        return _MANAGERS[key]
