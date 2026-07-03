"""Endpoints del pipeline de datos (SPEC §6). Todos exigen JWT de Supabase.

Cada endpoint acepta el archivo de dos formas:
- `file` (multipart): para archivos pequeños o desarrollo local.
- `storage_path` (form): ruta dentro del bucket de Supabase Storage; la API
  descarga el archivo con la service_role key (flujo preferido en producción).
"""

import json
import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from ..auth import get_current_user
from ..engine.clean import analyze_and_clean
from ..engine.loader import UnsupportedFileError, load_dataframe
from ..engine.mapping import detect_column_roles
from ..engine.metrics import compute_metrics
from ..engine.standardize import standardize_dataframe
from ..storage import download_from_storage

router = APIRouter(dependencies=[Depends(get_current_user)])

MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # multipart es solo para archivos pequeños
PREVIEW_ROWS = 5


async def _read_input(file: UploadFile | None, storage_path: str | None) -> tuple[str, bytes]:
    if file is not None:
        content = await file.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="El archivo supera los 15 MB. Súbelo a Supabase Storage y envía storage_path.",
            )
        return file.filename or "archivo.csv", content
    if storage_path:
        return os.path.basename(storage_path), download_from_storage(storage_path)
    raise HTTPException(
        status_code=422,
        detail="Envía un archivo (campo 'file') o una ruta de Storage (campo 'storage_path').",
    )


def _load_or_400(filename: str, content: bytes):
    try:
        return load_dataframe(filename, content)
    except UnsupportedFileError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _parse_json_field(raw: str | None, field: str) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=422,
            detail=f"El campo '{field}' debe ser JSON válido.",
        )
    if not isinstance(value, dict):
        raise HTTPException(
            status_code=422,
            detail=f"El campo '{field}' debe ser un objeto JSON.",
        )
    return value


@router.post("/standardize")
async def standardize(
    file: UploadFile | None = File(None),
    storage_path: str | None = Form(None),
) -> dict:
    filename, content = await _read_input(file, storage_path)
    df_original = _load_or_400(filename, content)
    df_std, report = standardize_dataframe(df_original)

    # Vista previa antes/después con los mismos encabezados normalizados.
    before = df_original.copy()
    before.columns = df_std.columns
    return {
        "archivo": filename,
        "filas": len(df_std),
        "columnas": len(df_std.columns),
        "column_types": report["column_types"],
        "mapeo": detect_column_roles(list(df_std.columns)),
        "cambios": report["cambios"],
        "preview": {
            "columnas": list(df_std.columns),
            "antes": [[str(v) for v in row] for row in before.head(PREVIEW_ROWS).itertuples(index=False, name=None)],
            "despues": [[str(v) for v in row] for row in df_std.head(PREVIEW_ROWS).itertuples(index=False, name=None)],
        },
    }


@router.post("/clean")
async def clean(
    file: UploadFile | None = File(None),
    storage_path: str | None = Form(None),
    rules: str | None = Form(None),
    apply: bool = Form(False),
) -> dict:
    filename, content = await _read_input(file, storage_path)
    df_original = _load_or_400(filename, content)
    result = analyze_and_clean(df_original, _parse_json_field(rules, "rules"), apply)
    result.pop("_df_limpio", None)
    result["archivo"] = filename
    return result


@router.post("/metrics")
async def metrics(
    file: UploadFile | None = File(None),
    storage_path: str | None = Form(None),
    mapping: str | None = Form(None),
    date_from: str | None = Form(None),
    date_to: str | None = Form(None),
) -> dict:
    filename, content = await _read_input(file, storage_path)
    df_original = _load_or_400(filename, content)
    # Las métricas siempre se calculan sobre datos estandarizados y limpios.
    result = analyze_and_clean(df_original, rules=None, apply=True)
    df_clean = result["_df_limpio"]
    mapping_dict = _parse_json_field(mapping, "mapping") or None
    computed = compute_metrics(df_clean, mapping_dict, date_from=date_from, date_to=date_to)
    computed["archivo"] = filename
    computed["calidad_datos"] = result["resumen"]["calidad_despues"]
    return computed
