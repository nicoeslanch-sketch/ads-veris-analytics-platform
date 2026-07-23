"""P0-6: control global de concurrencia para trabajos pandas pesados.

Cargar (parsear) un archivo es el paso que más memoria y CPU consume del
pipeline. Sin un tope, dos o tres archivos grandes procesándose a la vez
pueden agotar la memoria del proceso aunque cada uno, solo, hubiera
terminado bien — y un 500 por memoria agotada no le explica nada al
usuario. Este módulo acota cuántos trabajos pesados corren a la vez con un
semáforo lógico (contador + condición), una cola acotada (quien no cabe se
rechaza de inmediato) y una espera con timeout (nunca indefinida).

Uso: envolver el paso de carga/parseo (nunca la petición HTTP completa) con
``heavy_job_slot(settings, label=...)`` desde el hilo de threadpool que
ejecuta pandas — el semáforo es de threading, no de asyncio, porque el
trabajo real ya corre fuera del event loop vía run_in_threadpool.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from fastapi import HTTPException, status

from .config import Settings

logger = logging.getLogger("app.concurrency")

_condition = threading.Condition()
_active_jobs = 0
_waiting_jobs = 0
# Contadores acumulados para observabilidad (no se resetean solos; son para
# health checks / métricas puntuales, no una serie temporal).
_total_rejected_queue_full = 0
_total_rejected_timeout = 0


@dataclass(frozen=True)
class ConcurrencySnapshot:
    active: int
    waiting: int
    rejected_queue_full: int
    rejected_timeout: int


def snapshot() -> ConcurrencySnapshot:
    """Estado actual — para /health o un panel de observabilidad."""
    with _condition:
        return ConcurrencySnapshot(
            active=_active_jobs,
            waiting=_waiting_jobs,
            rejected_queue_full=_total_rejected_queue_full,
            rejected_timeout=_total_rejected_timeout,
        )


def _busy_response(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)


@contextmanager
def heavy_job_slot(settings: Settings, *, label: str = "carga de archivo") -> Iterator[None]:
    """Reserva un cupo de trabajo pesado; libera SIEMPRE, incluso ante error
    o cancelación (cancelación segura vía try/finally, nunca un cupo huérfano).

    Lanza 503 sin ocupar cupo si la cola ya está llena (rechazo inmediato) o
    si se agota el tiempo de espera por un cupo libre.
    """
    global _active_jobs, _waiting_jobs, _total_rejected_queue_full, _total_rejected_timeout

    max_concurrent = max(1, int(getattr(settings, "max_concurrent_heavy_jobs", 4)))
    queue_max = max(0, int(getattr(settings, "heavy_job_queue_max", 12)))
    timeout_s = max(0.0, float(getattr(settings, "heavy_job_acquire_timeout_s", 30.0)))

    with _condition:
        if _waiting_jobs >= queue_max:
            _total_rejected_queue_full += 1
            raise _busy_response(
                "El servidor está procesando demasiados archivos grandes en este "
                "momento. Espera un momento y vuelve a intentarlo."
            )
        _waiting_jobs += 1
        try:
            deadline = time.monotonic() + timeout_s
            while _active_jobs >= max_concurrent:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    _total_rejected_timeout += 1
                    raise _busy_response(
                        "El servidor sigue ocupado con otros archivos grandes. "
                        "Intenta de nuevo en unos segundos."
                    )
                _condition.wait(timeout=remaining)
            _active_jobs += 1
        finally:
            _waiting_jobs -= 1

    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - started
        with _condition:
            _active_jobs -= 1
            _condition.notify()
        logger.info("[concurrency] %s terminó en %.3fs", label, elapsed)
