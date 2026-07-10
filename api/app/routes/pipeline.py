"""Endpoints del pipeline de datos (SPEC §6 + Fase 7). Todos exigen JWT de Supabase.

Cada endpoint acepta el archivo de dos formas:
- `file` (multipart): para archivos pequeños o desarrollo local.
- `storage_path` (form): ruta dentro del bucket de Supabase Storage; la API
  descarga el archivo con la service_role key (flujo preferido en producción).

El trabajo pesado (descarga de Storage y pandas) es síncrono y corre en el
threadpool (`run_in_threadpool`): así el event loop queda libre y varios
usuarios pueden procesar archivos a la vez sin bloquearse entre ellos.

Fase 7:
- **Caché del pipeline** (§5.7): estandarizar+limpiar el mismo archivo con las
  mismas reglas se calcula UNA vez; cambiar el periodo del dashboard ya no
  re-corre todo el motor (gran ahorro de CPU en Render).
- **POST /clean/assisted**: limpieza dirigida por variables del usuario
  (Plan Analista/Gold, 2/mes + addons). La interpretación de instrucciones es
  determinista hoy; su costura IA vive en engine/directed.py.
- `mapping` (roles corregidos por el usuario, §5.10) y `scope` (columnas
  objetivo) disponibles en /clean, /clean/download y /metrics.
- Costura de refinado IA (§5.13) cableada tras la limpieza, apagada por flag.
"""

import hashlib
import io
import json
import os
import re
import threading
from collections import OrderedDict

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from .. import quota
from ..auth import AuthenticatedUser, get_current_user
from ..capabilities import Capability, require_capability_for_user
from ..config import Settings, get_settings
from ..engine.ai_refine import refine_with_ai
from ..engine.clean import analyze_and_clean
from ..engine.directed import (
    MAX_INSTRUCTIONS_CHARS,
    interpret_cleaning_instructions,
)
from ..engine.export import safe_export_dataframe
from ..engine.loader import UnsupportedFileError, load_dataframe_with_report
from ..engine.ai_classifier import classify_columns_with_ai
from ..engine.mapping import detect_column_roles, detect_columns_extended
from ..engine.metrics import compute_metrics
from ..engine.standardize import normalize_headers, standardize_dataframe
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
        return load_dataframe_with_report(filename, content)
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


# ── Caché del pipeline (§5.7) ─────────────────────────────────────────────────
# Un mismo archivo con las mismas reglas/mapeo/alcance se procesa UNA vez.
# LRU pequeño y con tope de celdas: protege la memoria de Render.

_CACHE_LOCK = threading.Lock()
_CLEAN_CACHE: "OrderedDict[tuple, dict]" = OrderedDict()
# Dimensionado para Render free (512 MB): cada entrada guarda un DataFrame de
# strings (~60–100 bytes/celda). 3 × 600k celdas ≈ 150 MB en el peor caso.
_CACHE_MAX_ENTRIES = 3
_CACHE_MAX_CELLS = 600_000


def _cache_key(content: bytes, rules: dict | None, apply: bool, mapping: dict | None, scope: dict | None) -> tuple:
    return (
        hashlib.sha1(content).digest(),
        json.dumps(rules or {}, sort_keys=True),
        apply,
        json.dumps(mapping or {}, sort_keys=True),
        json.dumps(scope or {}, sort_keys=True),
    )


def _analyze_cached(
    filename: str,
    content: bytes,
    rules: dict | None,
    apply: bool,
    mapping: dict | None = None,
    scope: dict | None = None,
) -> dict:
    """analyze_and_clean con caché. El dict cacheado JAMÁS se muta: los
    endpoints construyen su respuesta con una copia superficial."""
    key = _cache_key(content, rules, apply, mapping, scope)
    with _CACHE_LOCK:
        cached = _CLEAN_CACHE.get(key)
        if cached is not None:
            _CLEAN_CACHE.move_to_end(key)
            return cached

    df, load_report = _load_or_400(filename, content)
    result = analyze_and_clean(df, rules, apply, mapping=mapping, scope=scope)
    result["avisos"] = list(load_report.get("avisos", [])) + list(result.get("avisos", []))
    result["carga"] = {
        "hoja_usada": load_report.get("hoja_usada"),
        "hojas_disponibles": load_report.get("hojas_disponibles", []),
        "filas_titulo_omitidas": load_report.get("filas_titulo_omitidas", 0),
    }

    # Costura de refinado IA (§5.13): preparada, apagada por flag.
    settings = get_settings()
    if apply and settings.ai_refine_enabled and result.get("_df_limpio") is not None:
        refined, notas = refine_with_ai(result["_df_limpio"], result.get("reporte_calidad", {}))
        result["_df_limpio"] = refined
        if notas:
            result["avisos"] = result["avisos"] + [f"IA: {n}" for n in notas]

    rows = result["resumen"]["filas_despues" if apply else "filas_antes"]
    cols = result["resumen"]["columnas_despues" if apply else "columnas_antes"]
    if rows * max(cols, 1) <= _CACHE_MAX_CELLS:
        with _CACHE_LOCK:
            _CLEAN_CACHE[key] = result
            _CLEAN_CACHE.move_to_end(key)
            while len(_CLEAN_CACHE) > _CACHE_MAX_ENTRIES:
                _CLEAN_CACHE.popitem(last=False)
    return result


