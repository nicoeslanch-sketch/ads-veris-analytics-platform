"""Persistent, versioned snapshots for fast dataset restoration.

Snapshots contain only the public pipeline responses, never the full dataframe.
They are written with the service-role key and read through the API so clients
cannot forge analytical results in Supabase.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx
from fastapi import HTTPException, status

from .config import Settings, get_settings
from .engine.clean import DEFAULT_RULES
from .version import ENGINE_VERSION


# Fase 15 — v2: el snapshot declara el MOTOR que lo generó (engine_version) y
# metadatos de procedencia (hash del archivo, hashes de reglas/mapeo, hoja).
# Al restaurar, un snapshot de otro motor o de otro esquema se INVALIDA y se
# recalcula — jamás se sirven resultados de una versión distinta como si
# fueran actuales. `revision` (epoch ms) da orden monotónico: una tarea de
# fondo ANTIGUA que termina tarde ya no pisa un snapshot más nuevo.
RESTORE_SNAPSHOT_VERSION = 2
MAX_RESTORE_SNAPSHOT_BYTES = 512 * 1024
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
    source_sha256: str | None = None,
    rules: dict | None = None,
    sheet: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "version": RESTORE_SNAPSHOT_VERSION,
        "engine_version": ENGINE_VERSION,
        "generated_at": now.isoformat(),
        # Orden monotónico para escrituras en carrera (tareas de fondo)
        "revision": int(now.timestamp() * 1000),
        # Procedencia auditable: qué archivo/reglas/mapeo produjeron esto
        "source_sha256": source_sha256,
        "rules_hash": _stable_hash(rules) if rules is not None else None,
        "mapping_hash": _stable_hash(mapping) if mapping is not None else None,
        "sheet": sheet,
        "standardization": standardization,
        "cleaning": cleaning,
        "metrics": metrics,
        "mapping": mapping,
        "eliminar_duplicados": bool(eliminar_duplicados),
    }


def valid_restore_snapshot(raw: Any, dataset_status: str) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or raw.get("version") != RESTORE_SNAPSHOT_VERSION:
        return None
    # Fase 15: un snapshot generado por OTRO motor se invalida — el fallback
    # recalcula con el motor actual y lo reemplaza (resultados nunca mezclan
    # versiones). Cambios de archivo/mapeo/reglas producen dataset o snapshot
    # nuevos por diseño; esta es la última línea de defensa.
    if raw.get("engine_version") != ENGINE_VERSION:
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
    return raw


def store_restore_snapshot(
    dataset_id: str,
    user_id: str,
    snapshot: dict[str, Any],
    settings: Settings | None = None,
) -> bool:
    """Store only a bounded snapshot on a dataset owned by user_id."""
    settings = settings or get_settings()
    safe_dataset_id = _valid_uuid(dataset_id)
    if not _configured(settings) or safe_dataset_id is None:
        return False
    encoded = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_RESTORE_SNAPSHOT_BYTES:
        logger.warning(
            "Restore snapshot omitted because it is too large: %s bytes",
            len(encoded),
        )
        return False
    # Fase 15 — guardia monotónica: dos limpiezas en carrera escriben ambas
    # como tarea de fondo; si la ANTIGUA termina última, no debe pisar a la
    # nueva. El filtro extra solo actualiza cuando el snapshot guardado es más
    # antiguo (o no existe). `generated_at` ISO-UTC ordena lexicográficamente.
    params = {
        "id": f"eq.{safe_dataset_id}",
        "user_id": f"eq.{user_id}",
        "select": "id",
        "or": (
            "(restore_snapshot.is.null,"
            f"restore_snapshot->>generated_at.lt.{snapshot.get('generated_at', '')})"
        ),
    }
    try:
        response = httpx.patch(
            _rest_url(settings, "datasets"),
            params=params,
            json={"restore_snapshot": snapshot},
            headers=_headers(settings, representation=True),
            timeout=20,
        )
        if response.status_code == 400:
            # PostgREST sin soporte del filtro JSON (versiones antiguas):
            # degradar a la escritura simple antes que perder el snapshot.
            response = httpx.patch(
                _rest_url(settings, "datasets"),
                params={k: v for k, v in params.items() if k != "or"},
                json={"restore_snapshot": snapshot},
                headers=_headers(settings, representation=True),
                timeout=20,
            )
    except httpx.HTTPError as exc:
        logger.warning("Could not persist restore snapshot: %s", exc.__class__.__name__)
        return False
    # Missing migration or a deleted dataset stays best-effort.
    if response.status_code != 200:
        logger.warning("Supabase rejected restore snapshot with status %s", response.status_code)
        return False
    try:
        rows = response.json()
    except ValueError:
        return False
    # Lista vacía = la guardia decidió que ya había un snapshot MÁS NUEVO
    # (o el dataset no existe): en ambos casos, no sobrescribimos.
    return isinstance(rows, list) and bool(rows)
