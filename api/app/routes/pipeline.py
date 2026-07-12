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
from urllib.parse import unquote

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
from ..engine.metrics import compute_metrics, detect_currency
from ..engine.standardize import normalize_headers, standardize_dataframe
from ..storage import download_from_storage

router = APIRouter()

MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # multipart es solo para archivos pequeños
PREVIEW_ROWS = 5


def _normalize_user_storage_path(storage_path: str, user: AuthenticatedUser) -> str:
    """El bucket organiza los archivos por carpeta {user_id}/...; la API descarga
    con la service_role key (salta RLS), así que la propiedad se valida aquí."""
    raw = storage_path.strip()
    if not raw:
        raise HTTPException(status_code=422, detail="storage_path vacio.")

    normalized = raw.lstrip("/")
    decoded = normalized
    for _ in range(3):
        next_decoded = unquote(decoded)
        if next_decoded == decoded:
            break
        decoded = next_decoded

    parts = decoded.split("/")
    invalid = (
        "\\" in normalized
        or decoded != normalized
        or "%" in decoded
        or len(parts) < 2
        or parts[0] != user.id
        or any(part in {"", ".", ".."} for part in parts)
    )
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a ese archivo.",
        )
    return "/".join(parts)


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
        safe_storage_path = _normalize_user_storage_path(storage_path, user)
        content = await run_in_threadpool(download_from_storage, safe_storage_path)
        return os.path.basename(safe_storage_path), content
    raise HTTPException(
        status_code=422,
        detail="Envía un archivo (campo 'file') o una ruta de Storage (campo 'storage_path').",
    )


def _load_or_400(filename: str, content: bytes, sheet: str | None = None):
    try:
        return load_dataframe_with_report(filename, content, sheet=sheet)
    except UnsupportedFileError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _clean_sheet_param(sheet: str | None) -> str | None:
    """Nombre de hoja elegido por el usuario (Fase 10 §8.3), saneado."""
    if not sheet:
        return None
    value = sheet.strip()
    if len(value) > 100:
        raise HTTPException(status_code=422, detail="Nombre de hoja demasiado largo.")
    return value or None


def _parse_json_field(raw: str | None, field: str) -> dict:
    if not raw:
        return {}
    if len(raw) > 20_000:
        raise HTTPException(
            status_code=422,
            detail=f"El campo '{field}' es demasiado grande.",
        )
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


# ── Validación estricta de entradas (Fase 10 §14.1) ─────────────────────────
# La UI ya construye estos objetos bien, pero un cliente directo puede
# saltársela: claves desconocidas o tipos incorrectos → 422 claro.

_VALID_RULE_KEYS = {
    "fechas", "textos", "duplicados", "tipos", "nulos",
    "columnas_vacias", "fuera_de_rango",
}
_VALID_MAPPING_ROLES = {
    "fecha", "cliente", "producto", "categoria", "monto", "costo",
    "cantidad", "canal", "sucursal", "vendedor",
}


def _validate_rules(rules: dict) -> dict:
    for key, value in rules.items():
        if key not in _VALID_RULE_KEYS:
            raise HTTPException(
                status_code=422,
                detail=f"Regla desconocida: '{key}'. Válidas: {', '.join(sorted(_VALID_RULE_KEYS))}.",
            )
        if not isinstance(value, bool):
            raise HTTPException(
                status_code=422,
                detail=f"La regla '{key}' debe ser true o false.",
            )
    return rules


def _validate_mapping(mapping: dict | None) -> dict | None:
    if not mapping:
        return mapping
    if len(mapping) > 30:
        raise HTTPException(status_code=422, detail="El mapeo tiene demasiadas entradas.")
    for role, col in mapping.items():
        if str(role).strip().lower() not in _VALID_MAPPING_ROLES:
            raise HTTPException(
                status_code=422,
                detail=f"Rol de mapeo desconocido: '{role}'.",
            )
        if col is not None and not isinstance(col, str):
            raise HTTPException(
                status_code=422,
                detail=f"El mapeo del rol '{role}' debe ser el nombre de una columna (texto).",
            )
    return mapping


