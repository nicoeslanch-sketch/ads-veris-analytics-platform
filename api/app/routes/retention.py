"""Retención de archivos en Supabase Storage (Fase 8).

Cada usuario puede conservar hasta N archivos según su plan (10 Básico /
25 Analista / 50 Gold). Al subir un archivo nuevo, el frontend dispara
POST /storage/retention (fire-and-forget) y el backend poda la carpeta
{user_id}/ del bucket:

1. Los `storage_keep_last` archivos más recientes JAMÁS se borran.
2. Se elimina el excedente sobre el tope del plan (los más antiguos primero).
3. Se elimina lo no usado hace más de `storage_retention_days` días
   ("uso" = subida, modificación o último acceso registrado por Storage).

Los datasets cuyo archivo se purga conservan su fila en el historial, pero
con storage_path en null (la UI muestra "archivo ya no disponible" en vez
de fallar con 404 al retomar). Así el Storage no crece sin control y la
plataforma se mantiene rápida y barata de operar.
"""

from datetime import datetime, timezone
import logging
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from ..auth import AuthenticatedUser, get_current_user
from ..capabilities import get_profile_flags
from ..config import Settings, get_settings
from ..storage import invalidate_storage_cache
from ..commercial_rpc import commercial_rpc

router = APIRouter(prefix="/storage")

_TIMEOUT = 30
logger = logging.getLogger('uvicorn.error')


def _configured(settings: Settings) -> bool:
    return bool(settings.supabase_url and settings.supabase_service_role_key)


def _headers(settings: Settings) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }


def max_files_for(plan: str, is_admin: bool, settings: Settings) -> int:
    if is_admin:
        return settings.storage_max_files_gold
    return {
        "basico": settings.storage_max_files_basico,
        "analista": settings.storage_max_files_analista,
        "gold": settings.storage_max_files_gold,
    }.get(plan, settings.storage_max_files_basico)


def _parse_ts(value: str | None) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _last_use(item: dict) -> datetime:
    """Último uso conocido del archivo: subida, modificación o acceso."""
    candidates = [
        _parse_ts(item.get("created_at")),
        _parse_ts(item.get("updated_at")),
        _parse_ts(item.get("last_accessed_at")),
    ]
    valid = [c for c in candidates if c is not None]
    return max(valid) if valid else datetime.now(timezone.utc)


def _list_user_files(user_id: str, settings: Settings) -> list[dict]:
    url = (
        f"{settings.supabase_url.rstrip('/')}/storage/v1/object/list/"
        f"{settings.supabase_storage_bucket}"
    )
    files, seen = [], set()
    for offset in range(0, 10_000, 1000):
        response = httpx.post(url, json={"prefix": f"{user_id}/", "limit": 1000,
            "offset": offset, "sortBy": {"column": "name", "order": "asc"}},
            headers=_headers(settings), timeout=_TIMEOUT)
        response.raise_for_status()
        items = response.json()
        if not isinstance(items, list):
            raise HTTPException(503, "No se pudo verificar el inventario de archivos.")
        for item in items:
            if not isinstance(item, dict):
                raise HTTPException(503, "Inventario de archivos incompleto.")
            if not item.get("id"):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name or name in ('.', '..') or '/' in name or '\\' in name or name in seen:
                raise HTTPException(503, "Inventario de archivos no verificable.")
            seen.add(name)
            files.append(item)
        if len(items) < 1000:
            return files
    raise HTTPException(503, "Inventario demasiado grande para una retencion segura.")


