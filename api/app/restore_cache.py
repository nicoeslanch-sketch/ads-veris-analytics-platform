"""Persistent, versioned snapshots for fast dataset restoration.

Snapshots contain only the public pipeline responses, never the full dataframe.
They are written with the service-role key and read through the API so clients
cannot forge analytical results in Supabase.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx
from fastapi import HTTPException, status

from .config import Settings, get_settings
from .engine.clean import DEFAULT_RULES
from .version import ENGINE_VERSION


# Fase 16 — v3: las revisiones se reservan en PostgreSQL al RECIBIR la
# petición y cada hoja vive en una fila separada. Ya no existe el límite
# arbitrario de 512 KiB del jsonb embebido en datasets.
RESTORE_SNAPSHOT_VERSION = 3
# Alias de compatibilidad para importadores antiguos. ``None`` significa que
# el backend no descarta estados por tamaño; PostgreSQL/TOAST los almacena en
# la tabla dedicada creada por la migración 0020.
MAX_RESTORE_SNAPSHOT_BYTES: int | None = None
logger = logging.getLogger(__name__)


def _configured(settings: Settings) -> bool:
    return bool(settings.supabase_url and settings.supabase_service_role_key)


def _headers(settings: Settings, *, representation: bool = False) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }
    if representation:
        headers["Prefer"] = "return=representation"
    return headers


def _rest_url(settings: Settings, table: str) -> str:
    return f"{settings.supabase_url.rstrip('/')}/rest/v1/{table}"


def _valid_uuid(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError):
        return None


def _get(
    table: str,
    params: dict[str, str],
    settings: Settings,
) -> httpx.Response:
    try:
        return httpx.get(
            _rest_url(settings, table),
            params=params,
            headers=_headers(settings),
            timeout=20,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo consultar Supabase: {exc.__class__.__name__}",
        ) from exc


def _post_rpc(
    function: str,
    payload: dict[str, Any],
    settings: Settings,
) -> httpx.Response:
    try:
        return httpx.post(
            f"{settings.supabase_url.rstrip('/')}/rest/v1/rpc/{function}",
            json=payload,
            headers=_headers(settings),
            timeout=20,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo consultar Supabase: {exc.__class__.__name__}",
        ) from exc


def reserve_restore_snapshot_revision(
    dataset_id: str,
    user_id: str,
    settings: Settings | None = None,
) -> int | None:
    """Reserva el orden de una petición antes de ejecutar pandas.

    No hay fallback local: una revisión que no proviene de PostgreSQL no puede
    ordenar de forma segura procesos o instancias distintas del backend.
    """

    settings = settings or get_settings()
    safe_dataset_id = _valid_uuid(dataset_id)
    if not _configured(settings) or safe_dataset_id is None:
        return None
    try:
        response = _post_rpc(
            "reserve_restore_snapshot_revision",
            {"p_dataset_id": safe_dataset_id, "p_user_id": user_id},
            settings,
        )
    except HTTPException as exc:
        logger.warning("Could not reserve restore revision: %s", exc.detail)
        return None
    if response.status_code != 200:
        logger.warning(
            "Supabase rejected restore revision reservation with status %s",
            response.status_code,
        )
        return None
    try:
        revision = int(response.json())
    except (TypeError, ValueError):
        return None
    return revision if revision > 0 else None


def fetch_restore_state_metadata(
    dataset_id: str,
    user_id: str,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Authoritative global restore state, including its monotonic revision."""

    settings = settings or get_settings()
    safe_dataset_id = _valid_uuid(dataset_id)
    if not _configured(settings) or safe_dataset_id is None:
        return None
    state_response = _get(
        "dataset_restore_states",
        {
            "dataset_id": f"eq.{safe_dataset_id}",
            "user_id": f"eq.{user_id}",
            "select": (
                "dataset_id,user_id,revision,active_sheet,available_sheets,"
                "excluded_sheets,selected_sheets,sheet_errors,analysis_scope,"
                "combine_sheets,source_sha256,engine_version,updated_at"
            ),
            "limit": "1",
        },
        settings,
    )
    # Compatibilidad durante un despliegue escalonado antes de 0021.
    if state_response.status_code == 400:
        state_response = _get(
            "dataset_restore_states",
            {
                "dataset_id": f"eq.{safe_dataset_id}",
                "user_id": f"eq.{user_id}",
                "select": (
                    "dataset_id,user_id,revision,active_sheet,available_sheets,"
                    "excluded_sheets,combine_sheets,source_sha256,engine_version,updated_at"
                ),
                "limit": "1",
            },
            settings,
        )
    if state_response.status_code != 200:
        return None
    states = state_response.json()
    if not isinstance(states, list) or not states or not isinstance(states[0], dict):
        return None
    return states[0]


