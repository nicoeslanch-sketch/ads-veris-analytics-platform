"""Ingesta acotada para fuentes grandes del dominio de consolidación."""

from __future__ import annotations

import csv
import hashlib
import os
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

import httpx
import pandas as pd
from fastapi import HTTPException, status
from openpyxl import load_workbook

from ..config import Settings, get_settings
from ..storage import normalize_user_storage_path


def sha256_file(path: Path, chunk_bytes: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(chunk_bytes):
            digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def storage_source_file(
    storage_path: str,
    user_id: str,
    settings: Settings | None = None,
) -> Iterator[tuple[Path, str]]:
    """Descarga a un temporal generado; nunca acepta una ruta local del cliente."""
    cfg = settings or get_settings()
    normalized = normalize_user_storage_path(storage_path, user_id)
    if not cfg.supabase_url or not cfg.supabase_service_role_key:
        raise HTTPException(503, "Storage no está configurado para consolidación.")
    max_bytes = max(1, cfg.consolidation_max_source_mb) * 1024 * 1024
    suffix = Path(normalized).suffix.lower()
    encoded = "/".join(quote(part, safe="") for part in normalized.split("/"))
    url = f"{cfg.supabase_url.rstrip('/')}/storage/v1/object/{cfg.supabase_storage_bucket}/{encoded}"
    headers = {
        "Authorization": f"Bearer {cfg.supabase_service_role_key}",
        "apikey": cfg.supabase_service_role_key,
    }
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="ads-consolidation-", suffix=suffix, delete=False) as target:
            temp_path = Path(target.name)
            digest = hashlib.sha256()
            received = 0
            try:
                with httpx.stream("GET", url, headers=headers, timeout=180) as response:
                    if response.status_code == 404:
                        raise HTTPException(404, "La fuente de consolidación no existe.")
                    if response.status_code != 200:
                        raise HTTPException(502, "Storage no pudo entregar la fuente de consolidación.")
                    length = response.headers.get("content-length")
                    if length and int(length) > max_bytes:
                        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "La fuente supera el límite exclusivo de consolidación.")
                    for chunk in response.iter_bytes(1024 * 1024):
                        received += len(chunk)
                        if received > max_bytes:
                            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "La fuente supera el límite exclusivo de consolidación.")
                        digest.update(chunk)
                        target.write(chunk)
            except httpx.HTTPError as exc:
                raise HTTPException(502, f"No se pudo descargar la fuente: {exc.__class__.__name__}.") from exc
        yield temp_path, digest.hexdigest()
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def csv_columns(path: Path, delimiter: str = ";") -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return [str(value).strip() for value in next(csv.reader(source, delimiter=delimiter))]


def iter_csv_chunks(
    path: Path,
    usecols: Sequence[str] | None = None,
    *,
    delimiter: str = ";",
    chunk_rows: int | None = None,
) -> Iterator[pd.DataFrame]:
    rows = chunk_rows or get_settings().consolidation_csv_chunk_rows
    for chunk in pd.read_csv(
        path,
        sep=delimiter,
        usecols=list(usecols) if usecols else None,
        dtype="string",
        chunksize=max(1, rows),
        keep_default_na=False,
        na_values=[],
        encoding="utf-8-sig",
    ):
        yield chunk


def read_csv_selected(path: Path, usecols: Sequence[str] | None = None) -> pd.DataFrame:
    chunks = list(iter_csv_chunks(path, usecols))
    if not chunks:
        return pd.DataFrame(columns=list(usecols or []), dtype="string")
    return pd.concat(chunks, ignore_index=True, copy=False)


def workbook_headers(path: Path) -> dict[str, list[str]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        result: dict[str, list[str]] = {}
        for sheet in workbook.worksheets:
            header: list[str] = []
            for row in sheet.iter_rows(values_only=True):
                values = [str(value).strip() if value is not None else "" for value in row]
                if any(values):
                    header = values
                    break
            result[sheet.title] = header
        return result
    finally:
        workbook.close()


def read_xlsx_selected(
    path: Path,
    *,
    sheet_name: str,
    usecols: Sequence[str],
    filter_equals: tuple[str, str] | None = None,
) -> pd.DataFrame:
    """Itera filas reales en modo read-only y materializa solo columnas útiles."""
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if sheet_name not in workbook.sheetnames:
            raise ValueError(f"No existe la hoja '{sheet_name}'.")
        rows = workbook[sheet_name].iter_rows(values_only=True)
        header = [str(value).strip() if value is not None else "" for value in next(rows)]
        missing = [column for column in usecols if column not in header]
        if missing:
            raise ValueError(f"Faltan columnas en '{sheet_name}': {', '.join(missing)}")
        indexes = [header.index(column) for column in usecols]
        filter_index = header.index(filter_equals[0]) if filter_equals else None
        records: list[tuple[object, ...]] = []
        for row in rows:
            if filter_equals and str(row[filter_index]).strip() != filter_equals[1]:
                continue
            values = tuple(row[index] if index < len(row) else None for index in indexes)
            if any(value is not None and str(value).strip() for value in values):
                records.append(values)
        return pd.DataFrame.from_records(records, columns=list(usecols)).astype("string")
    finally:
        workbook.close()


def safe_local_acceptance_path(path: str | os.PathLike[str]) -> Path:
    """Solo para CLI/tests locales; esta función nunca se expone en la API."""
    resolved = Path(path).resolve(strict=True)
    if resolved.suffix.lower() not in {".csv", ".xlsx"}:
        raise ValueError("Formato de fuente no soportado.")
    return resolved


def upload_consolidation_artifact(
    local_path: Path,
    storage_path: str,
    user_id: str,
    settings: Settings | None = None,
) -> None:
    """Sube un artefacto inmutable; un objeto existente no se reemplaza."""
    cfg = settings or get_settings()
    normalized = normalize_user_storage_path(storage_path, user_id)
    encoded = "/".join(quote(part, safe="") for part in normalized.split("/"))
    url = f"{cfg.supabase_url.rstrip('/')}/storage/v1/object/{cfg.supabase_storage_bucket}/{encoded}"
    headers = {
        "Authorization": f"Bearer {cfg.supabase_service_role_key}",
        "apikey": cfg.supabase_service_role_key,
        "Content-Type": "application/octet-stream",
        "x-upsert": "false",
        "Content-Length": str(local_path.stat().st_size),
    }
    with local_path.open("rb") as content:
        try:
            response = httpx.post(url, headers=headers, content=content, timeout=300)
        except httpx.HTTPError as exc:
            raise HTTPException(502, f"No se pudo guardar el artefacto: {exc.__class__.__name__}.") from exc
    if response.status_code == 409:
        raise HTTPException(409, "El artefacto inmutable ya existe.")
    if response.status_code not in {200, 201}:
        raise HTTPException(502, "Storage no pudo guardar el artefacto de consolidación.")
