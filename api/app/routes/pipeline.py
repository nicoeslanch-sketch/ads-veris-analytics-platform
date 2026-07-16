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

import copy
import hashlib
import io
import json
import os
import re
import threading
from collections import OrderedDict

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from .. import quota
from ..auth import AuthenticatedUser, get_current_user
from ..capabilities import Capability, require_capability_for_user
from ..config import Settings, get_settings
from ..engine.ai_refine import refine_with_ai
from ..engine.clean import DEFAULT_RULES, analyze_and_clean
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
from ..restore_cache import (
    build_restore_snapshot,
    fetch_dataset_mapping,
    fetch_latest_cleaning_config,
    fetch_latest_restore_record,
    store_restore_snapshot,
    valid_restore_snapshot,
)
from ..storage import download_from_storage, normalize_user_storage_path

router = APIRouter()

MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # multipart es solo para archivos pequeños
PREVIEW_ROWS = 5

# Carga y estandarización son etapas inmutables compartidas por /standardize,
# /clean, /metrics y descargas. Un presupuesto único evita duplicar memoria sin
# límite: una base grande desplaza las entradas antiguas por LRU.
_FRAME_CACHE_LOCK = threading.Lock()
_FRAME_CACHE: "OrderedDict[tuple, tuple[object, dict]]" = OrderedDict()
_FRAME_CACHE_CELL_BUDGET = 1_600_000
_FRAME_CACHE_MAX_ENTRY_CELLS = 1_200_000


def _clone_frame(df):
    cloned = df.copy(deep=True)
    cloned.attrs = copy.deepcopy(df.attrs)
    return cloned


def _frame_cache_get(key: tuple):
    with _FRAME_CACHE_LOCK:
        cached = _FRAME_CACHE.get(key)
        if cached is None:
            return None
        _FRAME_CACHE.move_to_end(key)
        frame, report = cached
    return _clone_frame(frame), copy.deepcopy(report)


def _frame_cache_store(key: tuple, frame, report: dict) -> None:
    cells = len(frame) * max(len(frame.columns), 1)
    if cells > _FRAME_CACHE_MAX_ENTRY_CELLS:
        return
    stored = (_clone_frame(frame), copy.deepcopy(report))
    with _FRAME_CACHE_LOCK:
        _FRAME_CACHE[key] = stored
        _FRAME_CACHE.move_to_end(key)
        total = sum(
            len(item[0]) * max(len(item[0].columns), 1)
            for item in _FRAME_CACHE.values()
        )
        while len(_FRAME_CACHE) > 1 and total > _FRAME_CACHE_CELL_BUDGET:
            _, removed = _FRAME_CACHE.popitem(last=False)
            total -= len(removed[0]) * max(len(removed[0].columns), 1)


def _frame_key(kind: str, filename: str, content: bytes, sheet: str | None, extra: str = "") -> tuple:
    return (
        kind,
        hashlib.sha1(content).digest(),
        os.path.splitext(filename)[1].lower(),
        sheet or "",
        extra,
    )


def _normalize_user_storage_path(storage_path: str, user: AuthenticatedUser) -> str:
    """El bucket organiza los archivos por carpeta {user_id}/...; la API descarga
    con la service_role key (salta RLS), así que la propiedad se valida aquí."""
    return normalize_user_storage_path(storage_path, user.id)


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
    key = _frame_key("raw", filename, content, sheet)
    cached = _frame_cache_get(key)
    if cached is not None:
        return cached
    try:
        frame, report = load_dataframe_with_report(filename, content, sheet=sheet)
    except UnsupportedFileError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    _frame_cache_store(key, frame, report)
    return frame, report


def _standardize_frame_cached(
    filename: str,
    content: bytes,
    sheet: str | None,
    mapping: dict | None,
    original=None,
):
    mapping_key = json.dumps(mapping or {}, sort_keys=True)
    key = _frame_key("standardized", filename, content, sheet, mapping_key)
    cached = _frame_cache_get(key)
    if cached is not None:
        return cached
    if original is None:
        original, _ = _load_or_400(filename, content, sheet=sheet)
    standardized, report = standardize_dataframe(original, mapping=mapping)
    _frame_cache_store(key, standardized, report)
    return standardized, report


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


