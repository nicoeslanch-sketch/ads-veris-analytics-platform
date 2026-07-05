"""Conectores de fuentes externas (SPEC §7 — Fase 6). Exigen JWT de Supabase.

POST /connectors/sheets — importa una hoja de Google Sheets pública o
compartida por enlace. El frontend manda la URL que el usuario pegó; la API
extrae el ID del documento y arma ELLA la URL oficial de export a CSV
(nunca descarga la URL cruda del usuario — sin SSRF), con el mismo tope de
15 MB del resto del pipeline. Devuelve el CSV como texto para que el
navegador lo procese igual que un archivo subido (Storage + /standardize).
"""

import re
from urllib.parse import unquote

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..storage import MAX_DOWNLOAD_BYTES

router = APIRouter(prefix="/connectors", dependencies=[Depends(get_current_user)])

_SHEET_ID_RE = re.compile(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]{20,})")
_GID_RE = re.compile(r"[#?&]gid=(\d+)")
_FILENAME_RE = re.compile(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', re.IGNORECASE)
_SAFE_FILENAME_RE = re.compile(r"[^a-zA-Z0-9._ -]+")


class SheetsImportRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2000)


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


@router.post("/sheets")
async def import_google_sheet(body: SheetsImportRequest) -> dict:
    """Importa una hoja pública de Google Sheets como CSV."""
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
    return {"filename": _sanitize_filename(filename), "csv": csv_text}
