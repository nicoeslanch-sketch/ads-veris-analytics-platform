"""Endpoints del pipeline de datos (SPEC §6). Todos exigen JWT de Supabase.

Cada endpoint acepta el archivo de dos formas:
- `file` (multipart): para archivos pequeños o desarrollo local.
- `storage_path` (form): ruta dentro del bucket de Supabase Storage; la API
  descarga el archivo con la service_role key (flujo preferido en producción).

El trabajo pesado (descarga de Storage y pandas) es síncrono y corre en el
threadpool (`run_in_threadpool`): así el event loop queda libre y varios
usuarios pueden procesar archivos a la vez sin bloquearse entre ellos.
"""

import io
import json
import os
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from ..auth import AuthenticatedUser, get_current_user
from ..engine.clean import analyze_and_clean
from ..engine.loader import UnsupportedFileError, load_dataframe
from ..engine.mapping import detect_column_roles
from ..engine.metrics import compute_metrics
from ..engine.standardize import standardize_dataframe
from ..storage import download_from_storage

router = APIRouter()

MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # multipart es solo para archivos pequeños
PREVIEW_ROWS = 5


def _check_storage_ownership(storage_path: str, user: AuthenticatedUser) -> None:
    """El bucket organiza los archivos por carpeta {user_id}/...; la API descarga
    con la service_role key (salta RLS), así que la propiedad se valida aquí."""
    normalized = storage_path.lstrip("/")
    if not normalized.startswith(f"{user.id}/"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a ese archivo.",
        )


async def _read_input(
    file: UploadFile | None,
    storage_path: str | None,
    user: AuthenticatedUser,
) -> tuple[str, bytes]:
    if file is not None:
        content = await file.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="El archivo supera los 15 MB. Súbelo a Supabase Storage y envía storage_path.",
            )
        return file.filename or "archivo.csv", content
    if storage_path:
        _check_storage_ownership(storage_path, user)
        content = await run_in_threadpool(download_from_storage, storage_path)
        return os.path.basename(storage_path), content
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


# ── Trabajo pesado con pandas: SIEMPRE fuera del event loop ─────────────────


def _standardize_sync(filename: str, content: bytes) -> dict:
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


def _clean_sync(filename: str, content: bytes, rules: dict, apply: bool) -> dict:
    df_original = _load_or_400(filename, content)
    result = analyze_and_clean(df_original, rules, apply)
    result.pop("_df_limpio", None)
    result["archivo"] = filename
    return result