_MANIFEST_ENTRY_KEYS = {
    "nombre",
    "procesar",
    "rules",
    "mapping",
    "scope",
    "eliminar_duplicados",
}


def _parse_sheet_manifest(raw: str | None) -> dict | None:
    """Valida el contrato explícito de descarga multihoja.

    El manifiesto, no el caché del proceso, es la fuente de verdad de las hojas
    elegidas por el usuario y de la configuración aplicada a cada una.
    """
    if not raw:
        return None
    if len(raw) > 100_000:
        raise HTTPException(status_code=422, detail="El manifiesto de hojas es demasiado grande.")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="El campo 'manifest' debe ser JSON válido.")
    if not isinstance(value, dict) or set(value) != {"hojas"}:
        raise HTTPException(
            status_code=422,
            detail="El manifiesto debe ser un objeto con una única lista 'hojas'.",
        )
    entries = value.get("hojas")
    if not isinstance(entries, list) or not entries or len(entries) > 50:
        raise HTTPException(
            status_code=422,
            detail="El manifiesto debe incluir entre 1 y 50 hojas.",
        )

    normalized: list[dict] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise HTTPException(status_code=422, detail=f"La hoja {index} del manifiesto no es válida.")
        unknown = set(entry) - _MANIFEST_ENTRY_KEYS
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"La hoja {index} contiene campos desconocidos: {', '.join(sorted(unknown))}.",
            )
        name = _clean_sheet_param(entry.get("nombre"))
        if not name:
            raise HTTPException(status_code=422, detail=f"La hoja {index} no tiene nombre.")
        if name in seen:
            raise HTTPException(status_code=422, detail=f"La hoja '{name}' está repetida en el manifiesto.")
        seen.add(name)
        if not isinstance(entry.get("procesar"), bool):
            raise HTTPException(
                status_code=422,
                detail=f"'procesar' debe ser true o false para la hoja '{name}'.",
            )

        rules = entry.get("rules", {})
        mapping = entry.get("mapping", {})
        scope = entry.get("scope", {})
        if not isinstance(rules, dict) or not isinstance(mapping, dict) or not isinstance(scope, dict):
            raise HTTPException(
                status_code=422,
                detail=f"rules, mapping y scope deben ser objetos en la hoja '{name}'.",
            )
        remove_duplicates = entry.get("eliminar_duplicados", False)
        if not isinstance(remove_duplicates, bool):
            raise HTTPException(
                status_code=422,
                detail=f"eliminar_duplicados debe ser booleano en la hoja '{name}'.",
            )
        normalized.append(
            {
                "nombre": name,
                "procesar": entry["procesar"],
                "rules": _validate_rules(rules),
                "mapping": _validate_mapping(mapping) or {},
                "scope": _validate_scope(scope) or {},
                "eliminar_duplicados": remove_duplicates,
            }
        )

    if not any(entry["procesar"] for entry in normalized):
        raise HTTPException(status_code=422, detail="Selecciona al menos una hoja para procesar.")
    return {"hojas": normalized}


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
    eliminar_duplicados: bool = False,
) -> tuple:
    effective_rules = {**DEFAULT_RULES, **(rules or {})}
    return (
        hashlib.sha1(content).digest(),
        json.dumps(effective_rules, sort_keys=True),
        apply,
        json.dumps(mapping or {}, sort_keys=True),
        json.dumps(scope or {}, sort_keys=True),
        sheet or "",
        bool(eliminar_duplicados),
    )


