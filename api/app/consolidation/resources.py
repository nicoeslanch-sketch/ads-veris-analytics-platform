"""Presupuesto de recursos y telemetría agregada exclusiva de consolidación."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator
from uuid import uuid4

import psutil

try:
    import resource
except ImportError:  # pragma: no cover - resource no existe en Windows
    resource = None  # type: ignore[assignment]

from ..config import Settings

MB = 1024 * 1024


class ConsolidationResourceError(RuntimeError):
    """Fallo controlado y auditable del presupuesto exclusivo del dominio."""

    def __init__(self, code: str, message: str, metrics: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.metrics = metrics or {}


@dataclass
class StageObservation:
    stage: str
    attempts: int = 0
    rss_before_bytes: int = 0
    rss_after_bytes: int = 0
    peak_rss_bytes: int = 0
    duration_ms: int = 0
    rows_read: int = 0
    rows_generated: int = 0
    chunks: int = 0
    temporary_bytes: int = 0
    artifact_bytes: int = 0
    source_bytes: int = 0

    def as_dict(self) -> dict[str, int | str]:
        return {
            "stage": self.stage,
            "attempts": self.attempts,
            "rss_before_bytes": self.rss_before_bytes,
            "rss_after_bytes": self.rss_after_bytes,
            "peak_rss_bytes": self.peak_rss_bytes,
            "duration_ms": self.duration_ms,
            "rows_read": self.rows_read,
            "rows_generated": self.rows_generated,
            "chunks": self.chunks,
            "temporary_bytes": self.temporary_bytes,
            "artifact_bytes": self.artifact_bytes,
            "source_bytes": self.source_bytes,
        }


@dataclass
class StageUpdate:
    rows_read: int = 0
    rows_generated: int = 0
    chunks: int = 0
    temporary_bytes: int = 0
    artifact_bytes: int = 0
    source_bytes: int = 0

    def add(
        self,
        *,
        rows_read: int = 0,
        rows_generated: int = 0,
        chunks: int = 0,
        temporary_bytes: int = 0,
        artifact_bytes: int = 0,
        source_bytes: int = 0,
    ) -> None:
        self.rows_read += max(0, int(rows_read))
        self.rows_generated += max(0, int(rows_generated))
        self.chunks += max(0, int(chunks))
        self.temporary_bytes += max(0, int(temporary_bytes))
        self.artifact_bytes += max(0, int(artifact_bytes))
        self.source_bytes += max(0, int(source_bytes))


class ResourceMonitor:
    """Mide el proceso completo; el SO aporta el high-water mark cuando existe."""

    def __init__(
        self,
        settings: Settings,
        *,
        sample_interval_seconds: float = 0.05,
        on_stage: Callable[[str, str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.settings = settings
        try:
            self.process: psutil.Process | None = psutil.Process(os.getpid())
        except (psutil.Error, OSError):
            # Algunos runners aislados no montan /proc. El worker no debe
            # abortar antes de procesar: getrusage conserva un peak RSS
            # conservador aunque no pueda informar liberacion de memoria.
            self.process = None
        self.memory_backend = "psutil" if self.process is not None else "rusage"
        self.sample_interval_seconds = max(0.01, sample_interval_seconds)
        self.initial_rss_bytes = self.current_rss_bytes()
        self.final_rss_bytes = self.initial_rss_bytes
        self.peak_rss_bytes = max(self.initial_rss_bytes, self._os_peak_rss_bytes())
        self.started = time.perf_counter()
        self.on_stage = on_stage
        self.stages: dict[str, StageObservation] = {}
        self.soft_limit_exceeded = False
        self._active_observations: list[StageObservation] = []
        self._observations_lock = threading.Lock()
        self._stop = threading.Event()
        self._sampler = threading.Thread(target=self._sample_loop, name="consolidation-rss-sampler", daemon=True)
        self._sampler.start()

    def current_rss_bytes(self) -> int:
        if self.process is not None:
            try:
                return int(self.process.memory_info().rss)
            except (psutil.Error, OSError):
                self.process = None
                self.memory_backend = "rusage"
        return self._rusage_peak_rss_bytes()

    def _rusage_peak_rss_bytes(self) -> int:
        if resource is None:
            return 0
        peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        # Linux y los BSD reportan KiB; macOS reporta bytes.
        return peak if sys.platform == "darwin" else peak * 1024

    def _os_peak_rss_bytes(self) -> int:
        peak = self._rusage_peak_rss_bytes()
        if self.process is None:
            return peak
        try:
            info = self.process.memory_info()
        except (psutil.Error, OSError):
            return peak
        return max(peak, int(getattr(info, "peak_wset", 0) or 0))

    def _observe(self) -> int:
        rss = self.current_rss_bytes()
        self.peak_rss_bytes = max(self.peak_rss_bytes, rss, self._os_peak_rss_bytes())
        with self._observations_lock:
            for observation in self._active_observations:
                observation.peak_rss_bytes = max(observation.peak_rss_bytes, rss)
        self.final_rss_bytes = rss
        return rss

    def _sample_loop(self) -> None:
        while not self._stop.wait(self.sample_interval_seconds):
            try:
                self._observe()
            except (psutil.Error, OSError):
                return

    def checkpoint(self, stage: str) -> int:
        rss = self._observe()
        soft = self.settings.consolidation_memory_soft_limit_mb * MB
        hard = self.settings.consolidation_memory_hard_limit_mb * MB
        if rss > soft:
            self.soft_limit_exceeded = True
        if rss > hard:
            raise ConsolidationResourceError(
                "memory_hard_limit_exceeded",
                f"Consolidación superó su límite duro durante {stage}.",
                self.snapshot(),
            )
        return rss

    @contextmanager
    def stage(self, name: str) -> Iterator[StageUpdate]:
        before = self.checkpoint(name)
        started = time.perf_counter()
        update = StageUpdate()
        observation = self.stages.setdefault(name, StageObservation(stage=name))
        if observation.attempts == 0:
            observation.rss_before_bytes = before
        observation.attempts += 1
        observation.peak_rss_bytes = max(observation.peak_rss_bytes, before)
        with self._observations_lock:
            self._active_observations.append(observation)
        if self.on_stage:
            try:
                self.on_stage(name, "started", observation.as_dict())
            except Exception:
                pass
        outcome = "completed"
        try:
            yield update
        except BaseException:
            outcome = "failed"
            raise
        finally:
            after = self._observe()
            with self._observations_lock:
                if observation in self._active_observations:
                    self._active_observations.remove(observation)
            observation.rss_after_bytes = after
            observation.peak_rss_bytes = max(observation.peak_rss_bytes, before, after)
            observation.duration_ms += int((time.perf_counter() - started) * 1000)
            observation.rows_read += update.rows_read
            observation.rows_generated += update.rows_generated
            observation.chunks += update.chunks
            observation.temporary_bytes += update.temporary_bytes
            observation.artifact_bytes += update.artifact_bytes
            observation.source_bytes += update.source_bytes
            if self.on_stage:
                try:
                    self.on_stage(name, outcome, observation.as_dict())
                except Exception:
                    pass
            self.checkpoint(name)

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        self._sampler.join(timeout=1)
        self._observe()
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        return {
            "initial_rss_bytes": self.initial_rss_bytes,
            "final_rss_bytes": self.final_rss_bytes,
            "peak_rss_bytes": max(self.peak_rss_bytes, self._os_peak_rss_bytes()),
            "memory_released_bytes": max(0, self.peak_rss_bytes - self.final_rss_bytes),
            "soft_limit_bytes": self.settings.consolidation_memory_soft_limit_mb * MB,
            "hard_limit_bytes": self.settings.consolidation_memory_hard_limit_mb * MB,
            "memory_backend": self.memory_backend,
            "soft_limit_exceeded": self.soft_limit_exceeded,
            "duration_ms": int((time.perf_counter() - self.started) * 1000),
            "stages": [stage.as_dict() for stage in self.stages.values()],
        }


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def required_temp_bytes(settings: Settings, source_bytes: int = 0) -> int:
    configured = settings.consolidation_temp_disk_min_mb * MB
    # Descargas + XLSX derivados + margen conservador. Nunca reduce el mínimo.
    return max(configured, max(0, source_bytes) * 3)


def ensure_temp_capacity(base: Path, settings: Settings, *, source_bytes: int = 0) -> dict[str, int]:
    base.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(base)
    required = required_temp_bytes(settings, source_bytes)
    if usage.free < required:
        raise ConsolidationResourceError(
            "temporary_disk_insufficient",
            "No existe espacio temporal suficiente para ejecutar la consolidación.",
            {"temporary_free_bytes": usage.free, "temporary_required_bytes": required},
        )
    return {"temporary_free_bytes": usage.free, "temporary_required_bytes": required}


@contextmanager
def isolated_run_directory(
    settings: Settings,
    *,
    run_id: str | None = None,
    source_bytes: int = 0,
) -> Iterator[Path]:
    base = Path(settings.consolidation_temp_dir).expanduser() if settings.consolidation_temp_dir.strip() else Path(tempfile.gettempdir())
    ensure_temp_capacity(base, settings, source_bytes=source_bytes)
    identifier = run_id or str(uuid4())
    path = Path(tempfile.mkdtemp(prefix=f"ads-consolidation-{identifier}-", dir=base))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
