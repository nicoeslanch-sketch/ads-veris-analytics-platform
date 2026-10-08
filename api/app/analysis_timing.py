"""Bounded per-execution timings; never include workbook or account metadata."""

import json
import logging
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from time import perf_counter
from uuid import uuid4

logger = logging.getLogger("uvicorn.error")
_ACTIVE: ContextVar[dict | None] = ContextVar("analysis_timing", default=None)
_OPERATIONS = frozenset({"metrics", "standardize", "standardize_batch", "clean_batch",
                         "clean_export", "relationship_catalog", "relationship_dashboard"})
_STAGES = frozenset({"authorization", "source_download", "analysis_cache", "prepare_sheets",
                     "restore_clean_sheet", "compute_metrics", "lease_rpc"})


@contextmanager
def analysis_timing(operation: str):
    stages = {}
    token = _ACTIVE.set(stages)
    started = perf_counter()
    outcome = "raised"
    try:
        yield
        outcome = "returned"
    finally:
        _ACTIVE.reset(token)
        # Timing is diagnostic only: logging failure cannot fail or retry work.
        with suppress(Exception):
            logger.info(json.dumps({
                "event": "analysis_timing",
                "trace_id": uuid4().hex,
                "operation": operation if operation in _OPERATIONS else "other",
                "outcome": outcome,
                "duration_ms": round((perf_counter() - started) * 1000, 1),
                "stages": {
                    name: {"calls": value[0], "duration_ms": round(value[1] * 1000, 1)}
                    for name, value in stages.items()
                },
            }, separators=(",", ":")))


@contextmanager
def analysis_stage(name: str):
    stages = _ACTIVE.get()
    if stages is None or name not in _STAGES:
        yield
        return
    started = perf_counter()
    try:
        yield
    finally:
        count, seconds = stages.get(name, (0, 0.0))
        stages[name] = (count + 1, seconds + perf_counter() - started)