def _public_clean_response(result: dict, filename: str, extra: dict | None = None) -> dict:
    """Copia sin el DataFrame interno (el dict cacheado no se toca)."""
    response = {k: v for k, v in result.items() if k != "_df_limpio"}
    response["archivo"] = filename
    if extra:
        response.update(extra)
    return response


# ── Trabajo pesado con pandas: SIEMPRE fuera del event loop ─────────────────


def _standardize_sync(filename: str, content: bytes) -> dict:
    df_original, load_report = _load_or_400(filename, content)
    df_std, report = standardize_dataframe(df_original)

    # Fase 9: mapeo universal — rol extendido (64 roles) por columna según el
    # diccionario de palabras clave, con método y confianza del match.
    extended = detect_columns_extended(list(df_std.columns))
    settings = get_settings()
    if settings.ai_classifier_enabled:
        # Costura IA (apagada por defecto): clasificar lo que el diccionario
        # no reconoció. Hoy el stub devuelve {}.
        sin_match = [c for c in df_std.columns if c not in extended]
        if sin_match:
            extended.update(classify_columns_with_ai(sin_match, df_std))

    # Vista previa antes/después con los mismos encabezados normalizados.
    before = df_original.copy()
    before.columns = df_std.columns
    return {
        "archivo": filename,
        "filas": len(df_std),
        "columnas": len(df_std.columns),
        "column_types": report["column_types"],
        "column_confidence": report["column_confidence"],
        "mapeo": detect_column_roles(list(df_std.columns)),
        "mapeo_extendido": {col: match.to_dict() for col, match in extended.items()},
        "cambios": report["cambios"],
        "avisos": load_report.get("avisos", []),
        "carga": {
            "hoja_usada": load_report.get("hoja_usada"),
            "hojas_disponibles": load_report.get("hojas_disponibles", []),
            "filas_titulo_omitidas": load_report.get("filas_titulo_omitidas", 0),
        },
        "preview": {
            "columnas": list(df_std.columns),
            "antes": [[str(v) for v in row] for row in before.head(PREVIEW_ROWS).itertuples(index=False, name=None)],
            "despues": [[str(v) for v in row] for row in df_std.head(PREVIEW_ROWS).itertuples(index=False, name=None)],
        },
    }


def _clean_sync(
    filename: str,
    content: bytes,
    rules: dict,
    apply: bool,
    mapping: dict | None = None,
    scope: dict | None = None,
    extra: dict | None = None,
) -> dict:
    result = _analyze_cached(filename, content, rules, apply, mapping=mapping, scope=scope)
    return _public_clean_response(result, filename, extra)


def _extract_columns_sync(filename: str, content: bytes) -> tuple[list[str], dict[str, str]]:
    """Columnas normalizadas + roles detectados, sin correr el motor completo.
    Se usa para interpretar las instrucciones ANTES de gastar CPU (y cupo)."""
    df, _ = _load_or_400(filename, content)
    normalize_headers(df)
    columns = list(df.columns)
    return columns, detect_column_roles(columns)


def _clean_download_sync(
    filename: str,
    content: bytes,
    rules: dict,
    fmt: str,
    mapping: dict | None = None,
    scope: dict | None = None,
) -> tuple[bytes, str, str]:
    from ..engine.standardize import is_missing

    result = _analyze_cached(filename, content, rules, apply=True, mapping=mapping, scope=scope)
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

    df_export = safe_export_dataframe(df)

    if fmt == "csv":
        return (
            df_export.to_csv(index=False, sep=";").encode("utf-8-sig"),
            f"{stem}_limpio.csv",
            "text/csv; charset=utf-8",
        )

    import openpyxl
    from openpyxl.styles import PatternFill

    buf = io.BytesIO()
    df_export.to_excel(buf, index=False, engine="openpyxl")
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
    # Las métricas siempre se calculan sobre datos estandarizados y limpios.
    # Con el caché (§5.7), cambiar el periodo NO re-corre el pipeline completo.
    result = _analyze_cached(filename, content, rules=None, apply=True, mapping=mapping)
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
    mapping: str | None = Form(None),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    filename, content = await _read_input(file, storage_path, user)
    rules_dict = _parse_json_field(rules, "rules")
    mapping_dict = _parse_json_field(mapping, "mapping") or None
    return await run_in_threadpool(
        _clean_sync, filename, content, rules_dict, apply, mapping_dict
    )