def fetch_restore_state_bundle(
    dataset_id: str,
    user_id: str,
    settings: Settings | None = None,
    *,
    state: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Estado global y snapshots por hoja, leídos de tablas dedicadas."""

    settings = settings or get_settings()
    safe_dataset_id = _valid_uuid(dataset_id)
    if not _configured(settings) or safe_dataset_id is None:
        return None
    authoritative_state = state or fetch_restore_state_metadata(
        safe_dataset_id, user_id, settings
    )
    if authoritative_state is None:
        return None

    sheets_response = _get(
        "dataset_sheet_snapshots",
        {
            "dataset_id": f"eq.{safe_dataset_id}",
            "user_id": f"eq.{user_id}",
            "select": (
                "sheet_key,revision,source_sha256,rules_hash,mapping_hash,"
                "sheet,engine_version,snapshot"
            ),
            "order": "revision.asc",
        },
        settings,
    )
    if sheets_response.status_code != 200:
        return None
    sheets = sheets_response.json()
    if not isinstance(sheets, list):
        return None
    return {"state": authoritative_state, "sheets": sheets}


def fetch_latest_restore_record(
    user_id: str,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Latest restorable dataset owned by the authenticated user."""
    settings = settings or get_settings()
    if not _configured(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El servidor no tiene configurado Supabase.",
        )
    base_params = {
        "user_id": f"eq.{user_id}",
        "storage_path": "not.is.null",
        "status": "neq.error",
        "order": "created_at.desc",
        "limit": "1",
    }
    response = _get(
        "datasets",
        {
            **base_params,
            "select": "id,name,source,storage_path,status,created_at,restore_snapshot",
        },
        settings,
    )
    # Rolling-deploy compatibility before migration 0014 is applied.
    if response.status_code == 400 and "restore_snapshot" in response.text:
        response = _get(
            "datasets",
            {
                **base_params,
                "select": "id,name,source,storage_path,status,created_at",
            },
            settings,
        )
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Supabase respondio {response.status_code} al buscar el ultimo archivo.",
        )
    rows = response.json()
    if not isinstance(rows, list) or not rows:
        return None
    row = rows[0]
    return row if isinstance(row, dict) else None