def _analyze_cached(
    filename: str,
    content: bytes,
    rules: dict | None,
    apply: bool,
    mapping: dict | None = None,
    scope: dict | None = None,
    sheet: str | None = None,
    eliminar_duplicados: bool = False,
) -> dict:
    """analyze_and_clean con caché. El dict cacheado JAMÁS se muta: los
    endpoints construyen su respuesta con una copia superficial."""
    key = _cache_key(
        content, rules, apply, mapping, scope, sheet, eliminar_duplicados
    )
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
    standardized = _standardize_frame_cached(
        filename,
        content,
        sheet,
        mapping,
        original=df,
    )

    result = analyze_and_clean(
        df,
        rules,
        apply,
        mapping=mapping,
        scope=scope,
        eliminar_duplicados=eliminar_duplicados,
        standardized=standardized,
    )
    result["_moneda"] = currency
    result["avisos"] = list(load_report.get("avisos", [])) + list(result.get("avisos", []))
    result["carga"] = {
        "hoja_usada": load_report.get("hoja_usada"),
        "hojas_disponibles": load_report.get("hojas_disponibles", []),
        "filas_titulo_omitidas": load_report.get("filas_titulo_omitidas", 0),
        "formulas": load_report.get("formulas"),
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
    df_std, report = _standardize_frame_cached(
        filename,
        content,
        sheet,
        mapping=None,
        original=df_original,
    )

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
        "mojibake_auditoria": report.get("mojibake_auditoria", []),
        "avisos": list(load_report.get("avisos", [])) + list(report.get("avisos", [])),
        "carga": {
            "hoja_usada": load_report.get("hoja_usada"),
            "hojas_disponibles": load_report.get("hojas_disponibles", []),
            "filas_titulo_omitidas": load_report.get("filas_titulo_omitidas", 0),
            "formulas": load_report.get("formulas"),
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
    eliminar_duplicados: bool = False,
) -> dict:
    result = _analyze_cached(
        filename,
        content,
        rules,
        apply,
        mapping=mapping,
        scope=scope,
        sheet=sheet,
        eliminar_duplicados=eliminar_duplicados,
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


def _export_annotations(result: dict, df) -> tuple[dict, dict, list[tuple]]:
    """Marcas visuales y observaciones auditables para una hoja limpia."""
    from ..engine.standardize import is_missing, parse_date, parse_number

    role_labels: dict[str, str] = {
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
    column_types: dict = result["column_types"]
    col_role = {col_name: role for role, col_name in result["mapeo"].items()}
    total = max(len(df), 1)
    source_rows = list(result.get("_source_rows_limpio") or range(2, len(df) + 2))
    source_sheet = (result.get("carga") or {}).get("hoja_usada")
    yellow: dict[tuple[int, str], str] = {}
    red: dict[tuple[int, str], str] = {}

    for col in df.columns:
        ctype = column_types.get(col, "texto")
        role = col_role.get(col)
        vals = list(df[col])
        fill_rate = sum(1 for value in vals if not is_missing(str(value))) / total
        for row_idx, value in enumerate(vals):
            text = str(value)
            if not is_missing(text):
                # Fase 12b (P0): los valores NO interpretables se conservan en
                # los datos — aquí se marcan para que el cliente pueda revisar
                # el original en vez de encontrar una celda vaciada.
                if ctype == "fecha" and parse_date(text) is None:
                    yellow[(row_idx, col)] = (
                        "Fecha no interpretable: se conservó el valor original — revisar."
                    )
                elif ctype == "numero" and parse_number(text) is None:
                    yellow[(row_idx, col)] = (
                        "Número no interpretable: se conservó el valor original — revisar."
                    )
                continue
            if ctype == "fecha":
                yellow[(row_idx, col)] = "Fecha faltante: revisar."
            elif fill_rate >= 0.7:
                label = role_labels.get(role, col) if role else col
                red[(row_idx, col)] = f"Dato faltante en una columna casi completa ({label})."

    observations = [
        (source_rows[row], source_sheet, col, "revisar", message)
        for (row, col), message in yellow.items()
    ] + [
        (source_rows[row], source_sheet, col, "faltante", message)
        for (row, col), message in red.items()
    ] + [
        (
            detail["fila_origen"],
            detail.get("hoja_origen"),
            "*",
            "duplicado_eliminado",
            detail["motivo"],
        )
        for detail in result.get("_filas_duplicadas_eliminadas", [])
    ]
    return yellow, red, observations


def _safe_excel_sheet_name(name: str, used: set[str]) -> str:
    """Nombre válido y único sin perder silenciosamente una hoja."""
    base = re.sub(r"[\\/*?:\[\]]", "_", str(name)).strip().strip("'") or "Hoja"
    base = base[:31]
    candidate = base
    suffix = 2
    while candidate.casefold() in used:
        tail = f"_{suffix}"
        candidate = f"{base[: 31 - len(tail)]}{tail}"
        suffix += 1
    used.add(candidate.casefold())
    return candidate


def _write_clean_sheet(wb, title: str, df, yellow: dict, red: dict) -> None:
    from openpyxl.styles import Font, PatternFill

    ws = wb.create_sheet(title)
    exported = safe_export_dataframe(df)
    ws.append(list(exported.columns))
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in exported.itertuples(index=False, name=None):
        ws.append(list(row))

    yellow_fill = PatternFill(start_color="FFEB3B", end_color="FFEB3B", fill_type="solid")
    red_fill = PatternFill(start_color="FFCDD2", end_color="FFCDD2", fill_type="solid")
    columns = list(df.columns)
    positions = {column: index + 1 for index, column in enumerate(columns)}
    for row, column in yellow:
        ws.cell(row=row + 2, column=positions[column]).fill = yellow_fill
    for row, column in red:
        ws.cell(row=row + 2, column=positions[column]).fill = red_fill


def _write_observations_sheet(wb, observations: list[tuple]) -> None:
    from openpyxl.styles import Font

    ws = wb.create_sheet("Observaciones")
    ws.append(["Fila origen", "Hoja", "Columna", "Tipo", "Detalle"])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    if observations:
        for source_row, source_sheet, column, kind, message in observations:
            ws.append([source_row, source_sheet or "CSV", column, kind, message])
    else:
        ws.append(["—", "—", "—", "—", "Sin observaciones: la base quedó completa."])
    ws.column_dimensions["B"].width = 20
    ws.column_dimensions["C"].width = 24
    ws.column_dimensions["E"].width = 64


def _clean_download_sync(
    filename: str,
    content: bytes,
    rules: dict,
    fmt: str,
    mapping: dict | None = None,
    scope: dict | None = None,
    sheet: str | None = None,
    eliminar_duplicados: bool = False,
) -> tuple[bytes, str, str]:
    result = _analyze_cached(
        filename,
        content,
        rules,
        apply=True,
        mapping=mapping,
        scope=scope,
        sheet=sheet,
        eliminar_duplicados=eliminar_duplicados,
    )
    df = result["_df_limpio"].copy()
    stem = re.sub(r"[^\w\-]", "_", os.path.splitext(filename)[0])
    df_export = safe_export_dataframe(df)

    if fmt == "csv":
        # CSV limpio de verdad: sin marcadores dentro de los datos.
        return (
            df_export.to_csv(index=False, sep=";").encode("utf-8-sig"),
            f"{stem}_limpio.csv",
            "text/csv; charset=utf-8",
        )

    import openpyxl

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    yellow, red, observations = _export_annotations(result, df)
    _write_clean_sheet(wb, "Datos_limpios", df, yellow, red)
    _write_observations_sheet(wb, observations)
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return (
        output.getvalue(),
        f"{stem}_limpio.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _clean_download_multi_sync(
    filename: str,
    content: bytes,
    manifest: dict,
    combine_sheets: bool,
) -> tuple[bytes, str, str]:
    """Exporta exactamente las hojas declaradas por el cliente.

    El caché acelera cada análisis, pero nunca participa en la decisión de qué
    hojas están procesadas. El manifiesto debe enumerar todas las hojas reales.
    """
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="La descarga multihoja requiere un archivo .xlsx.")

    entries = manifest["hojas"]
    _, load_report = _load_or_400(filename, content, sheet=entries[0]["nombre"])
    available = list(load_report.get("hojas_disponibles", []))
    declared = [entry["nombre"] for entry in entries]
    missing = [name for name in available if name not in declared]
    unknown = [name for name in declared if name not in available]
    if missing or unknown or len(declared) != len(available):
        details: list[str] = []
        if missing:
            details.append(f"faltan: {', '.join(missing)}")
        if unknown:
            details.append(f"no existen: {', '.join(unknown)}")
        raise HTTPException(
            status_code=422,
            detail="El manifiesto debe enumerar todas las hojas del Excel (" + "; ".join(details) + ").",
        )

    import openpyxl
    import pandas as pd

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    used_names = {"observaciones"}
    if combine_sheets:
        used_names.add("datos_combinados")
    observations: list[tuple] = []
    processed_frames: list[tuple[str, object]] = []

    for entry in entries:
        sheet_name = entry["nombre"]
        if not entry["procesar"]:
            observations.append(
                (
                    "—",
                    sheet_name,
                    "*",
                    "hoja_no_procesada",
                    "Hoja incluida en el manifiesto, pero el usuario decidió no procesarla.",
                )
            )
            continue
        result = _analyze_cached(
            filename,
            content,
            entry["rules"],
            apply=True,
            mapping=entry["mapping"] or None,
            scope=entry["scope"] or None,
            sheet=sheet_name,
            eliminar_duplicados=entry["eliminar_duplicados"],
        )
        frame = result["_df_limpio"].copy()
        yellow, red, sheet_observations = _export_annotations(result, frame)
        export_name = _safe_excel_sheet_name(sheet_name, used_names)
        _write_clean_sheet(wb, export_name, frame, yellow, red)
        observations.extend(sheet_observations)
        processed_frames.append((sheet_name, frame))

    if combine_sheets:
        if len(processed_frames) < 2:
            raise HTTPException(
                status_code=422,
                detail="Se necesitan al menos dos hojas procesadas para combinarlas.",
            )
        first_columns = list(processed_frames[0][1].columns)
        if "hoja_origen" in first_columns:
            raise HTTPException(
                status_code=422,
                detail="No se pueden combinar las hojas porque ya existe una columna 'hoja_origen'.",
            )
        first_set = set(first_columns)
        if any(set(frame.columns) != first_set for _, frame in processed_frames[1:]):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Solo se pueden combinar hojas con el mismo conjunto de encabezados "
                    "normalizados. No se realizan uniones por claves automáticamente."
                ),
            )
        combined_parts = []
        for source_name, frame in processed_frames:
            part = frame.reindex(columns=first_columns).copy()
            part.insert(0, "hoja_origen", source_name)
            combined_parts.append(part)
        combined = pd.concat(combined_parts, ignore_index=True)
        _write_clean_sheet(wb, "Datos_combinados", combined, {}, {})

    _write_observations_sheet(wb, observations)
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    stem = re.sub(r"[^\w\-]", "_", os.path.splitext(filename)[0])
    return (
        output.getvalue(),
        f"{stem}_multihoja_limpio.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _metrics_sync(
    filename: str,
    content: bytes,
    mapping: dict | None,
    date_from: str | None,
    date_to: str | None,
    sheet: str | None = None,
    eliminar_duplicados: bool = False,
) -> dict:
    # Las métricas siempre se calculan sobre datos estandarizados y limpios.
    # Con el caché (§5.7), cambiar el periodo NO re-corre el pipeline completo.
    result = _analyze_cached(
        filename,
        content,
        rules=None,
        apply=True,
        mapping=mapping,
        sheet=sheet,
        eliminar_duplicados=eliminar_duplicados,
    )
    df_clean = result["_df_limpio"]
    computed = compute_metrics(
        df_clean, mapping, date_from=date_from, date_to=date_to,
        currency_hint=result.get("_moneda"),
    )
    computed["archivo"] = filename
    computed["calidad_datos"] = result["resumen"]["calidad_despues"]
    return computed


