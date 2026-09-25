"""Reference-only jobs, atomically admitted and fenced in PostgreSQL."""

import hashlib
import json
from uuid import UUID

import httpx
from fastapi import HTTPException

from .config import Settings
from .storage import normalize_user_storage_path
from .version import ENGINE_VERSION

PUBLIC_FIELDS = frozenset({
    "job_id", "status", "phase", "attempt", "completed_phases", "total_phases",
    "current_sheet", "cancel_requested", "created_at", "updated_at", "result", "error",
})
KINDS = frozenset({"metrics", "standardize", "standardize_batch", "clean_batch", "clean_export",
                   "relationship_catalog", "relationship_dashboard"})


def durable_mode(settings: Settings) -> str:
    if settings.analysis_durable_mode == "auto":
        return "embedded" if settings.app_env.lower() == "production" else "off"
    return settings.analysis_durable_mode


def use_durable_source(settings: Settings, file, path: str | None, dataset_id: str | None) -> bool:
    return durable_mode(settings) != "off" and file is None and bool(path and dataset_id)


def public_job(job: dict | None) -> dict | None:
    return {key: value for key, value in job.items() if key in PUBLIC_FIELDS} if job else None


class DurableAnalysisRepository:
    def __init__(self, settings: Settings):
        self.settings = settings

    def call(self, action: str, user_id: str | None = None, job_id: str | None = None,
             payload: dict | None = None, token: str | None = None) -> dict | None:
        if not self.settings.supabase_url or not self.settings.supabase_service_role_key:
            raise HTTPException(503, "La cola persistente no esta configurada.")
        try:
            response = httpx.post(
                f"{self.settings.supabase_url.rstrip('/')}/rest/v1/rpc/analysis_queue",
                json={"p_action": action, "p_user_id": user_id, "p_job_id": job_id,
                      "p_payload": payload or {}, "p_token": token},
                headers={"Authorization": f"Bearer {self.settings.supabase_service_role_key}",
                         "apikey": self.settings.supabase_service_role_key}, timeout=15,
            )
            response.raise_for_status()
            result = response.json()
            if result is not None and not isinstance(result, dict):
                raise ValueError("Invalid queue response")
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(503, "No se pudo consultar la cola de procesamiento. Vuelve a intentar.") from exc
        if result and result.get("rejected"):
            code = int(result["rejected"])
            raise HTTPException(code, result.get("detail", "El trabajo no fue admitido."),
                                headers={"Retry-After": "10"} if code == 429 else None)
        return result

    def enqueue(self, user_id: str, dataset_id: str, path: str, kind: str, options: dict) -> dict:
        try:
            UUID(user_id)
            UUID(dataset_id)
        except ValueError as exc:
            raise HTTPException(422, "Identificador de dataset invalido.") from exc
        path = normalize_user_storage_path(path, user_id)
        if kind not in KINDS:
            raise ValueError("Unsupported job kind")
        payload = {"dataset_id": dataset_id, "source_path": path, "kind": kind,
                   "options": options, "engine_version": ENGINE_VERSION}
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
        if len(encoded.encode()) > 262144:
            raise HTTPException(413, "Las opciones del trabajo son demasiado grandes.")
        job_id = "dq_" + hashlib.sha256((user_id + encoded).encode()).hexdigest()[:32]
        result = self.call("enqueue", user_id, job_id, payload)
        if not result:
            raise HTTPException(503, "La cola no confirmo el trabajo. Vuelve a intentar.")
        if result.get("status") in {"failed", "cancelled"}:
            result = self.call("retry", user_id, job_id)
            if not result:
                raise HTTPException(503, "La cola no confirmo el reintento.")
        if durable_mode(self.settings) == "embedded":
            from .analysis_worker import WAKE
            WAKE.set()
        return public_job(result)

    def get(self, user_id: str, job_id: str) -> dict | None:
        return public_job(self.call("get", user_id, job_id))

    def cancel(self, user_id: str, job_id: str) -> dict | None:
        return public_job(self.call("cancel", user_id, job_id))

    def retry(self, user_id: str, job_id: str) -> dict | None:
        return public_job(self.call("retry", user_id, job_id))