def _delete_files(user_id: str, names: list[str], settings: Settings) -> None:
    url = (
        f"{settings.supabase_url.rstrip('/')}/storage/v1/object/"
        f"{settings.supabase_storage_bucket}"
    )
    response = httpx.request(
        "DELETE",
        url,
        json={"prefixes": [f"{user_id}/{name}" for name in names]},
        headers=_headers(settings),
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    removed = response.json()
    expected = {f'{user_id}/{name}' for name in names}
    if not isinstance(removed, list) or not expected.issubset({
        row.get('name') for row in removed if isinstance(row, dict)
    }):
        raise HTTPException(503, 'No se pudo confirmar la eliminacion del archivo.')
    for name in names:
        invalidate_storage_cache(f"{user_id}/{name}")


def _unlink_datasets(user_id: str, names: list[str], settings: Settings) -> None:
    """A failed unlink remains recoverable in the private retention journal."""
    rest = f"{settings.supabase_url.rstrip('/')}/rest/v1/datasets"
    for name in names:
        response = httpx.patch(
                rest,
                params={
                    "user_id": f"eq.{user_id}",
                    "storage_path": f"eq.{user_id}/{name}",
                },
                json={"storage_path": None},
                headers={**_headers(settings), "Prefer": "return=minimal"},
                timeout=_TIMEOUT,
        )
        response.raise_for_status()


def _prune_activity(user_id: str, settings: Settings) -> int:
    """Conserva una bitácora compacta de las fuentes recientes.

    Además colapsa el legado multihoja que registró una limpieza idéntica por
    hoja. No toca cleaning_jobs ni snapshots: activity_log es trazabilidad,
    no la caché que permite restaurar documentos.
    """

    root = f"{settings.supabase_url.rstrip('/')}/rest/v1"
    datasets_response = httpx.get(
        f"{root}/datasets",
        params={
            "user_id": f"eq.{user_id}",
            "select": "id",
            "order": "created_at.desc",
            "limit": str(max(1, settings.activity_retention_dataset_limit)),
        },
        headers=_headers(settings),
        timeout=_TIMEOUT,
    )
    datasets_response.raise_for_status()
    recent_datasets = {
        str(row["id"])
        for row in datasets_response.json()
        if isinstance(row, dict) and row.get("id")
    }

    activity_response = httpx.get(
        f"{root}/activity_log",
        params={
            "user_id": f"eq.{user_id}",
            "select": "id,dataset_id,activity_type,description,created_at",
            "order": "created_at.desc",
            "limit": "1000",
        },
        headers=_headers(settings),
        timeout=_TIMEOUT,
    )
    activity_response.raise_for_status()
    rows = activity_response.json()
    if not isinstance(rows, list):
        return 0

    kept = 0
    seen: set[str] = set()
    delete_ids: list[str] = []
    max_events = max(1, settings.activity_retention_max_events)
    for row in rows:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        dataset_id = str(row.get("dataset_id") or "")
        description = re.sub(r"\s+", " ", str(row.get("description") or "")).strip().casefold()
        activity_type = str(row.get("activity_type") or "")
        key = (
            f"{dataset_id}:limpieza"
            if dataset_id and activity_type == "limpieza"
            else f"{dataset_id}:{activity_type}:{description}"
        )
        outside_recent_sources = bool(dataset_id) and dataset_id not in recent_datasets
        duplicate = key in seen
        over_limit = kept >= max_events
        if outside_recent_sources or duplicate or over_limit:
            delete_ids.append(str(row["id"]))
            continue
        seen.add(key)
        kept += 1

    if not delete_ids:
        return 0
    deleted_count = 0
    for start in range(0, len(delete_ids), 100):
        batch = delete_ids[start : start + 100]
        response = httpx.request(
            "DELETE",
            f"{root}/activity_log",
            params={
                "user_id": f"eq.{user_id}",
                "id": f"in.({','.join(batch)})",
            },
            headers={**_headers(settings), "Prefer": "return=representation"},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        deleted = response.json()
        if isinstance(deleted, list):
            deleted_count += len(deleted)
    return deleted_count


def _retention_plan(user_id: str, settings: Settings) -> tuple[dict, list[dict], list[dict]]:
    plan, is_admin = get_profile_flags(user_id, settings, require_profile=True)
    limit = max_files_for(plan, is_admin, settings)
    keep_last = settings.storage_keep_last
    max_age_days = settings.storage_retention_days

    files = _list_user_files(user_id, settings)
    files.sort(key=_last_use, reverse=True)  # más reciente primero

    now = datetime.now(timezone.utc)
    candidates: list[dict] = []
    for index, item in enumerate(files):
        if index < keep_last:
            continue  # los más recientes jamás se tocan
        if not any(_parse_ts(item.get(key)) for key in ('created_at', 'updated_at', 'last_accessed_at')):
            continue
        over_limit = index >= limit
        expired = (now - _last_use(item)).days > max_age_days
        if over_limit or expired:
            candidates.append(item)
    return {
        "eliminados": 0,
        "conservados": len(files),
        "limite": limit,
        "plan": plan,
        "actividad_eliminada": 0,
        "candidatos": len(candidates),
    }, files, candidates


def _journal(action, user_id, settings, **payload):
    return commercial_rpc('retention_journal_operation', {'p_action': action, 'p_user_id': user_id, **payload}, settings)


def _retention_sync(user_id: str, settings: Settings, *, dry_run: bool = False) -> dict:
    if dry_run:
        report, _, _ = _retention_plan(user_id, settings)
        return {**report, 'simulacion': True}
    lease = commercial_rpc('retention_guard', {'p_action': 'claim', 'p_user_id': user_id}, settings)
    if not lease:
        raise HTTPException(409, 'La conservacion de archivos ya esta en curso.')
    def renew():
        renewed = commercial_rpc('retention_guard', {
            'p_action': 'renew', 'p_user_id': user_id, 'p_lease': lease}, settings)
        if not renewed:
            raise HTTPException(409, 'El turno de conservacion de archivos vencio.')
    try:
        return _retention_locked(user_id, settings, renew)
    finally:
        try:
            commercial_rpc('retention_guard', {'p_action': 'release', 'p_user_id': user_id, 'p_lease': lease}, settings)
        except Exception:
            logger.warning('retention_guard_release_pending')


def _retention_locked(user_id: str, settings: Settings, renew) -> dict:
    report, files, candidates = _retention_plan(user_id, settings)
    pending = _journal('list', user_id, settings)
    for item in candidates[:100]:
        renew()
        job = _journal('begin', user_id, settings, p_name=item['name'],
                       p_object_id=str(item['id']), p_stamp=_last_use(item).isoformat())
        if job['stage'] in ('pending', 'storage_deleted') and not any(row['id'] == job['id'] for row in pending):
            pending.append(job)
    if pending:
        # A fresh inventory protects files accessed/replaced since planning.
        _, fresh, eligible = _retention_plan(user_id, settings)
        current = {row['name']: row for row in fresh}
        allowed = {row['name'] for row in eligible}
        for job in pending[:100]:
            renew()
            name, present = job['object_name'], current.get(job['object_name'])
            if present and (name not in allowed or str(present['id']) != job['object_id']
                            or _last_use(present).isoformat() != job['object_stamp']
                            or job['stage'] == 'storage_deleted'):
                _journal('advance', user_id, settings, p_id=job['id'], p_stage='cancelled')
                continue
            if present:
                _delete_files(user_id, [name], settings)
                report['eliminados'] += 1
            _journal('advance', user_id, settings, p_id=job['id'], p_stage='storage_deleted')
            _unlink_datasets(user_id, [name], settings)
            _journal('advance', user_id, settings, p_id=job['id'], p_stage='completed')
        report['conservados'] = max(0, len(fresh) - report['eliminados'])
    try:
        report['actividad_eliminada'] = _prune_activity(user_id, settings)
    except httpx.HTTPError:
        report['actividad_error'] = True
    return report


@router.post("/retention")
async def apply_retention(
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Poda los archivos guardados del usuario según su plan (ver docstring)."""
    if not _configured(settings):
        return {
            "eliminados": 0,
            "conservados": 0,
            "limite": 0,
            "plan": "basico",
            "actividad_eliminada": 0,
        }
    try:
        return await run_in_threadpool(_retention_sync, user.id, settings)
    except (httpx.HTTPError, HTTPException) as exc:
        # La retención jamás debe romper el flujo de carga del usuario.
        logger.warning('retention_incomplete')
        return {
            "eliminados": 0,
            "conservados": 0,
            "limite": 0,
            "plan": "basico",
            "actividad_eliminada": 0,
            "error": True,
        }
