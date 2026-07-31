"""Persistencia intercambiable: Supabase en producción y repositorio simulado local."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import httpx

from ..config import Settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryConsolidationRepository:
    def __init__(self) -> None:
        self.projects: dict[str, dict[str, Any]] = {}
        self.runs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create_project(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        project = {"id": str(uuid4()), "user_id": user_id, "status": "draft", "created_at": _now(), **payload}
        with self._lock:
            self.projects[project["id"]] = project
        return dict(project)

    def get_project(self, project_id: str, user_id: str) -> dict[str, Any] | None:
        project = self.projects.get(project_id)
        return dict(project) if project and project["user_id"] == user_id else None

    def replace_sources(self, project_id: str, user_id: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
        with self._lock:
            project = self.projects.get(project_id)
            if not project or project["user_id"] != user_id:
                raise KeyError(project_id)
            project["sources"] = sources
            project["updated_at"] = _now()
            return dict(project)

    def enqueue_run(self, project: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        with self._lock:
            existing = next((run for run in self.runs.values() if run["user_id"] == project["user_id"] and run["idempotency_key"] == idempotency_key), None)
            if existing:
                return dict(existing)
            run = {
                "id": str(uuid4()), "project_id": project["id"], "user_id": project["user_id"],
                "status": "queued", "idempotency_key": idempotency_key,
                "config_hash": project["config_hash"], "engine_version": project["engine_version"],
                "report": {}, "created_at": _now(),
            }
            self.runs[run["id"]] = run
            return dict(run)

    def get_run(self, run_id: str, user_id: str) -> dict[str, Any] | None:
        run = self.runs.get(run_id)
        if not run or run["user_id"] != user_id:
            return None
        result = dict(run)
        reused = self.runs.get(str(run.get("reused_run_id"))) if run.get("reused_run_id") else None
        if reused:
            result["artifacts"] = reused.get("artifacts", [])
        return result

    def claim_next(self) -> dict[str, Any] | None:
        with self._lock:
            queued = sorted((run for run in self.runs.values() if run["status"] == "queued"), key=lambda item: item["created_at"])
            if not queued:
                return None
            run = queued[0]
            run["status"] = "running"
            run["started_at"] = _now()
            return dict(run)

    def complete_run(self, run_id: str, *, status: str, input_hash: str, report: dict[str, Any], artifacts: list[dict[str, Any]], reused_run_id: str | None = None) -> None:
        with self._lock:
            run = self.runs[run_id]
            run.update({"status": status, "input_hash": input_hash, "report": report, "artifacts": artifacts, "reused_run_id": reused_run_id, "completed_at": _now()})

    def fail_run(self, run_id: str, code: str, message: str) -> None:
        with self._lock:
            self.runs[run_id].update({"status": "failed", "error_code": code, "error_message": message[:500], "completed_at": _now()})

    def find_completed(self, user_id: str, input_hash: str, config_hash: str) -> dict[str, Any] | None:
        for run in self.runs.values():
            if run["user_id"] == user_id and run.get("input_hash") == input_hash and run.get("config_hash") == config_hash and run["status"] in {"partial", "certified", "valid_with_warnings"}:
                return dict(run)
        return None


class SupabaseConsolidationRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.supabase_service_role_key}", "apikey": self.settings.supabase_service_role_key, "Prefer": "return=representation"}

    def _url(self, table: str) -> str:
        return f"{self.settings.supabase_url.rstrip('/')}/rest/v1/{table}"

    def _rows(self, response: httpx.Response) -> list[dict[str, Any]]:
        response.raise_for_status()
        value = response.json()
        return value if isinstance(value, list) else []

    def create_project(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        rows = self._rows(httpx.post(self._url("consolidation_projects"), headers=self.headers, json={"user_id": user_id, **payload}, timeout=20))
        return rows[0]

    def get_project(self, project_id: str, user_id: str) -> dict[str, Any] | None:
        rows = self._rows(httpx.get(self._url("consolidation_projects"), headers=self.headers, params={"id": f"eq.{project_id}", "user_id": f"eq.{user_id}", "select": "*"}, timeout=20))
        if not rows:
            return None
        project = rows[0]
        sources = self._rows(httpx.get(self._url("consolidation_project_sources"), headers=self.headers, params={"project_id": f"eq.{project_id}", "user_id": f"eq.{user_id}", "select": "*"}, timeout=20))
        project["sources"] = sources
        return project

    def replace_sources(self, project_id: str, user_id: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
        response = httpx.delete(self._url("consolidation_project_sources"), headers=self.headers, params={"project_id": f"eq.{project_id}", "user_id": f"eq.{user_id}"}, timeout=20)
        response.raise_for_status()
        if sources:
            rows = [{"project_id": project_id, "user_id": user_id, **source} for source in sources]
            self._rows(httpx.post(self._url("consolidation_project_sources"), headers=self.headers, json=rows, timeout=20))
        project = self.get_project(project_id, user_id)
        if not project:
            raise KeyError(project_id)
        return project

    def enqueue_run(self, project: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        payload = {"project_id": project["id"], "user_id": project["user_id"], "status": "queued", "idempotency_key": idempotency_key, "config_hash": project["config_hash"], "engine_version": project["engine_version"]}
        response = httpx.post(self._url("consolidation_runs"), headers={**self.headers, "Prefer": "resolution=ignore-duplicates,return=representation"}, json=payload, timeout=20)
        rows = self._rows(response)
        if rows:
            return rows[0]
        existing = self._rows(httpx.get(self._url("consolidation_runs"), headers=self.headers, params={"user_id": f"eq.{project['user_id']}", "idempotency_key": f"eq.{idempotency_key}", "select": "*"}, timeout=20))
        return existing[0]

    def get_run(self, run_id: str, user_id: str) -> dict[str, Any] | None:
        rows = self._rows(httpx.get(self._url("consolidation_runs"), headers=self.headers, params={"id": f"eq.{run_id}", "user_id": f"eq.{user_id}", "select": "*"}, timeout=20))
        if not rows:
            return None
        run = rows[0]
        artifact_run_id = str(run.get("reused_run_id") or run_id)
        run["artifacts"] = self._rows(httpx.get(self._url("consolidation_artifacts"), headers=self.headers, params={"run_id": f"eq.{artifact_run_id}", "user_id": f"eq.{user_id}", "select": "*"}, timeout=20))
        return run

    def claim_next(self) -> dict[str, Any] | None:
        rows = self._rows(httpx.get(self._url("consolidation_runs"), headers=self.headers, params={"status": "eq.queued", "order": "created_at.asc", "limit": "1", "select": "*"}, timeout=20))
        if not rows:
            return None
        run = rows[0]
        claimed = self._rows(httpx.patch(self._url("consolidation_runs"), headers=self.headers, params={"id": f"eq.{run['id']}", "status": "eq.queued"}, json={"status": "running", "started_at": _now()}, timeout=20))
        return claimed[0] if claimed else None

    def complete_run(self, run_id: str, *, status: str, input_hash: str, report: dict[str, Any], artifacts: list[dict[str, Any]], reused_run_id: str | None = None) -> None:
        response = httpx.patch(self._url("consolidation_runs"), headers=self.headers, params={"id": f"eq.{run_id}"}, json={"status": status, "input_hash": input_hash, "report": report, "reused_run_id": reused_run_id, "completed_at": _now()}, timeout=20)
        response.raise_for_status()
        if artifacts:
            self._rows(httpx.post(self._url("consolidation_artifacts"), headers=self.headers, json=artifacts, timeout=20))

    def fail_run(self, run_id: str, code: str, message: str) -> None:
        response = httpx.patch(self._url("consolidation_runs"), headers=self.headers, params={"id": f"eq.{run_id}"}, json={"status": "failed", "error_code": code, "error_message": message[:500], "completed_at": _now()}, timeout=20)
        response.raise_for_status()

    def find_completed(self, user_id: str, input_hash: str, config_hash: str) -> dict[str, Any] | None:
        rows = self._rows(httpx.get(self._url("consolidation_runs"), headers=self.headers, params={"user_id": f"eq.{user_id}", "input_hash": f"eq.{input_hash}", "config_hash": f"eq.{config_hash}", "status": "in.(partial,certified,valid_with_warnings)", "order": "completed_at.desc", "limit": "1", "select": "*"}, timeout=20))
        return rows[0] if rows else None


MEMORY_REPOSITORY = MemoryConsolidationRepository()


def repository_for(settings: Settings):
    if settings.supabase_url and settings.supabase_service_role_key:
        return SupabaseConsolidationRepository(settings)
    return MEMORY_REPOSITORY
