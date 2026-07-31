"""API aislada de consolidación; todos los endpoints exigen JWT y ownership."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from ..auth import AuthenticatedUser, get_current_user
from ..config import Settings, get_settings
from ..storage import create_export_cache_signed_url
from ..version import ENGINE_VERSION
from .models import SourceAssignment, SourceRole
from .repository import repository_for
from .service import idempotency_key, owned_dataset_metadata, require_consolidation_access
from .target_schema import TARGET_COLUMNS, resolve_target_columns

router = APIRouter(prefix="/consolidation", tags=["consolidation"])


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    cohort: int = Field(default=2026, ge=2000, le=2100)
    include_historical_output: bool = False
    target_columns: list[str] | None = None
    aliases: dict[str, str] = Field(default_factory=dict)
    precedence: dict[str, list[str]] = Field(default_factory=dict)


class SourcesRequest(BaseModel):
    sources: list[SourceAssignment]


class ActivateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)


def _access(user: AuthenticatedUser, settings: Settings) -> None:
    require_consolidation_access(user, settings)


def _project_or_404(project_id: UUID, user: AuthenticatedUser, settings: Settings) -> tuple[Any, dict[str, Any]]:
    repo = repository_for(settings)
    project = repo.get_project(str(project_id), user.id)
    if not project:
        raise HTTPException(404, "Proyecto de consolidación no encontrado.")
    return repo, project


@router.post("/projects")
async def create_project(
    body: CreateProjectRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _access(user, settings)
    target = resolve_target_columns(body.target_columns)
    config = body.model_dump()
    config["target_columns"] = list(target)
    config_hash = hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    repo = repository_for(settings)
    return await run_in_threadpool(repo.create_project, user.id, {"name": body.name, "config": config, "config_hash": config_hash, "engine_version": ENGINE_VERSION})


@router.get("/projects/{project_id}")
async def get_project(
    project_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _access(user, settings)
    _repo, project = await run_in_threadpool(_project_or_404, project_id, user, settings)
    return project


@router.put("/projects/{project_id}/sources")
async def set_sources(
    project_id: UUID,
    body: SourcesRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _access(user, settings)
    repo, _project = await run_in_threadpool(_project_or_404, project_id, user, settings)
    roles = [source.role for source in body.sources]
    if len(roles) != len(set(roles)):
        raise HTTPException(422, "Cada rol solo puede asignarse una vez.")
    ids = [str(source.dataset_id) for source in body.sources]
    metadata = await run_in_threadpool(owned_dataset_metadata, ids, user.id, settings)
    sources = [
        {
            "dataset_id": str(source.dataset_id), "role": source.role.value,
            "required": source.required, "selected_sheet": source.selected_sheet,
            "profile": {"name": metadata[str(source.dataset_id)]["name"], "storage_path": metadata[str(source.dataset_id)]["storage_path"]},
            "status": "draft",
        }
        for source in body.sources
    ]
    return await run_in_threadpool(repo.replace_sources, str(project_id), user.id, sources)


@router.post("/projects/{project_id}/validate")
async def validate_project(
    project_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _access(user, settings)
    _repo, project = await run_in_threadpool(_project_or_404, project_id, user, settings)
    roles = {source["role"] for source in project.get("sources", [])}
    blocking = [] if SourceRole.MATRICULA.value in roles else ["matricula_missing"]
    warnings = [] if SourceRole.ARCHIVO_B.value in roles else ["archivo_b_missing"]
    return {"status": "blocked" if blocking else "valid_with_warnings" if warnings else "valid", "blocking": blocking, "warnings": warnings, "source_count": len(roles), "target_columns": len(project.get("config", {}).get("target_columns", TARGET_COLUMNS))}


async def _enqueue(project_id: UUID, user: AuthenticatedUser, settings: Settings, purpose: str) -> dict[str, Any]:
    repo, project = await run_in_threadpool(_project_or_404, project_id, user, settings)
    sources = project.get("sources", [])
    if not any(source["role"] == SourceRole.MATRICULA.value for source in sources):
        raise HTTPException(422, "Asigna Matrícula antes de ejecutar.")
    key = idempotency_key(str(project_id), project["config_hash"], sources + [{"role": "purpose", "dataset_id": purpose}])
    return await run_in_threadpool(repo.enqueue_run, project, key)


@router.post("/projects/{project_id}/preview")
async def preview_project(project_id: UUID, user: AuthenticatedUser = Depends(get_current_user), settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    _access(user, settings)
    return await _enqueue(project_id, user, settings, "preview")


@router.post("/projects/{project_id}/runs")
async def run_project(project_id: UUID, user: AuthenticatedUser = Depends(get_current_user), settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    _access(user, settings)
    return await _enqueue(project_id, user, settings, "full")


@router.get("/runs/{run_id}")
async def get_run(run_id: UUID, user: AuthenticatedUser = Depends(get_current_user), settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    _access(user, settings)
    repo = repository_for(settings)
    run = await run_in_threadpool(repo.get_run, str(run_id), user.id)
    if not run:
        raise HTTPException(404, "Ejecución no encontrada.")
    return run


@router.get("/runs/{run_id}/report")
async def get_report(run_id: UUID, user: AuthenticatedUser = Depends(get_current_user), settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    run = await get_run(run_id, user, settings)
    return {"run_id": str(run_id), "status": run["status"], "report": run.get("report", {})}


@router.get("/runs/{run_id}/export/{artifact_kind}")
async def export_artifact(artifact_kind: str, run_id: UUID, user: AuthenticatedUser = Depends(get_current_user), settings: Settings = Depends(get_settings)) -> dict[str, str]:
    run = await get_run(run_id, user, settings)
    artifact = next((item for item in run.get("artifacts", []) if item["kind"] == artifact_kind), None)
    if not artifact:
        raise HTTPException(404, "Artefacto no encontrado.")
    if not settings.supabase_url:
        return {"local_path": artifact["storage_path"]}
    filename = artifact["storage_path"].rsplit("/", 1)[-1]
    url = await run_in_threadpool(create_export_cache_signed_url, artifact["storage_path"], filename)
    return {"url": url}


@router.post("/runs/{run_id}/activate")
async def activate_result(run_id: UUID, body: ActivateRequest, user: AuthenticatedUser = Depends(get_current_user), settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    run = await get_run(run_id, user, settings)
    if run["status"] not in {"partial", "certified", "valid_with_warnings"}:
        raise HTTPException(409, "La ejecución todavía no tiene un resultado utilizable.")
    annual = next((item for item in run.get("artifacts", []) if item["kind"] == "annual"), None)
    if not annual:
        raise HTTPException(409, "La ejecución no tiene base anual.")
    if not settings.supabase_url:
        return {"status": "simulated", "run_id": str(run_id), "name": body.name}
    headers = {"Authorization": f"Bearer {settings.supabase_service_role_key}", "apikey": settings.supabase_service_role_key, "Prefer": "return=representation"}
    try:
        response = await run_in_threadpool(
            lambda: httpx.post(
                f"{settings.supabase_url.rstrip('/')}/rest/v1/datasets", headers=headers,
                json={"user_id": user.id, "name": body.name, "source": "consolidation_derived", "storage_path": annual["storage_path"], "rows": run.get("report", {}).get("row_counts", {}).get("annual"), "columns": len(run.get("report", {}).get("target_columns", TARGET_COLUMNS)), "status": "cargado"}, timeout=20,
            )
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(502, "No se pudo registrar el dataset derivado.") from exc
    rows = response.json()
    return {"status": "activated", "dataset": rows[0]}
