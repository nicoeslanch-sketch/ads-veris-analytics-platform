"""Conectores de fuentes externas (SPEC §7 — Fase 6). Exigen JWT de Supabase.

POST /connectors/sheets — importa una hoja de Google Sheets pública o
compartida por enlace. El frontend manda la URL que el usuario pegó; la API
extrae el ID del documento y arma ELLA la URL oficial de export a CSV
(nunca descarga la URL cruda del usuario — sin SSRF), con el mismo tope de
15 MB del resto del pipeline. Devuelve el CSV como texto para que el
navegador lo procese igual que un archivo subido (Storage + /standardize).
"""

import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import unquote

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from ..auth import AuthenticatedUser, get_current_user
from ..capabilities import Capability, require_capability_for_user
from ..config import Settings, get_settings
from ..storage import MAX_DOWNLOAD_BYTES

router = APIRouter(prefix="/connectors", dependencies=[Depends(get_current_user)])

_SHEET_ID_RE = re.compile(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]{20,})")
_GID_RE = re.compile(r"[#?&]gid=(\d+)")
_FILENAME_RE = re.compile(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', re.IGNORECASE)
_SAFE_FILENAME_RE = re.compile(r"[^a-zA-Z0-9._ -]+")


class SheetsImportRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2000)
    sync_mode: str = Field(default="manual", pattern="^(manual|automatic)$")


class SheetsRefreshRequest(BaseModel):
    include_content: bool = False


class SheetsModeRequest(BaseModel):
    sync_mode: str = Field(pattern="^(manual|automatic)$")


class SheetsLinkRequest(BaseModel):
    dataset_id: str | None = Field(default=None, max_length=80)


def _sanitize_filename(filename: str) -> str:
    """Normaliza nombres de Google antes de devolverlos al navegador."""
    decoded = unquote(filename).replace("\\", "/").split("/")[-1]
    decoded = _SAFE_FILENAME_RE.sub("_", decoded).strip(" ._-")
    if not decoded:
        decoded = "google-sheets"
    if decoded.lower().endswith(".csv"):
        decoded = decoded[:-4]
    decoded = decoded[:80].strip(" ._-") or "google-sheets"
    return f"{decoded}.csv"


def _parse_sheet_url(url: str) -> tuple[str, str]:
    """Extrae (sheet_id, gid) de una URL de Google Sheets; 400 si no lo es."""
    match = _SHEET_ID_RE.search(url)
    if not match:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La URL no parece de Google Sheets. Pega el enlace del documento "
            "(docs.google.com/spreadsheets/d/...).",
        )
    gid_match = _GID_RE.search(url)
    return match.group(1), gid_match.group(1) if gid_match else "0"


def _download_sheet_csv(sheet_id: str, gid: str) -> tuple[str, bytes]:
    """Descarga el export CSV oficial. Devuelve (nombre_archivo, contenido)."""
    export_url = (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    )
    try:
        with httpx.stream(
            "GET", export_url, follow_redirects=True, timeout=30
        ) as response:
            if response.status_code in (401, 403):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="La hoja no es pública. En Google Sheets: Compartir → "
                    "'Cualquier persona con el enlace' (como lector).",
                )
            if response.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No se encontró la hoja. Revisa el enlace.",
                )
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Google Sheets respondió {response.status_code}.",
                )
            content_type = response.headers.get("content-type", "")
            if "text/html" in content_type:
                # Google devuelve la página de login cuando la hoja es privada
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="La hoja no es pública. En Google Sheets: Compartir → "
                    "'Cualquier persona con el enlace' (como lector).",
                )
            chunks: list[bytes] = []
            received = 0
            for chunk in response.iter_bytes():
                received += len(chunk)
                if received > MAX_DOWNLOAD_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="La hoja supera los 15 MB. Divide los datos en hojas "
                        "más pequeñas.",
                    )
                chunks.append(chunk)
            # Google manda el nombre real en Content-Disposition
            disposition = response.headers.get("content-disposition", "")
            name_match = _FILENAME_RE.search(disposition)
            filename = name_match.group(1) if name_match else f"google-sheets-{sheet_id[:8]}.csv"
            return _sanitize_filename(filename), b"".join(chunks)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo contactar a Google Sheets: {exc.__class__.__name__}",
        )