@router.post("/clean/assisted")
async def clean_assisted(
    file: UploadFile | None = File(None),
    storage_path: str | None = Form(None),
    instructions: str = Form(...),
    rules: str | None = Form(None),
    mapping: str | None = Form(None),
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Limpieza dirigida por variables del usuario (Fase 7 §3).

    Flujo: capacidad (Plan Analista/Gold) → cupo (2/mes + addons) →
    interpretar instrucciones (costura IA determinista) → correr el motor
    dirigido → registrar el consumo SOLO si corrió OK. Si las instrucciones
    no se reconocen, responde 422 y el intento NO se descuenta."""
    require_capability_for_user(user.id, Capability.AI_CLEANING, settings)

    instructions = (instructions or "").strip()
    if not instructions:
        raise HTTPException(status_code=422, detail="Escribe qué variables o columnas quieres limpiar.")
    if len(instructions) > MAX_INSTRUCTIONS_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"Las instrucciones superan los {MAX_INSTRUCTIONS_CHARS} caracteres. Sé breve y específico.",
        )

    filename, content = await _read_input(file, storage_path, user)
    rules_dict = _parse_json_field(rules, "rules")
    mapping_dict = _parse_json_field(mapping, "mapping") or None

    # 1) Cupo ANTES de gastar CPU (lanza 429 con CTA a Planes si no quedan intentos).
    quota_info = await run_in_threadpool(quota.check_cleaning_quota, user.id, settings)

    # 2) Interpretar instrucciones sobre las columnas reales del archivo.
    columns, auto_roles = await run_in_threadpool(_extract_columns_sync, filename, content)
    roles = {**auto_roles, **(mapping_dict or {})}
    plan = interpret_cleaning_instructions(instructions, columns, roles)
    if not plan.reconocido:
        raise HTTPException(
            status_code=422,
            detail=" ".join(plan.avisos) + " El intento NO se descontó de tu cupo.",
        )

    # 3) Correr el motor con las reglas y el alcance dirigidos.
    merged_rules = {**rules_dict, **plan.reglas_forzadas}
    scope = {"incluir": plan.columnas_incluir, "excluir": plan.columnas_excluir}
    result = await run_in_threadpool(
        _clean_sync, filename, content, merged_rules, True, mapping_dict, scope
    )

    # 4) Registrar el consumo (best-effort) SOLO tras un run exitoso.
    consume_addon = bool(quota_info and quota_info.get("consume_addon"))
    await run_in_threadpool(quota.record_cleaning_usage, user.id, settings, consume_addon)

    if quota_info:
        base = quota_info["base"]
        usadas = quota_info["usadas_mes"] + 1
        addons = quota_info["addons"] - (1 if consume_addon else 0)
        cupo = {
            "disponible": True,
            "usadas_mes": usadas,
            "base": base,
            "addons": max(addons, 0),
            "restantes": max(base - usadas, 0) + max(addons, 0),
        }
    else:
        cupo = {"disponible": False, "usadas_mes": 0, "base": settings.ai_cleaning_monthly_limit, "addons": 0}

    result["dirigida"] = {"instrucciones": instructions, **plan.to_dict(), "cupo": cupo}
    return result


@router.post("/clean/download")
async def clean_download(
    file: UploadFile | None = File(None),
    storage_path: str | None = Form(None),
    rules: str | None = Form(None),
    fmt: str = Form("xlsx"),
    format: str | None = Form(None),
    mapping: str | None = Form(None),
    scope: str | None = Form(None),
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Devuelve el dataset con la limpieza aplicada como archivo descargable (xlsx o csv)."""
    require_capability_for_user(
        user.id,
        Capability.DOWNLOAD_CLEAN_DATASET,
        settings,
    )
    export_format = (format or fmt).strip().lower()
    if export_format not in {"csv", "xlsx"}:
        raise HTTPException(
            status_code=422,
            detail="El campo 'fmt' debe ser 'csv' o 'xlsx'.",
        )
    filename, content = await _read_input(file, storage_path, user)
    rules_dict = _parse_json_field(rules, "rules")
    mapping_dict = _parse_json_field(mapping, "mapping") or None
    scope_dict = _parse_json_field(scope, "scope") or None
    file_bytes, out_name, media_type = await run_in_threadpool(
        _clean_download_sync, filename, content, rules_dict, export_format, mapping_dict, scope_dict
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
