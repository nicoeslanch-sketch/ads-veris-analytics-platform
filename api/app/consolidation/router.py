"""API aislada de consolidación; todos los endpoints exigen JWT y ownership."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from ..auth import AuthenticatedUser, get_current_user
from ..config import Settings, get_settings
from ..storage import create_export_cache_signed_url
from ..version import ENGINE_VERSION
from .ingestion import storage_source_file, tabular_headers
from .models import SourceAssignment, SourceRole
from .repository import repository_for
from .service import idempotency_key, owned_dataset_metadata, require_consolidation_access
from .target_schema import TARGET_COLUMNS, resolve_target_columns

router = APIRouter(prefix="/consolidation", tags=["consolidation"])


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    template: Literal["general", "demre_2026"] = "general"
    cohort: int = Field(default=2026, ge=2000, le=2100)
    period_label: str | None = Field(default=None, max_length=80)
    include_historical_output: bool = False
    target_columns: list[str] | None = None
    aliases: dict[str, str] = Field(default_factory=dict)
    precedence: dict[str, list[str]] = Field(default_factory=dict)
    cohort_id_strategy: str = "cohort_and_id"
    mapping_manifest: dict[str, Any] | None = None


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


@router.get("/status")
async def consolidation_status(
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Permite que la interfaz detecte flags incoherentes antes de crear."""
    if not settings.consolidation_enabled:
        return {"available": False, "reason": "backend_disabled", "admin_only": settings.consolidation_admin_only}
    try:
        require_consolidation_access(user, settings)
    except HTTPException as exc:
        return {"available": False, "reason": "admin_required" if exc.status_code == 403 else "access_check_failed", "admin_only": settings.consolidation_admin_only}
    return {"available": True, "reason": None, "admin_only": settings.consolidation_admin_only}


def _inspect_owned_dataset(dataset_id: UUID, user: AuthenticatedUser, settings: Settings) -> dict[str, Any]:
    metadata = owned_dataset_metadata([str(dataset_id)], user.id, settings)[str(dataset_id)]
    with storage_source_file(metadata["storage_path"], user.id, settings) as (path, digest):
        sheets = tabular_headers(path)
    return {
        "dataset_id": str(dataset_id), "name": metadata["name"], "sha256": digest,
        "sheets": [{"name": name, "columns": columns} for name, columns in sheets.items()],
    }


@router.get("/datasets/{dataset_id}/inspect")
async def inspect_dataset(
    dataset_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _access(user, settings)
    try:
        return await run_in_threadpool(_inspect_owned_dataset, dataset_id, user, settings)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/projects")
async def create_project(
    body: CreateProjectRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _access(user, settings)
    config = body.model_dump()
    if body.template == "demre_2026":
        config["target_columns"] = list(resolve_target_columns(body.target_columns))
        config["mapping_version"] = "demre-2026-v1"
    else:
        if body.target_columns:
            raise HTTPException(422, "El modo general construye las columnas desde los archivos; no usa una plantilla DEMRE.")
        config["target_columns"] = []
        config["mapping_version"] = "general-v1"
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
            "profile": {
                "name": metadata[str(source.dataset_id)]["name"],
                "storage_path": metadata[str(source.dataset_id)]["storage_path"],
                "configuration": {
                    "label": source.label,
                    "primary_key": source.primary_key,
                    "source_key": source.source_key,
                    "target_column": source.target_column,
                    "value_column": source.value_column,
                    "output_column": source.output_column,
                    "prefix": source.prefix,
                    "include_columns": source.include_columns,
                    "selected_sheet": source.selected_sheet,
                },
            },
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
    config = project.get("config", {})
    roles = {source["role"] for source in project.get("sources", [])}
    if config.get("template") == "general":
        blocking: list[str] = []
        primary = next((source for source in project.get("sources", []) if source["role"] == SourceRole.PRIMARY.value), None)
        if not primary:
            blocking.append("Selecciona un archivo principal.")
        elif not primary.get("profile", {}).get("configuration", {}).get("primary_key"):
            blocking.append("Selecciona la columna clave del archivo principal.")
        for source in project.get("sources", []):
            source_config = source.get("profile", {}).get("configuration", {})
            if source["role"].startswith("supplement_") and not source_config.get("source_key"):
                blocking.append(f"Falta la clave de {source_config.get('label') or source['role']}.")
            if source["role"].startswith("equivalence_") and not all(source_config.get(key) for key in ("target_column", "source_key", "value_column")):
                blocking.append(f"Falta configurar la equivalencia {source_config.get('label') or source['role']}.")
        return {
            "status": "blocked" if blocking else "valid", "blocking": blocking, "warnings": [],
            "source_count": len(roles), "target_columns": 0,
        }
    blocking = [] if SourceRole.MATRICULA.value in roles else ["Falta Matrícula (archivo ancla)."]
    warnings = [] if SourceRole.ARCHIVO_B.value in roles else ["Archivo B no fue asignado."]
    return {"status": "blocked" if blocking else "valid_with_warnings" if warnings else "valid", "blocking": blocking, "warnings": warnings, "source_count": len(roles), "target_columns": len(config.get("target_columns", TARGET_COLUMNS))}


async def _enqueue(project_id: UUID, user: AuthenticatedUser, settings: Settings, purpose: str) -> dict[str, Any]:
    repo, project = await run_in_threadpool(_project_or_404, project_id, user, settings)
    sources = project.get("sources", [])
    required_role = SourceRole.PRIMARY if project.get("config", {}).get("template") == "general" else SourceRole.MATRICULA
    if not any(source["role"] == required_role.value for source in sources):
        message = "Selecciona un archivo principal antes de ejecutar." if required_role is SourceRole.PRIMARY else "Asigna Matrícula antes de ejecutar."
        raise HTTPException(422, message)
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