def fetch_restore_record(
    dataset_id: str,
    user_id: str,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Dataset concreto, filtrado por propietario, para mutaciones de estado."""

    settings = settings or get_settings()
    safe_dataset_id = _valid_uuid(dataset_id)
    if safe_dataset_id is None:
        return None
    if not _configured(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El servidor no tiene configurado Supabase.",
        )
    response = _get(
        "datasets",
        {
            "id": f"eq.{safe_dataset_id}",
            "user_id": f"eq.{user_id}",
            "select": "id,name,source,storage_path,status,created_at",
            "limit": "1",
        },
        settings,
    )
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Supabase no pudo validar el dataset. Puedes reintentar.",
        )
    rows = response.json()
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return None
    return rows[0]


def fetch_latest_cleaning_config(
    dataset_id: str,
    user_id: str,
    settings: Settings | None = None,
) -> tuple[dict[str, bool], bool]:
    settings = settings or get_settings()
    params = {
        "select": "rules,options",
        "dataset_id": f"eq.{dataset_id}",
        "user_id": f"eq.{user_id}",
        "order": "created_at.desc",
        "limit": "1",
    }
    response = _get("cleaning_jobs", params, settings)
    if response.status_code == 400 and "options" in response.text:
        response = _get("cleaning_jobs", {**params, "select": "rules"}, settings)
    if response.status_code != 200:
        return dict(DEFAULT_RULES), False
    rows = response.json()
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return dict(DEFAULT_RULES), False
    row = rows[0]
    rules = row.get("rules") if isinstance(row.get("rules"), dict) else {}
    options = row.get("options") if isinstance(row.get("options"), dict) else {}
    return {**DEFAULT_RULES, **rules}, bool(options.get("eliminar_duplicados", False))


def fetch_dataset_mapping(
    dataset_id: str,
    settings: Settings | None = None,
) -> dict[str, str] | None:
    settings = settings or get_settings()
    response = _get(
        "dataset_columns",
        {
            "select": "original_name,mapped_role",
            "dataset_id": f"eq.{dataset_id}",
            "mapped_role": "not.is.null",
        },
        settings,
    )
    if response.status_code != 200:
        return None
    rows = response.json()
    if not isinstance(rows, list):
        return None
    mapping = {
        str(row["mapped_role"]): str(row["original_name"])
        for row in rows
        if isinstance(row, dict) and row.get("mapped_role") and row.get("original_name")
    }
    return mapping or None


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    import hashlib

    return hashlib.sha256(encoded).hexdigest()[:16]


def build_restore_snapshot(
    standardization: dict,
    cleaning: dict | None,
    metrics: dict | None,
    mapping: dict[str, str] | None,
    eliminar_duplicados: bool,
    *,
    revision: int,
    source_sha256: str,
    rules: dict | None = None,
    sheet: str | None = None,
) -> dict[str, Any]:
    if revision <= 0:
        raise ValueError("revision must be reserved before building a snapshot")
    if not isinstance(source_sha256, str) or not re.fullmatch(
        r"[0-9a-f]{64}", source_sha256
    ):
        raise ValueError("source_sha256 must be a full SHA-256 hex digest")
    now = datetime.now(timezone.utc)
    return {
        "version": RESTORE_SNAPSHOT_VERSION,
        "engine_version": ENGINE_VERSION,
        "generated_at": now.isoformat(),
        # Reservada por PostgreSQL al recibir la petición, no al finalizarla.
        "revision": revision,
        # Procedencia auditable: qué archivo/reglas/mapeo produjeron esto
        "source_sha256": source_sha256,
        "rules_hash": _stable_hash(rules or {}),
        "mapping_hash": _stable_hash(mapping or {}),
        "sheet": sheet,
        "standardization": standardization,
        "cleaning": cleaning,
        "metrics": metrics,
        "mapping": mapping,
        "eliminar_duplicados": bool(eliminar_duplicados),
    }


def valid_restore_snapshot(
    raw: Any,
    dataset_status: str,
    *,
    expected_revision: int,
    expected_source_sha256: str,
    expected_rules_hash: str,
    expected_mapping_hash: str,
    expected_sheet: str | None,
) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or raw.get("version") != RESTORE_SNAPSHOT_VERSION:
        return None
    # Fase 15: un snapshot generado por OTRO motor se invalida — el fallback
    # recalcula con el motor actual y lo reemplaza (resultados nunca mezclan
    # versiones). Cambios de archivo/mapeo/reglas producen dataset o snapshot
    # nuevos por diseño; esta es la última línea de defensa.
    if raw.get("engine_version") != ENGINE_VERSION:
        return None
    if not isinstance(expected_revision, int) or expected_revision <= 0:
        return None
    if not isinstance(expected_source_sha256, str) or not re.fullmatch(
        r"[0-9a-f]{64}", expected_source_sha256
    ):
        return None
    if not isinstance(expected_rules_hash, str) or not re.fullmatch(
        r"[0-9a-f]{16}", expected_rules_hash
    ):
        return None
    if not isinstance(expected_mapping_hash, str) or not re.fullmatch(
        r"[0-9a-f]{16}", expected_mapping_hash
    ):
        return None
    if raw.get("revision") != expected_revision:
        return None
    if raw.get("source_sha256") != expected_source_sha256:
        return None
    if raw.get("rules_hash") != expected_rules_hash:
        return None
    if raw.get("mapping_hash") != expected_mapping_hash:
        return None
    if raw.get("sheet") != expected_sheet:
        return None
    if not isinstance(raw.get("standardization"), dict):
        return None
    if dataset_status == "limpio":
        if not isinstance(raw.get("cleaning"), dict):
            return None
        if not isinstance(raw.get("metrics"), dict):
            return None
    mapping = raw.get("mapping")
    if mapping is not None and not isinstance(mapping, dict):
        return None
    if _stable_hash(mapping or {}) != expected_mapping_hash:
        return None
    cleaning = raw.get("cleaning")
    rules = cleaning.get("reglas_activas") if isinstance(cleaning, dict) else None
    if _stable_hash(rules or {}) != expected_rules_hash:
        return None
    return raw


def store_restore_snapshot(
    dataset_id: str,
    user_id: str,
    snapshot: dict[str, Any],
    settings: Settings | None = None,
    restore_state: dict[str, Any] | None = None,
) -> bool:
    """Guarda una hoja mediante una única función PostgreSQL atómica."""
    settings = settings or get_settings()
    safe_dataset_id = _valid_uuid(dataset_id)
    if not _configured(settings) or safe_dataset_id is None:
        return False
    revision = snapshot.get("revision")
    if not isinstance(revision, int) or revision <= 0:
        return False

    state = restore_state if isinstance(restore_state, dict) else {}
    available_sheets = state.get("available_sheets")
    if not isinstance(available_sheets, list):
        available_sheets = (
            snapshot.get("standardization", {}).get("carga", {}).get("hojas_disponibles", [])
        )
    active_sheet = state.get("active_sheet", snapshot.get("sheet"))
    excluded_sheets = state.get("excluded_sheets")
    if not isinstance(excluded_sheets, list):
        excluded_sheets = [
            name for name in available_sheets if name != snapshot.get("sheet")
        ]
    payload = {
        "p_dataset_id": safe_dataset_id,
        "p_user_id": user_id,
        "p_sheet_key": snapshot.get("sheet") or "__single__",
        "p_snapshot": snapshot,
        "p_revision": revision,
        "p_source_sha256": snapshot.get("source_sha256"),
        "p_rules_hash": snapshot.get("rules_hash"),
        "p_mapping_hash": snapshot.get("mapping_hash"),
        "p_sheet": snapshot.get("sheet"),
        "p_active_sheet": active_sheet,
        "p_available_sheets": available_sheets,
        "p_excluded_sheets": excluded_sheets,
        "p_combine_sheets": bool(state.get("combine_sheets", False)),
        "p_engine_version": ENGINE_VERSION,
    }
    analysis_scope = state.get("analysis_scope")
    persisted_analysis_scope = (
        dict(analysis_scope) if isinstance(analysis_scope, dict) else {}
    )
    selection_mode = state.get("selection_mode")
    if selection_mode in {"all", "custom"}:
        # 0021 ya persiste analysis_scope como JSONB. Guardar aquí el modo de
        # selección evita otra columna/migración y permite restaurar exactamente
        # "Todas" frente a "Elegir hojas" después de recargar.
        persisted_analysis_scope["_selection_mode"] = selection_mode
    payload_v2 = {
        **payload,
        "p_selected_sheets": state.get("selected_sheets", []),
        "p_sheet_errors": state.get("sheet_errors", {}),
        "p_analysis_scope": persisted_analysis_scope,
    }
    uses_v2 = any(
        key in state
        for key in (
            "selected_sheets",
            "sheet_errors",
            "analysis_scope",
            "selection_mode",
        )
    )
    try:
        response = _post_rpc(
            "store_restore_snapshot_guarded_v2" if uses_v2 else "store_restore_snapshot_guarded",
            payload_v2 if uses_v2 else payload,
            settings,
        )
    except HTTPException as exc:
        logger.warning("Could not persist restore snapshot: %s", exc.detail)
        return False
    if response.status_code != 200:
        logger.warning("Supabase rejected restore snapshot with status %s", response.status_code)
        return False
    try:
        stored = response.json()
    except ValueError:
        return False
    return stored is True
