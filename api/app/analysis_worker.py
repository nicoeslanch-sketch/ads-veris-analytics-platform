"""One bounded consumer for the existing pipeline, embedded or standalone."""

import gc
import logging
import os
import signal
import threading
from contextlib import contextmanager

from fastapi import HTTPException

from .analysis_jobs import JobCancelled, _PROGRESS
from .config import Settings, get_settings
from .durable_analysis import DurableAnalysisRepository, durable_mode
from .processing_capacity import HEAVY_WORK_SLOT
from .version import ENGINE_VERSION

logger = logging.getLogger(__name__)
WAKE = threading.Event()


class LeaseLost(Exception):
    pass


@contextmanager
def job_lease(repository, job, stop: threading.Event):
    done = threading.Event()
    lost = threading.Event()
    cancelled = threading.Event()
    lock = threading.Lock()

    def check(action="heartbeat", payload=None):
        if stop.is_set() or lost.is_set():
            raise LeaseLost()
        with lock:
            current = repository.call(action, job["user_id"], job["job_id"], payload, job["lease_token"])
        if not current:
            lost.set()
            raise LeaseLost()
        if current.get("cancel_requested"):
            cancelled.set()
            raise JobCancelled()
        return current

    def heartbeat():
        while not done.wait(20):
            try:
                check()
            except JobCancelled:
                return
            except Exception:
                lost.set()
                return

    def progress(phase, completed, total, sheet=None):
        if cancelled.is_set():
            raise JobCancelled()
        check("progress", {"phase": phase, "completed_phases": completed,
                           "total_phases": total, "current_sheet": sheet})

    thread = threading.Thread(target=heartbeat, name="analysis-lease", daemon=True)
    thread.start()
    token = _PROGRESS.set(progress)
    try:
        check("source")
        yield check
    finally:
        _PROGRESS.reset(token)
        done.set()
        thread.join(timeout=16)


def execute_job(job: dict, settings: Settings) -> dict:
    # Import lazily so a standalone worker does not construct the ASGI app.
    from .routes import pipeline as p
    from .capabilities import Capability, require_capability_for_user
    from .storage import download_from_storage, normalize_user_storage_path

    kind = job["kind"]
    capabilities = {"metrics": Capability.VIEW_DASHBOARD, "standardize_batch": Capability.STANDARDIZE,
                    "clean_batch": Capability.CLEAN, "clean_export": Capability.DOWNLOAD_CLEAN_DATASET}
    if kind not in capabilities or job["engine_version"] != ENGINE_VERSION:
        raise HTTPException(409, "El trabajo corresponde a otra version del motor. Vuelve a crearlo.")
    user_id, dataset_id, opts = job["user_id"], job["dataset_id"], job["options"]
    # Subscription and ownership may have changed while waiting in the queue.
    require_capability_for_user(user_id, capabilities[kind], settings)
    path = normalize_user_storage_path(job["source_path"], user_id)
    content = download_from_storage(path)
    filename = p._display_filename(os.path.basename(path))
    p.report_job_progress("opening", 0, 1)
    if kind == "standardize_batch":
        return p._standardize_batch_sync(filename, content, opts["sheets"], dataset_id,
                                         user_id, opts["revision"], opts.get("restore_state"))
    if kind == "clean_batch":
        return p._clean_batch_sync(filename, content, opts["manifest"], dataset_id,
                                  user_id, opts["revision"], opts.get("restore_state"))
    if kind == "metrics":
        if opts.get("manifest") is not None:
            return p._metrics_multi_cached_sync(filename, content, opts["manifest"], opts["analysis_scope"],
                                                opts.get("date_from"), opts.get("date_to"), dataset_id,
                                                user_id, opts.get("business_filters"))
        return p._metrics_sync(filename, content, opts.get("mapping"), opts.get("date_from"),
                               opts.get("date_to"), opts.get("sheet"), opts.get("eliminar_duplicados", False),
                               opts.get("rules", {}), opts.get("scope"), dataset_id, opts.get("revision"),
                               opts.get("business_filters"), user_id)
    manifest, fmt, scope = opts["manifest"], opts["format"], opts.get("analysis_scope")
    p._prune_caches_for_export(content, manifest, dataset_id)
    _payload, out_name, _media_type = p._clean_download_book_sync(
        filename, content, manifest, fmt, scope, dataset_id, user_id,
    )
    # A separate process cannot promise that an in-memory export is downloadable.
    # Verify durable metadata before publishing readiness. Quota failures remain
    # explicit; synchronous download can still compute the same clean output.
    p.report_job_progress("saving", 0, 1)
    identity = p._export_cache_identity(content, manifest, fmt, scope)
    base = p._export_cache_storage_path(user_id, dataset_id, fmt)
    metadata = p._unpack_export_cache_metadata(p.download_export_cache(f"{base}.json"), identity)
    if metadata is None:
        raise HTTPException(503, "La exportacion se calculo, pero no pudo guardarse. Revisa tu cuota y reintenta la descarga.")
    return {"ready": True, "filename": out_name, "format": fmt}


class AnalysisWorker:
    def __init__(self, settings: Settings, repository=None, execute=None):
        self.settings = settings
        self.repository = repository or DurableAnalysisRepository(settings)
        self.execute = execute or execute_job
        self.stop = threading.Event()

    def run_once(self) -> bool:
        # Claim only when this process can actually start work; avoid expiring
        # a lease while waiting behind a synchronous/legacy calculation.
        if not HEAVY_WORK_SLOT.acquire(blocking=False):
            return False
        try:
            job = self.repository.call("claim", payload={"engine_version": ENGINE_VERSION})
            if not job:
                return False
            try:
                with job_lease(self.repository, job, self.stop) as check:
                    result = self.execute(job, self.settings)
                    check("source")
                    terminal = {"status": "completed", "result": result}
            except LeaseLost:
                # Do not publish a late error over another worker's attempt.
                return True
            except JobCancelled:
                terminal = {"status": "cancelled"}
            except HTTPException as exc:
                terminal = {"status": "failed", "error": str(exc.detail)[:500]}
            except Exception:
                logger.exception("durable_analysis_failed job_id=%s", job["job_id"])
                terminal = {"status": "failed", "error": "El proceso no pudo completarse con los datos disponibles."}
            self.repository.call("finish", job["user_id"], job["job_id"], terminal, job["lease_token"])
            return True
        finally:
            HEAVY_WORK_SLOT.release()

    def run(self):
        delay = self.settings.analysis_worker_poll_seconds
        while not self.stop.is_set():
            try:
                worked = self.run_once()
            except Exception:
                logger.exception("durable_analysis_queue_unavailable")
                worked = False
            if worked:
                gc.collect()
                delay = self.settings.analysis_worker_poll_seconds
                continue
            WAKE.wait(delay)
            WAKE.clear()
            delay = min(60, delay * 1.5)

    def shutdown(self):
        self.stop.set()
        WAKE.set()


def main():
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key or settings.dev_auth_bypass:
        raise RuntimeError("Worker requires Supabase and authenticated operation.")
    if durable_mode(settings) not in {"embedded", "external"}:
        raise RuntimeError("Set ANALYSIS_DURABLE_MODE=external for the standalone worker.")
    worker = AnalysisWorker(settings)
    signal.signal(signal.SIGTERM, lambda *_: worker.shutdown())
    signal.signal(signal.SIGINT, lambda *_: worker.shutdown())
    worker.run()


if __name__ == "__main__":
    main()