def _validate_scope(scope: dict | None) -> dict | None:
    if not scope:
        return scope
    for key in scope:
        if key not in {"incluir", "excluir"}:
            raise HTTPException(
                status_code=422,
                detail=f"Clave de alcance desconocida: '{key}' (usa 'incluir'/'excluir').",
            )
    for key in ("incluir", "excluir"):
        values = scope.get(key)
        if values is None:
            continue
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise HTTPException(
                status_code=422,
                detail=f"'{key}' debe ser una lista de nombres de columna.",
            )
        if len(values) > 200:
            raise HTTPException(status_code=422, detail=f"'{key}' tiene demasiadas columnas.")
    return scope


# ── Caché del pipeline (§5.7 + Fase 11) ──────────────────────────────────────
# Un mismo archivo con las mismas reglas/mapeo/alcance se procesa UNA vez.
#
# Fase 11: el tope ANTIGUO era por entrada (600k celdas) y excluía justamente
# a los archivos grandes — un 50.000×20 se reprocesaba completo en CADA
# módulo (Resumen, Explorar, Reportes, retomar…), que era la lentitud
# reportada. Ahora el límite es un PRESUPUESTO TOTAL de celdas: caben varias
# bases chicas o una grande, y se desalojan las más antiguas (LRU) hasta que
# la nueva quepa. Presupuesto para Render 512 MB: 2,4M celdas × ~80 B ≈ 190 MB
# en el peor caso.

_CACHE_LOCK = threading.Lock()
_CLEAN_CACHE: "OrderedDict[tuple, dict]" = OrderedDict()
_CACHE_TOTAL_CELL_BUDGET = 2_400_000
# Una entrada individual jamás puede superar el presupuesto completo
# (el loader ya limita a 200.000 filas).
_CACHE_MAX_ENTRY_CELLS = 2_400_000


def _cache_entry_cells(result: dict, apply: bool) -> int:
    rows = result["resumen"]["filas_despues" if apply else "filas_antes"]
    cols = result["resumen"]["columnas_despues" if apply else "columnas_antes"]
    return rows * max(cols, 1)


def _cache_store(key: tuple, result: dict, apply: bool) -> None:
    cells = _cache_entry_cells(result, apply)
    if cells > _CACHE_MAX_ENTRY_CELLS:
        return
    with _CACHE_LOCK:
        _CLEAN_CACHE[key] = result
        _CLEAN_CACHE.move_to_end(key)
        # Desalojar LRU hasta caber en el presupuesto total.
        def total() -> int:
            return sum(
                _cache_entry_cells(r, bool(r["resumen"]["aplicado"]))
                for r in _CLEAN_CACHE.values()
            )
        while len(_CLEAN_CACHE) > 1 and total() > _CACHE_TOTAL_CELL_BUDGET:
            _CLEAN_CACHE.popitem(last=False)


def _cache_key(
    content: bytes,
    rules: dict | None,
    apply: bool,
    mapping: dict | None,
    scope: dict | None,
    sheet: str | None = None,
) -> tuple:
    return (
        hashlib.sha1(content).digest(),
        json.dumps(rules or {}, sort_keys=True),
        apply,
        json.dumps(mapping or {}, sort_keys=True),
        json.dumps(scope or {}, sort_keys=True),
        sheet or "",
    )


def _analyze_cached(
    filename: str,
    content: bytes,
    rules: dict | None,
    apply: bool,
    mapping: dict | None = None,
    scope: dict | None = None,
    sheet: str | None = None,
) -> dict:
    """analyze_and_clean con caché. El dict cacheado JAMÁS se muta: los
    endpoints construyen su respuesta con una copia superficial."""
    key = _cache_key(content, rules, apply, mapping, scope, sheet)
    with _CACHE_LOCK:
        cached = _CLEAN_CACHE.get(key)
        if cached is not None:
            _CLEAN_CACHE.move_to_end(key)
            return cached

    df, load_report = _load_or_400(filename, content, sheet=sheet)

    # Moneda (Fase 10 §4.4): se detecta sobre los valores CRUDOS — la
    # estandarización quita los símbolos y después ya no hay evidencia.
    raw_roles = {**detect_column_roles(list(df.columns)), **(mapping or {})}
    monto_col = raw_roles.get("monto")
    currency = detect_currency(df[monto_col] if monto_col in df.columns else None)

    result = analyze_and_clean(df, rules, apply, mapping=mapping, scope=scope)
    result["_moneda"] = currency
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

    _cache_store(key, result, apply)
    return result