def _restore_response(record: dict, snapshot: dict, source: str) -> dict:
    return {
        "dataset": {
            "id": record["id"],
            "name": record["name"],
            "source": record.get("source", "excel_csv"),
            "storage_path": record["storage_path"],
            "status": record["status"],
        },
        "standardization": snapshot["standardization"],
        "cleaning": snapshot.get("cleaning"),
        "metrics": snapshot.get("metrics"),
        "mapping": snapshot.get("mapping"),
        "eliminar_duplicados": bool(snapshot.get("eliminar_duplicados", False)),
        "source": source,
    }


def _build_and_store_restore_snapshot(
    dataset_id: str,
    user_id: str,
    filename: str,
    content: bytes,
    cleaning: dict | None,
    mapping: dict | None,
    sheet: str | None,
    eliminar_duplicados: bool,
) -> dict:
    """Build a bounded snapshot from server-generated results only."""
    standardization = _standardize_sync(filename, content, sheet)
    metrics = (
        _metrics_sync(
            filename,
            content,
            mapping,
            None,
            None,
            sheet,
            eliminar_duplicados,
        )
        if cleaning is not None
        else None
    )
    snapshot = build_restore_snapshot(
        standardization,
        cleaning,
        metrics,
        mapping,
        eliminar_duplicados,
    )
    store_restore_snapshot(dataset_id, user_id, snapshot)
    return snapshot