def _clean_download_sync(filename: str, content: bytes, rules: dict, fmt: str) -> tuple[bytes, str, str]:
    from ..engine.standardize import is_missing

    result = analyze_and_clean(_load_or_400(filename, content), rules, apply=True)
    df = result["_df_limpio"].copy()
    column_types: dict = result["column_types"]
    col_role = {col_name: role for role, col_name in result["mapeo"].items()}
    stem = re.sub(r"[^\w\-]", "_", os.path.splitext(filename)[0])

    _ROLE_MSG: dict[str, str] = {
        "fecha": "SIN FECHA",
        "monto": "SIN MONTO",
        "costo": "SIN COSTO",
        "cantidad": "SIN CANTIDAD",
        "cliente": "SIN CLIENTE",
        "producto": "SIN PRODUCTO",
        "categoria": "SIN CATEGORIA",
        "canal": "SIN CANAL",
        "sucursal": "SIN SUCURSAL",
        "vendedor": "SIN VENDEDOR",
    }
    DATE_MARKER = "FECHA INVALIDA - REVISAR"
    total = max(len(df), 1)

    yellow: dict[tuple[int, str], str] = {}
    red: dict[tuple[int, str], str] = {}

    for col in df.columns:
        ctype = column_types.get(col, "texto")
        role = col_role.get(col)
        vals = list(df[col])
        fill_rate = sum(1 for v in vals if not is_missing(str(v))) / total

        for row_idx, val in enumerate(vals):
            if not is_missing(str(val)):
                continue
            if ctype == "fecha":
                yellow[(row_idx, col)] = DATE_MARKER
            elif fill_rate >= 0.7:
                msg = _ROLE_MSG.get(role) if role else None
                red[(row_idx, col)] = msg or "VACIO - " + col.upper()

    for (r, c), msg in yellow.items():
        df.at[r, c] = msg
    for (r, c), msg in red.items():
        df.at[r, c] = msg

    if fmt == "csv":
        return (
            df.to_csv(index=False, sep=";").encode("utf-8-sig"),
            f"{stem}_limpio.csv",
            "text/csv; charset=utf-8",
        )

    import openpyxl
    from openpyxl.styles import PatternFill

    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)

    wb = openpyxl.load_workbook(buf)
    ws = wb.active
    col_list = list(df.columns)
    YELLOW_FILL = PatternFill(start_color="FFEB3B", end_color="FFEB3B", fill_type="solid")
    RED_FILL = PatternFill(start_color="FFCDD2", end_color="FFCDD2", fill_type="solid")

    for (r, c) in yellow:
        ws.cell(row=r + 2, column=col_list.index(c) + 1).fill = YELLOW_FILL
    for (r, c) in red:
        ws.cell(row=r + 2, column=col_list.index(c) + 1).fill = RED_FILL

    buf2 = io.BytesIO()
    wb.save(buf2)
    buf2.seek(0)
    return (
        buf2.getvalue(),
        f"{stem}_limpio.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )




def _metrics_sync(
    filename: str,
    content: bytes,
    mapping: dict | None,
    date_from: str | None,
    date_to: str | None,
) -> dict:
    df_original = _load_or_400(filename, content)
    # Las métricas siempre se calculan sobre datos estandarizados y limpios.
    result = analyze_and_clean(df_original, rules=None, apply=True)
    df_clean = result["_df_limpio"]
    computed = compute_metrics(df_clean, mapping, date_from=date_from, date_to=date_to)
    computed["archivo"] = filename
    computed["calidad_datos"] = result["resumen"]["calidad_despues"]
    return computed


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/standardize")
async def standardize(
    file: UploadFile | None = File(None),
    storage_path: str | None = Form(None),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    filename, content = await _read_input(file, storage_path, user)
    return await run_in_threadpool(_standardize_sync, filename, content)


@router.post("/clean")
async def clean(
    file: UploadFile | None = File(None),
    storage_path: str | None = Form(None),
    rules: str | None = Form(None),
    apply: bool = Form(False),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    filename, content = await _read_input(file, storage_path, user)
    rules_dict = _parse_json_field(rules, "rules")
    return await run_in_threadpool(_clean_sync, filename, content, rules_dict, apply)


@router.post("/clean/download")
async def clean_download(
    file: UploadFile | None = File(None),
    storage_path: str | None = Form(None),
    rules: str | None = Form(None),
    fmt: str = Form("xlsx"),
    user: AuthenticatedUser = Depends(get_current_user),
) -> StreamingResponse:
    """Devuelve el dataset con la limpieza aplicada como archivo descargable (xlsx o csv)."""
    if fmt not in ("xlsx", "csv"):
        fmt = "xlsx"
    filename, content = await _read_input(file, storage_path, user)
    rules_dict = _parse_json_field(rules, "rules")
    file_bytes, out_name, media_type = await run_in_threadpool(
        _clean_download_sync, filename, content, rules_dict, fmt
    )
    return StreamingResponse(
        iter([file_bytes]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{out_name}"'},
    )


@router.post("/metrics")
async def metrics(
    file: UploadFile | None = File(None),
    storage_path: str | None = Form(None),
    mapping: str | None = Form(None),
    date_from: str | None = Form(None),
    date_to: str | None = Form(None),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    filename, content = await _read_input(file, storage_path, user)
    mapping_dict = _parse_json_field(mapping, "mapping") or None
    return await run_in_threadpool(
        _metrics_sync, filename, content, mapping_dict, date_from, date_to
    )