def _public_clean_response(result: dict, filename: str, extra: dict | None = None) -> dict:
    """Copia sin los campos internos "_" (el dict cacheado no se toca)."""
    response = {k: v for k, v in result.items() if not k.startswith("_")}
    response["archivo"] = filename
    if extra:
        response.update(extra)
    return response


# ── Trabajo pesado con pandas: SIEMPRE fuera del event loop ─────────────────


def _standardize_sync(filename: str, content: bytes, sheet: str | None = None) -> dict:
    df_original, load_report = _load_or_400(filename, content, sheet=sheet)
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
        "avisos": list(load_report.get("avisos", [])) + list(report.get("avisos", [])),
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
    sheet: str | None = None,
) -> dict:
    result = _analyze_cached(
        filename, content, rules, apply, mapping=mapping, scope=scope, sheet=sheet
    )
    return _public_clean_response(result, filename, extra)


def _extract_columns_sync(
    filename: str, content: bytes, sheet: str | None = None
) -> tuple[list[str], dict[str, str]]:
    """Columnas normalizadas + roles detectados, sin correr el motor completo.
    Se usa para interpretar las instrucciones ANTES de gastar CPU (y cupo)."""
    df, _ = _load_or_400(filename, content, sheet=sheet)
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
    sheet: str | None = None,
) -> tuple[bytes, str, str]:
    from ..engine.standardize import is_missing

    result = _analyze_cached(
        filename, content, rules, apply=True, mapping=mapping, scope=scope, sheet=sheet
    )
    df = result["_df_limpio"].copy()
    column_types: dict = result["column_types"]
    col_role = {col_name: role for role, col_name in result["mapeo"].items()}
    stem = re.sub(r"[^\w\-]", "_", os.path.splitext(filename)[0])

    # Fase 10 §6.5: la base limpia se descarga SIN textos de revisión dentro de
    # los datos — una columna de fecha sigue siendo fecha y una numérica sigue
    # siendo numérica (importable en cualquier sistema). Las celdas problemáticas
    # se marcan con color y el DETALLE va en la hoja "Observaciones".
    _ROLE_LABEL: dict[str, str] = {
        "fecha": "fecha",
        "monto": "monto",
        "costo": "costo",
        "cantidad": "cantidad",
        "cliente": "cliente",
        "producto": "producto",
        "categoria": "categoría",
        "canal": "canal",
        "sucursal": "sucursal",
        "vendedor": "vendedor",
    }
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
                yellow[(row_idx, col)] = (
                    "Fecha faltante o que no se pudo interpretar: revisar."
                )
            elif fill_rate >= 0.7:
                etiqueta = _ROLE_LABEL.get(role, col) if role else col
                red[(row_idx, col)] = (
                    f"Dato faltante en una columna casi completa ({etiqueta})."
                )

    df_export = safe_export_dataframe(df)

    if fmt == "csv":
        # CSV limpio de verdad: sin marcadores dentro de los datos.
        return (
            df_export.to_csv(index=False, sep=";").encode("utf-8-sig"),
            f"{stem}_limpio.csv",
            "text/csv; charset=utf-8",
        )

    import openpyxl
    from openpyxl.styles import Font, PatternFill

    buf = io.BytesIO()
    df_export.to_excel(buf, index=False, engine="openpyxl", sheet_name="Datos_limpios")
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

    # Hoja de Observaciones: fila, columna, problema (los datos quedan intactos).
    observations = sorted(
        [(r, c, "revisar", msg) for (r, c), msg in yellow.items()]
        + [(r, c, "faltante", msg) for (r, c), msg in red.items()],
        key=lambda item: (item[0], item[1]),
    )
    ws_obs = wb.create_sheet("Observaciones")
    ws_obs.append(["Fila", "Columna", "Tipo", "Detalle"])
    for cell in ws_obs[1]:
        cell.font = Font(bold=True)
    if observations:
        for row_idx, col, kind, msg in observations:
            # +2: fila 1 = encabezados de la hoja de datos.
            ws_obs.append([row_idx + 2, col, kind, msg])
    else:
        ws_obs.append(["—", "—", "—", "Sin observaciones: la base quedó completa."])
    ws_obs.column_dimensions["B"].width = 24
    ws_obs.column_dimensions["D"].width = 64

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
    sheet: str | None = None,
) -> dict:
    # Las métricas siempre se calculan sobre datos estandarizados y limpios.
    # Con el caché (§5.7), cambiar el periodo NO re-corre el pipeline completo.
    result = _analyze_cached(
        filename, content, rules=None, apply=True, mapping=mapping, sheet=sheet
    )
    df_clean = result["_df_limpio"]
    computed = compute_metrics(
        df_clean, mapping, date_from=date_from, date_to=date_to,
        currency_hint=result.get("_moneda"),
    )
    computed["archivo"] = filename
    computed["calidad_datos"] = result["resumen"]["calidad_despues"]
    return computed


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/standardize")
async def standardize(
    file: UploadFile | None = File(None),
    storage_path: str | None = Form(None),
    sheet: str | None = Form(None),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    filename, content = await _read_input(file, storage_path, user)
    return await run_in_threadpool(
        _standardize_sync, filename, content, _clean_sheet_param(sheet)
    )


@router.post("/clean")
async def clean(
    file: UploadFile | None = File(None),
    storage_path: str | None = Form(None),
    rules: str | None = Form(None),
    apply: bool = Form(False),
    mapping: str | None = Form(None),
    sheet: str | None = Form(None),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    filename, content = await _read_input(file, storage_path, user)
    rules_dict = _validate_rules(_parse_json_field(rules, "rules"))
    mapping_dict = _validate_mapping(_parse_json_field(mapping, "mapping") or None)
    return await run_in_threadpool(
        _clean_sync, filename, content, rules_dict, apply, mapping_dict, None, None,
        _clean_sheet_param(sheet),
    )


@router.post("/clean/assisted")
async def clean_assisted(
    file: UploadFile | None = File(None),
    storage_path: str | None = Form(None),
    instructions: str = Form(...),
    rules: str | None = Form(None),
    mapping: str | None = Form(None),
    sheet: str | None = Form(None),
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
    rules_dict = _validate_rules(_parse_json_field(rules, "rules"))
    mapping_dict = _validate_mapping(_parse_json_field(mapping, "mapping") or None)
    sheet_name = _clean_sheet_param(sheet)

    # 1) Cupo ANTES de gastar CPU (lanza 429 con CTA a Planes si no quedan intentos).
    quota_info = await run_in_threadpool(quota.check_cleaning_quota, user.id, settings)

    # 2) Interpretar instrucciones sobre las columnas reales del archivo.
    columns, auto_roles = await run_in_threadpool(
        _extract_columns_sync, filename, content, sheet_name
    )
    roles = {**auto_roles, **(mapping_dict or {})}
    plan = interpret_cleaning_instructions(instructions, columns, roles)
    if not plan.reconocido:
        raise HTTPException(
            status_code=422,
            detail=" ".join(plan.avisos) + " El intento NO se descontó de tu cupo.",
        )

    # 3) Correr el motor con las reglas y el alcance dirigidos. Un alcance que
    #    queda VACÍO (las exclusiones cubren todo) jamás se reinterpreta como
    #    "todas las columnas" (Fase 10 §6.3).
    effective_scope = (set(plan.columnas_incluir) or set(columns)) - set(plan.columnas_excluir)
    if not effective_scope:
        raise HTTPException(
            status_code=422,
            detail="Tus instrucciones excluyen todas las columnas: no habría nada que "
            "limpiar. Ajusta las columnas a incluir. El intento NO se descontó de tu cupo.",
        )
    merged_rules = {**rules_dict, **plan.reglas_forzadas}
    scope = {"incluir": plan.columnas_incluir, "excluir": plan.columnas_excluir}
    result = await run_in_threadpool(
        _clean_sync, filename, content, merged_rules, True, mapping_dict, scope,
        None, sheet_name,
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
    sheet: str | None = Form(None),
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
    rules_dict = _validate_rules(_parse_json_field(rules, "rules"))
    mapping_dict = _validate_mapping(_parse_json_field(mapping, "mapping") or None)
    scope_dict = _validate_scope(_parse_json_field(scope, "scope") or None)
    file_bytes, out_name, media_type = await run_in_threadpool(
        _clean_download_sync, filename, content, rules_dict, export_format,
        mapping_dict, scope_dict, _clean_sheet_param(sheet),
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
    sheet: str | None = Form(None),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    filename, content = await _read_input(file, storage_path, user)
    mapping_dict = _validate_mapping(_parse_json_field(mapping, "mapping") or None)
    return await run_in_threadpool(
        _metrics_sync, filename, content, mapping_dict, date_from, date_to,
        _clean_sheet_param(sheet),
    )