def _restore_latest_sync(user_id: str) -> dict:
    """Restore from a persistent snapshot, or rebuild once as a fallback."""
    record = fetch_latest_restore_record(user_id)
    if record is None:
        return {"dataset": None, "source": "empty"}

    cached = valid_restore_snapshot(record.get("restore_snapshot"), record["status"])
    if cached is not None:
        return _restore_response(record, cached, "snapshot")

    storage_path = normalize_user_storage_path(record["storage_path"], user_id)
    content = download_from_storage(storage_path)
    filename = os.path.basename(storage_path)
    mapping = fetch_dataset_mapping(record["id"])
    cleaning = None
    eliminar_duplicados = False
    if record["status"] == "limpio":
        rules, eliminar_duplicados = fetch_latest_cleaning_config(record["id"], user_id)
        cleaning = _clean_sync(
            filename,
            content,
            rules,
            True,
            mapping,
            None,
            None,
            None,
            eliminar_duplicados,
        )
    snapshot = _build_and_store_restore_snapshot(
        record["id"],
        user_id,
        filename,
        content,
        cleaning,
        mapping,
        None,
        eliminar_duplicados,
    )
    return _restore_response(record, snapshot, "computed")


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/restore/latest")
async def restore_latest(
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    """One round-trip restoration; pandas is only used when no snapshot exists."""
    # Fase 14 (P0): el fallback sin snapshot corre el pipeline completo —
    # misma puerta comercial que el dashboard. El frontend (DatasetBootstrap)
    # trata el 403 como "nada que restaurar", sin romper la navegación.
    await run_in_threadpool(
        require_capability_for_user, user.id, Capability.VIEW_DASHBOARD, settings
    )
    return await run_in_threadpool(_restore_latest_sync, user.id)


@router.post("/standardize")
async def standardize(
    file: UploadFile | None = File(None),
    storage_path: str | None = Form(None),
    sheet: str | None = Form(None),
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    # Fase 13: las cuentas nuevas nacen SIN plan — pueden navegar, pero
    # procesar archivos requiere un plan activo o la prueba gratuita vigente
    # (las cuentas existentes conservan su plan básico y no notan el cambio).
    # threadpool: la puerta consulta Supabase por HTTP y no debe bloquear el loop.
    await run_in_threadpool(
        require_capability_for_user, user.id, Capability.STANDARDIZE, settings
    )
    filename, content = await _read_input(file, storage_path, user)
    return await run_in_threadpool(
        _standardize_sync, filename, content, _clean_sheet_param(sheet)
    )


@router.post("/clean")
async def clean(
    background_tasks: BackgroundTasks,
    file: UploadFile | None = File(None),
    storage_path: str | None = Form(None),
    dataset_id: str | None = Form(None),
    rules: str | None = Form(None),
    apply: bool = Form(False),
    eliminar_duplicados: bool = Form(False),
    mapping: str | None = Form(None),
    sheet: str | None = Form(None),
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    await run_in_threadpool(
        require_capability_for_user, user.id, Capability.CLEAN, settings
    )
    filename, content = await _read_input(file, storage_path, user)
    rules_dict = _validate_rules(_parse_json_field(rules, "rules"))
    mapping_dict = _validate_mapping(_parse_json_field(mapping, "mapping") or None)
    result = await run_in_threadpool(
        _clean_sync, filename, content, rules_dict, apply, mapping_dict, None, None,
        _clean_sheet_param(sheet), eliminar_duplicados,
    )
    if apply and dataset_id:
        background_tasks.add_task(
            _build_and_store_restore_snapshot,
            dataset_id,
            user.id,
            filename,
            content,
            result,
            mapping_dict,
            _clean_sheet_param(sheet),
            eliminar_duplicados,
        )
    return result


@router.post("/clean/assisted")
async def clean_assisted(
    background_tasks: BackgroundTasks,
    file: UploadFile | None = File(None),
    storage_path: str | None = Form(None),
    dataset_id: str | None = Form(None),
    instructions: str = Form(...),
    rules: str | None = Form(None),
    eliminar_duplicados: bool = Form(False),
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
    await run_in_threadpool(
        require_capability_for_user, user.id, Capability.AI_CLEANING, settings
    )

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
        None, sheet_name, eliminar_duplicados,
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
    if dataset_id:
        background_tasks.add_task(
            _build_and_store_restore_snapshot,
            dataset_id,
            user.id,
            filename,
            content,
            result,
            mapping_dict,
            sheet_name,
            eliminar_duplicados,
        )
    return result


@router.post("/clean/download")
async def clean_download(
    file: UploadFile | None = File(None),
    storage_path: str | None = Form(None),
    rules: str | None = Form(None),
    eliminar_duplicados: bool = Form(False),
    fmt: str = Form("xlsx"),
    format: str | None = Form(None),
    mapping: str | None = Form(None),
    scope: str | None = Form(None),
    sheet: str | None = Form(None),
    manifest: str | None = Form(None),
    combinar_hojas: bool = Form(False),
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Devuelve el dataset con la limpieza aplicada como archivo descargable (xlsx o csv)."""
    await run_in_threadpool(
        require_capability_for_user, user.id, Capability.DOWNLOAD_CLEAN_DATASET, settings
    )
    export_format = (format or fmt).strip().lower()
    if export_format not in {"csv", "xlsx"}:
        raise HTTPException(
            status_code=422,
            detail="El campo 'fmt' debe ser 'csv' o 'xlsx'.",
        )
    filename, content = await _read_input(file, storage_path, user)
    sheet_manifest = _parse_sheet_manifest(manifest)
    if combinar_hojas and sheet_manifest is None:
        raise HTTPException(
            status_code=422,
            detail="Para combinar hojas debes enviar un manifiesto explícito.",
        )
    if sheet_manifest is not None:
        if export_format != "xlsx":
            raise HTTPException(
                status_code=422,
                detail="La descarga multihoja solo está disponible en formato XLSX.",
            )
        file_bytes, out_name, media_type = await run_in_threadpool(
            _clean_download_multi_sync,
            filename,
            content,
            sheet_manifest,
            combinar_hojas,
        )
        return StreamingResponse(
            iter([file_bytes]),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{out_name}"'},
        )
    rules_dict = _validate_rules(_parse_json_field(rules, "rules"))
    mapping_dict = _validate_mapping(_parse_json_field(mapping, "mapping") or None)
    scope_dict = _validate_scope(_parse_json_field(scope, "scope") or None)
    file_bytes, out_name, media_type = await run_in_threadpool(
        _clean_download_sync, filename, content, rules_dict, export_format,
        mapping_dict, scope_dict, _clean_sheet_param(sheet), eliminar_duplicados,
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
    eliminar_duplicados: bool = Form(False),
    date_from: str | None = Form(None),
    date_to: str | None = Form(None),
    sheet: str | None = Form(None),
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    # Fase 14 (P0): /metrics reprocesa el archivo completo (caché aparte) —
    # sin esta puerta, una cuenta sin plan tenía el dashboard gratis.
    await run_in_threadpool(
        require_capability_for_user, user.id, Capability.VIEW_DASHBOARD, settings
    )
    filename, content = await _read_input(file, storage_path, user)
    mapping_dict = _validate_mapping(_parse_json_field(mapping, "mapping") or None)
    return await run_in_threadpool(
        _metrics_sync, filename, content, mapping_dict, date_from, date_to,
        _clean_sheet_param(sheet), eliminar_duplicados,
    )