def _configured(settings: Settings) -> bool:
    return bool(settings.supabase_url and settings.supabase_service_role_key)


def _headers(settings: Settings) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }


def _rest(settings: Settings, table: str) -> str:
    return f"{settings.supabase_url.rstrip('/')}/rest/v1/{table}"


def _hash_content(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical_url(sheet_id: str, gid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit#gid={gid}"


def _save_source_sync(
    user_id: str,
    sheet_id: str,
    gid: str,
    filename: str,
    sync_mode: str,
    content_hash: str,
    settings: Settings,
) -> str | None:
    if not _configured(settings):
        return None
    try:
        response = httpx.post(
            _rest(settings, "google_sheet_sources"),
            params={"on_conflict": "user_id,sheet_id,gid"},
            json={
                "user_id": user_id,
                "source_url": _canonical_url(sheet_id, gid),
                "sheet_id": sheet_id,
                "gid": gid,
                "display_name": filename.removesuffix(".csv"),
                "sync_mode": sync_mode,
                "content_hash": content_hash,
                "remote_hash": content_hash,
                "update_available": False,
                "last_status": "connected",
                "last_error": None,
                "last_checked_at": datetime.now(timezone.utc).isoformat(),
                "last_synced_at": datetime.now(timezone.utc).isoformat(),
            },
            headers={
                **_headers(settings),
                "Prefer": "resolution=merge-duplicates,return=representation",
            },
            timeout=10,
        )
        response.raise_for_status()
        rows = response.json()
        return str(rows[0]["id"]) if rows else None
    except httpx.HTTPError:
        return None


def _source_for_user_sync(source_id: str, user_id: str, settings: Settings) -> dict:
    response = httpx.get(
        _rest(settings, "google_sheet_sources"),
        params={
            "id": f"eq.{source_id}",
            "user_id": f"eq.{user_id}",
            "select": "*",
            "limit": "1",
        },
        headers=_headers(settings),
        timeout=10,
    )
    response.raise_for_status()
    rows = response.json()
    if not rows:
        raise HTTPException(status_code=404, detail="No existe esa conexión de Google Sheets.")
    return rows[0]


@router.post("/sheets")
async def import_google_sheet(
    body: SheetsImportRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Importa una hoja pública de Google Sheets como CSV."""
    # Fase 13: importar datos es procesar archivos — requiere plan activo o
    # prueba gratuita vigente. threadpool: la puerta consulta Supabase por HTTP.
    await run_in_threadpool(
        require_capability_for_user, user.id, Capability.STANDARDIZE, settings
    )
    sheet_id, gid = _parse_sheet_url(body.url)
    filename, content = await run_in_threadpool(_download_sheet_csv, sheet_id, gid)
    try:
        csv_text = content.decode("utf-8")
    except UnicodeDecodeError:
        csv_text = content.decode("latin-1")
    if not csv_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La hoja está vacía.",
        )
    content_hash = _hash_content(content)
    source_id = await run_in_threadpool(
        _save_source_sync,
        user.id,
        sheet_id,
        gid,
        _sanitize_filename(filename),
        body.sync_mode,
        content_hash,
        settings,
    )
    return {
        "filename": _sanitize_filename(filename),
        "csv": csv_text,
        "source_id": source_id,
        "content_hash": content_hash,
        "persistent": source_id is not None,
    }


def _list_sources_sync(user_id: str, settings: Settings) -> list:
    if not _configured(settings):
        return []
    response = httpx.get(
        _rest(settings, "google_sheet_sources"),
        params={
            "user_id": f"eq.{user_id}",
            "select": "id,dataset_id,source_url,display_name,gid,sync_mode,update_available,last_status,last_error,last_checked_at,last_synced_at,created_at",
            "order": "updated_at.desc",
            "limit": "100",
        },
        headers=_headers(settings),
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


@router.get("/sheets/sources")
async def list_google_sheet_sources(
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        sources = await run_in_threadpool(_list_sources_sync, user.id, settings)
    except httpx.HTTPError:
        return {"available": False, "sources": []}
    return {"available": True, "sources": sources}


def _refresh_source_sync(
    source_id: str,
    user_id: str,
    include_content: bool,
    settings: Settings,
) -> dict:
    source = _source_for_user_sync(source_id, user_id, settings)
    try:
        filename, content = _download_sheet_csv(str(source["sheet_id"]), str(source["gid"]))
        content_hash = _hash_content(content)
        changed = content_hash != source.get("content_hash")
        now = datetime.now(timezone.utc).isoformat()
        response = httpx.patch(
            _rest(settings, "google_sheet_sources"),
            params={"id": f"eq.{source_id}", "user_id": f"eq.{user_id}"},
            json={
                "remote_hash": content_hash,
                "update_available": changed,
                "last_status": "changed" if changed else "connected",
                "last_error": None,
                "last_checked_at": now,
            },
            headers={**_headers(settings), "Prefer": "return=minimal"},
            timeout=10,
        )
        response.raise_for_status()
        result = {
            "source_id": source_id,
            "filename": _sanitize_filename(filename),
            "changed": changed,
            "content_hash": content_hash,
            "checked_at": now,
        }
        if include_content and changed:
            try:
                result["csv"] = content.decode("utf-8")
            except UnicodeDecodeError:
                result["csv"] = content.decode("latin-1")
        return result
    except (httpx.HTTPError, HTTPException) as exc:
        message = exc.detail if isinstance(exc, HTTPException) else "No se pudo contactar a Google Sheets."
        try:
            httpx.patch(
                _rest(settings, "google_sheet_sources"),
                params={"id": f"eq.{source_id}", "user_id": f"eq.{user_id}"},
                json={
                    "last_status": "error",
                    "last_error": str(message)[:500],
                    "last_checked_at": datetime.now(timezone.utc).isoformat(),
                },
                headers={**_headers(settings), "Prefer": "return=minimal"},
                timeout=10,
            )
        except httpx.HTTPError:
            pass
        raise


@router.post("/sheets/sources/{source_id}/refresh")
async def refresh_google_sheet_source(
    source_id: str,
    body: SheetsRefreshRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    await run_in_threadpool(
        require_capability_for_user, user.id, Capability.STANDARDIZE, settings
    )
    return await run_in_threadpool(
        _refresh_source_sync, source_id, user.id, body.include_content, settings
    )


def _patch_source_sync(source_id: str, user_id: str, payload: dict, settings: Settings) -> None:
    response = httpx.patch(
        _rest(settings, "google_sheet_sources"),
        params={"id": f"eq.{source_id}", "user_id": f"eq.{user_id}"},
        json=payload,
        headers={**_headers(settings), "Prefer": "return=representation"},
        timeout=10,
    )
    response.raise_for_status()
    if not response.json():
        raise HTTPException(status_code=404, detail="No existe esa conexión de Google Sheets.")


@router.post("/sheets/sources/{source_id}/mode")
async def update_google_sheet_mode(
    source_id: str,
    body: SheetsModeRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    await run_in_threadpool(
        _patch_source_sync,
        source_id,
        user.id,
        {"sync_mode": body.sync_mode},
        settings,
    )
    return {"ok": True, "sync_mode": body.sync_mode}


@router.post("/sheets/sources/{source_id}/link")
async def link_google_sheet_dataset(
    source_id: str,
    body: SheetsLinkRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    source = await run_in_threadpool(_source_for_user_sync, source_id, user.id, settings)
    await run_in_threadpool(
        _patch_source_sync,
        source_id,
        user.id,
        {
            "dataset_id": body.dataset_id,
            "content_hash": source.get("remote_hash") or source.get("content_hash"),
            "update_available": False,
            "last_status": "connected",
            "last_synced_at": datetime.now(timezone.utc).isoformat(),
        },
        settings,
    )
    return {"ok": True, "dataset_id": body.dataset_id}


@router.delete("/sheets/sources/{source_id}")
async def delete_google_sheet_source(
    source_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    response = await run_in_threadpool(
        httpx.delete,
        _rest(settings, "google_sheet_sources"),
        params={"id": f"eq.{source_id}", "user_id": f"eq.{user.id}"},
        headers={**_headers(settings), "Prefer": "return=representation"},
        timeout=10,
    )
    response.raise_for_status()
    if not response.json():
        raise HTTPException(status_code=404, detail="No existe esa conexión de Google Sheets.")
    return {"ok": True}
