"""Alcances multihoja seguros para analisis, exportacion y restauracion.

El modulo no carga archivos ni decide planes. Recibe DataFrames ya procesados
por el pipeline existente y se limita a validar apilados/relaciones, detectar
claves y demostrar que una union no altera filas ni totales transaccionales.
"""

from __future__ import annotations

import itertools
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

import pandas as pd

from .mapping import detect_columns_extended, norm_key, resolve_mapping
from .metrics import detect_currency, is_transaction_profile
from .standardize import NUMERIC_CANONICAL_ATTR, detect_value_type_confidence, parse_number

# Se permite una relacion parcial controlada desde 60%: las filas sin clave o
# sin correspondencia permanecen en el left join y se informan. El archivo de
# estres contiene nulos estructurales de sucursal y quedaba bloqueado pese a
# que la porcion identificada tiene solapamiento y cardinalidad seguros.
RELATION_MIN_COVERAGE = 0.60
RELATION_MIN_OVERLAP = 0.60
RELATION_UNIQUE_THRESHOLD = 0.995
MAX_RELATION_KEYS = 2

ANALYSIS_MODES = {"single", "append", "join", "append_join"}
METRIC_ROLES = {"monto", "costo", "cantidad"}
IDENTIFIER_MARKERS = {
    "id", "codigo", "code", "sku", "rut", "folio", "numero", "nro", "num",
    "uuid", "clave", "key",
}


def is_unit_cost_column(column: str | None) -> bool:
    """Solo acepta encabezados que declaran explícitamente costo por unidad."""

    if not column:
        return False
    compact = norm_key(str(column))
    return any(
        marker in compact
        for marker in (
            "costounitario",
            "costoporunidad",
            "unitcost",
            "costperunit",
        )
    )


def validate_analysis_scope(raw: dict | None, available_sheets: list[str]) -> dict:
    """Contrato compacto, estricto y serializable del alcance compartido."""
    if not raw:
        active = available_sheets[0] if available_sheets else None
        return {"mode": "single", "sheets": [active] if active else [], "active_sheet": active}
    if not isinstance(raw, dict):
        raise ValueError("analysis_scope debe ser un objeto JSON.")
    unknown = set(raw) - {"mode", "sheets", "active_sheet", "join", "append_sheets", "_selection_mode"}
    if unknown:
        raise ValueError(f"analysis_scope contiene campos desconocidos: {', '.join(sorted(unknown))}.")
    mode = str(raw.get("mode", "single")).strip().lower()
    if mode not in ANALYSIS_MODES:
        raise ValueError("analysis_scope.mode debe ser single, append, join o append_join.")
    sheets_raw = raw.get("sheets", [])
    if not isinstance(sheets_raw, list) or not all(isinstance(item, str) for item in sheets_raw):
        raise ValueError("analysis_scope.sheets debe ser una lista de hojas.")
    sheets: list[str] = []
    for name in sheets_raw:
        clean = name.strip()
        if clean and clean not in sheets:
            sheets.append(clean)
    unknown_sheets = [name for name in sheets if name not in available_sheets]
    if unknown_sheets:
        raise ValueError(f"Hojas desconocidas en analysis_scope: {', '.join(unknown_sheets)}.")
    # append_join accepts one sales sheet plus one reference sheet. The left
    # sheet is only a representative when several sales sheets are stacked.
    minimum = 1 if mode == "single" else 2
    if len(sheets) < minimum:
        raise ValueError(f"El modo {mode} requiere al menos {minimum} hoja(s).")
    active = raw.get("active_sheet")
    active_sheet = str(active).strip() if isinstance(active, str) and active.strip() else sheets[0]
    if active_sheet not in sheets:
        raise ValueError("analysis_scope.active_sheet debe estar incluido en sheets.")
    normalized: dict[str, Any] = {"mode": mode, "sheets": sheets, "active_sheet": active_sheet}
    selection_mode = raw.get("_selection_mode")
    if selection_mode in {"all", "custom"}:
        normalized["_selection_mode"] = selection_mode
    append_sheets: list[str] = []
    if mode == "append_join":
        append_raw = raw.get("append_sheets")
        if not isinstance(append_raw, list) or not all(isinstance(item, str) for item in append_raw):
            raise ValueError("append_join requiere append_sheets.")
        append_sheets = list(dict.fromkeys(item.strip() for item in append_raw if item.strip()))
        if len(append_sheets) < 1 or any(name not in sheets for name in append_sheets):
            raise ValueError("append_join requiere al menos una hoja de ventas incluida.")
        normalized["append_sheets"] = append_sheets
    if mode in {"join", "append_join"}:
        join = raw.get("join")
        if not isinstance(join, dict):
            raise ValueError("El modo join requiere una relacion confirmada.")
        allowed = {"left_sheet", "right_sheet", "left_keys", "right_keys", "type"}
        if set(join) - allowed:
            raise ValueError("La relacion contiene campos desconocidos.")
        left = str(join.get("left_sheet", "")).strip()
        right = str(join.get("right_sheet", "")).strip()
        left_keys = join.get("left_keys")
        right_keys = join.get("right_keys")
        valid_left = left in sheets and (
            mode == "join" or left in append_sheets
        )
        valid_right = right in sheets and (
            mode == "join" or right not in append_sheets
        )
        if not valid_left or not valid_right or left == right:
            raise ValueError("Las hojas izquierda y derecha deben ser distintas e incluidas.")
        if (
            not isinstance(left_keys, list)
            or not isinstance(right_keys, list)
            or not left_keys
            or len(left_keys) != len(right_keys)
            or len(left_keys) > MAX_RELATION_KEYS
            or not all(isinstance(key, str) and key.strip() for key in left_keys + right_keys)
        ):
            raise ValueError("Las claves de la relacion no son validas.")
        if join.get("type", "left") != "left":
            raise ValueError("Solo se permiten relaciones left many-to-one.")
        normalized["join"] = {
            "left_sheet": left,
            "right_sheet": right,
            "left_keys": [key.strip() for key in left_keys],
            "right_keys": [key.strip() for key in right_keys],
            "type": "left",
        }
    return normalized


def _text_key(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = unicodedata.normalize("NFKD", str(value).strip().lower())
    return "".join(char for char in text if not unicodedata.combining(char))


def _key_series(frame: pd.DataFrame, keys: list[str]) -> pd.Series:
    parts = [frame[key].map(_text_key) for key in keys]
    valid = pd.Series(True, index=frame.index)
    for part in parts:
        valid &= part != ""
    tuples = pd.Series(list(zip(*parts, strict=False)), index=frame.index, dtype="object")
    return tuples.where(valid, None)


def _column_type(frame: pd.DataFrame, column: str) -> str:
    return detect_value_type_confidence(frame[column], column)[0]


def _compatible_types(left: pd.DataFrame, left_keys: list[str], right: pd.DataFrame, right_keys: list[str]) -> bool:
    return all(
        _column_type(left, left_key) == _column_type(right, right_key)
        for left_key, right_key in zip(left_keys, right_keys, strict=True)
    )


@dataclass(frozen=True)
class RelationStats:
    coverage_left: float
    coverage_right: float
    overlap: float
    unique_left: float
    unique_right: float
    cardinality: str
    safe: bool
    reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "coverage_left": round(self.coverage_left, 4),
            "coverage_right": round(self.coverage_right, 4),
            "overlap": round(self.overlap, 4),
            "unique_left": round(self.unique_left, 4),
            "unique_right": round(self.unique_right, 4),
            "cardinality": self.cardinality,
            "safe": self.safe,
            "reason": self.reason,
        }


def relation_stats(
    left: pd.DataFrame,
    left_keys: list[str],
    right: pd.DataFrame,
    right_keys: list[str],
) -> RelationStats:
    if any(key not in left.columns for key in left_keys) or any(key not in right.columns for key in right_keys):
        return RelationStats(0, 0, 0, 0, 0, "sin_relacion_segura", False, "La clave no existe.")
    if not _compatible_types(left, left_keys, right, right_keys):
        return RelationStats(0, 0, 0, 0, 0, "sin_relacion_segura", False, "Los tipos son incompatibles.")
    left_series = _key_series(left, left_keys)
    right_series = _key_series(right, right_keys)
    return _relation_stats_from_series(left_series, len(left), right_series, len(right))


def _relation_stats_from_series(
    left_series: pd.Series,
    left_rows: int,
    right_series: pd.Series,
    right_rows: int,
) -> RelationStats:
    """Calcula la seguridad desde claves ya normalizadas.

    El detector automático reutiliza estas series entre candidatos; normalizar
    las mismas 5.500 claves cientos de veces era su principal cuello de botella.
    """
    left_valid = left_series.dropna()
    right_valid = right_series.dropna()
    coverage_left = len(left_valid) / max(left_rows, 1)
    coverage_right = len(right_valid) / max(right_rows, 1)
    left_unique_values = set(left_valid.tolist())
    right_unique_values = set(right_valid.tolist())
    overlap = (
        len(left_unique_values & right_unique_values) / max(len(left_unique_values), 1)
        if left_unique_values
        else 0.0
    )
    unique_left = left_valid.nunique() / max(len(left_valid), 1)
    unique_right = right_valid.nunique() / max(len(right_valid), 1)
    left_is_unique = unique_left >= RELATION_UNIQUE_THRESHOLD
    right_is_unique = unique_right >= RELATION_UNIQUE_THRESHOLD
    if left_is_unique and right_is_unique:
        cardinality = "uno_a_uno"
    elif right_is_unique:
        cardinality = "muchos_a_uno"
    elif left_is_unique:
        cardinality = "uno_a_muchos"
    else:
        cardinality = "muchos_a_muchos"
    reason = None
    if coverage_left < RELATION_MIN_COVERAGE or coverage_right < RELATION_MIN_COVERAGE:
        reason = "La cobertura de la clave es demasiado baja."
    elif overlap < RELATION_MIN_OVERLAP:
        reason = "El solapamiento entre hojas es insuficiente."
    elif not right_is_unique:
        reason = "La hoja de referencia contiene claves duplicadas."
    safe = reason is None and cardinality in {"muchos_a_uno", "uno_a_uno"}
    return RelationStats(
        coverage_left,
        coverage_right,
        overlap,
        unique_left,
        unique_right,
        cardinality,
        safe,
        reason,
    )


def _candidate_pairs(left: pd.DataFrame, right: pd.DataFrame) -> list[tuple[str, str]]:
    right_by_norm = {norm_key(str(column)): str(column) for column in right.columns}
    pairs: list[tuple[str, str]] = []
    left_extended = detect_columns_extended([str(column) for column in left.columns])
    right_extended = detect_columns_extended([str(column) for column in right.columns])
    for left_column in left.columns:
        left_name = str(left_column)
        right_name = right_by_norm.get(norm_key(left_name))
        words = {
            word for word in re.split(r"[^a-z0-9]+", _text_key(left_name)) if word
        }
        normalized_name = norm_key(left_name)
        looks_identifier = bool(words & IDENTIFIER_MARKERS) or normalized_name.startswith(
            ("id", "codigo", "sku", "rut", "folio", "uuid", "clave")
        ) or normalized_name.endswith(("id", "codigo", "sku", "rut", "folio", "uuid"))
        left_match = left_extended.get(left_name)
        if right_name and (
            looks_identifier or (left_match is not None and left_match.grupo == "identificador")
        ):
            pairs.append((left_name, right_name))
            continue
        if not left_match or left_match.grupo != "identificador":
            continue
        for candidate, right_match in right_extended.items():
            if right_match.grupo == "identificador" and right_match.rol == left_match.rol:
                pairs.append((left_name, candidate))
                break
    return pairs


def detect_relationships(
    frames: dict[str, pd.DataFrame],
    mappings: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Detecta relaciones de enriquecimiento y las ordena por utilidad.

    Dos tablas transaccionales compatibles se deben apilar, no relacionar.
    Para evitar sugerencias confusas, la deteccion automatica prioriza una
    tabla de ventas a la izquierda y una maestra (especialmente Productos con
    costo) a la derecha. La validacion manual sigue disponible para cualquier
    pareja y usa :func:`relation_stats` directamente.
    """
    mappings = mappings or {}
    resolved_mappings = {
        name: resolve_mapping([str(column) for column in frame.columns], mappings.get(name))
        for name, frame in frames.items()
    }

    def sheet_profile(name: str) -> dict[str, bool]:
        mapping = resolved_mappings[name]
        is_transaction = is_transaction_profile(frames[name].columns, mapping)
        return {
            "transaction": is_transaction,
            "cost_reference": bool(
                is_unit_cost_column(mapping.get("costo")) and not is_transaction
            ),
        }

    profiles = {name: sheet_profile(name) for name in frames}
    key_series_cache: dict[tuple[str, tuple[str, ...]], pd.Series] = {}
    column_type_cache: dict[tuple[str, str], str] = {}

    def cached_column_type(name: str, frame: pd.DataFrame, key: str) -> str:
        cache_key = (name, key)
        if cache_key not in column_type_cache:
            column_type_cache[cache_key] = _column_type(frame, key)
        return column_type_cache[cache_key]

    def cached_stats(
        left_name: str,
        left_keys: list[str],
        right_name: str,
        right_keys: list[str],
    ) -> RelationStats:
        left = frames[left_name]
        right = frames[right_name]
        if any(key not in left.columns for key in left_keys) or any(
            key not in right.columns for key in right_keys
        ):
            return RelationStats(
                0, 0, 0, 0, 0, "sin_relacion_segura", False, "La clave no existe."
            )
        left_types = tuple(
            cached_column_type(left_name, left, key)
            for key in left_keys
        )
        right_types = tuple(
            cached_column_type(right_name, right, key)
            for key in right_keys
        )
        if left_types != right_types:
            return RelationStats(
                0, 0, 0, 0, 0, "sin_relacion_segura", False, "Los tipos son incompatibles."
            )
        left_cache_key = (left_name, tuple(left_keys))
        right_cache_key = (right_name, tuple(right_keys))
        if left_cache_key not in key_series_cache:
            key_series_cache[left_cache_key] = _key_series(left, left_keys)
        if right_cache_key not in key_series_cache:
            key_series_cache[right_cache_key] = _key_series(right, right_keys)
        return _relation_stats_from_series(
            key_series_cache[left_cache_key],
            len(left),
            key_series_cache[right_cache_key],
            len(right),
        )

    def purpose(left_name: str, right_name: str) -> str:
        left = profiles[left_name]
        right = profiles[right_name]
        if left["transaction"] and right["cost_reference"]:
            return "enriquecer_costos"
        if left["transaction"] and not right["transaction"]:
            return "enriquecer_referencia"
        return "otra_relacion"

    candidates: list[dict[str, Any]] = []
    for first_name, second_name in itertools.combinations(frames, 2):
        # Ventas Enero + Ventas Febrero es un apilado. Buscar una llave entre
        # ambas agrega trabajo y puede terminar recomendando una union que no
        # representa el negocio.
        first_transaction = profiles[first_name]["transaction"]
        second_transaction = profiles[second_name]["transaction"]
        if first_transaction == second_transaction:
            continue
        # La orientación comercial es inequívoca: ventas a la izquierda y la
        # maestra a la derecha. Evaluar también el sentido inverso triplicaba
        # estadísticas y generaba sugerencias sin utilidad para el usuario.
        if first_transaction:
            left_name, right_name = first_name, second_name
        else:
            left_name, right_name = second_name, first_name
        left = frames[left_name]
        right = frames[right_name]
        pairs = _candidate_pairs(left, right)
        relation_purpose = purpose(left_name, right_name)
        pair_candidates: list[dict[str, Any]] = []
        for left_key, right_key in pairs:
            stats = cached_stats(left_name, [left_key], right_name, [right_key])
            pair_candidates.append(
                {
                    "left_sheet": left_name,
                    "right_sheet": right_name,
                    "left_keys": [left_key],
                    "right_keys": [right_key],
                    "type": "left",
                    "purpose": relation_purpose,
                    "recommended": bool(
                        stats.safe and relation_purpose == "enriquecer_costos"
                    ),
                    **stats.to_dict(),
                }
            )
        safe_single = [item for item in pair_candidates if item["safe"]]
        if safe_single:
            candidates.append(max(
                safe_single,
                key=lambda item: (item["overlap"], item["coverage_left"]),
            ))
            continue
        composite_candidate: dict[str, Any] | None = None
        for pair_combo in itertools.combinations(pairs[:6], 2):
            left_keys = [pair[0] for pair in pair_combo]
            right_keys = [pair[1] for pair in pair_combo]
            stats = cached_stats(left_name, left_keys, right_name, right_keys)
            if stats.safe:
                composite_candidate = {
                    "left_sheet": left_name,
                    "right_sheet": right_name,
                    "left_keys": left_keys,
                    "right_keys": right_keys,
                    "type": "left",
                    "purpose": relation_purpose,
                    "recommended": bool(relation_purpose == "enriquecer_costos"),
                    **stats.to_dict(),
                }
                break
        if composite_candidate is not None:
            candidates.append(composite_candidate)
        elif pair_candidates:
            candidates.append(max(
                pair_candidates,
                key=lambda item: (item["overlap"], item["coverage_left"]),
            ))
    purpose_order = {
        "enriquecer_costos": 0,
        "enriquecer_referencia": 1,
        "otra_relacion": 2,
    }
    candidates.sort(
        key=lambda item: (
            not item["safe"],
            not item.get("recommended", False),
            purpose_order.get(item.get("purpose"), 3),
            -item["overlap"],
            -item["coverage_left"],
        )
    )
    return candidates


def _numeric_values(frame: pd.DataFrame, column: str) -> pd.Series:
    canonical = bool(frame.attrs.get(NUMERIC_CANONICAL_ATTR))
    return frame[column].map(
        lambda value: parse_number(
            value,
            dot3_convention="decimal" if canonical else "miles",
            comma3_convention="decimal",
        )
    )


def _metric_totals(frame: pd.DataFrame, mapping: dict[str, str]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for role in METRIC_ROLES:
        column = mapping.get(role)
        if not column or column not in frame.columns:
            continue
        values = _numeric_values(frame, column)
        totals[role] = float(pd.to_numeric(values, errors="coerce").sum())
    return totals


def append_compatible_frames(
    frames: dict[str, pd.DataFrame],
    mappings: dict[str, dict[str, str]],
    *,
    allow_single: bool = False,
) -> tuple[pd.DataFrame, dict[str, str], dict[str, Any]]:
    if len(frames) < 2 and not (allow_single and len(frames) == 1):
        raise ValueError("Se necesitan al menos dos hojas para apilar.")
    names = list(frames)
    first_name = names[0]
    first = frames[first_name]
    columns = [str(column) for column in first.columns]
    union_columns = list(columns)
    for frame in frames.values():
        for column in map(str, frame.columns):
            if column not in union_columns:
                union_columns.append(column)
    column_sets = [set(map(str, frame.columns)) for frame in frames.values()]
    common_columns = set.intersection(*column_sets)
    # Una columna auxiliar opcional (p. ej. Observación.1 en un solo mes) no
    # vuelve incompatibles tablas con el mismo grano. La base común debe cubrir
    # al menos 80% del esquema más pequeño; tipos y roles se validan abajo.
    smallest_schema = min((len(columns) for columns in column_sets), default=0)
    if not smallest_schema or len(common_columns) / smallest_schema < 0.8:
        raise ValueError("Las hojas seleccionadas no tienen columnas compatibles.")
    if "hoja_origen" in columns:
        raise ValueError("Ya existe una columna hoja_origen.")
    first_types = {
        column: _column_type(first, column)
        for column in columns
        if column in common_columns
    }
    first_mapping = resolve_mapping(columns, mappings.get(first_name))
    parts: list[pd.DataFrame] = []
    missing_by_sheet: dict[str, list[str]] = {}
    for name in names:
        frame = frames[name]
        current_columns = set(map(str, frame.columns))
        current = frame.reindex(columns=union_columns)
        current_types = {
            column: _column_type(current, column) for column in first_types
        }
        if current_types != first_types:
            raise ValueError("Las hojas seleccionadas tienen tipos incompatibles.")
        current_mapping = resolve_mapping(
            [str(column) for column in frame.columns], mappings.get(name)
        )
        for role, column in first_mapping.items():
            if current_mapping.get(role) != column:
                raise ValueError("Las hojas seleccionadas tienen interpretaciones incompatibles.")
        missing_by_sheet[name] = [
            column for column in union_columns if column not in current_columns
        ]
        part = current.copy()
        part.insert(0, "hoja_origen", name)
        parts.append(part)
    combined = pd.concat(parts, ignore_index=True)
    if all(bool(frame.attrs.get(NUMERIC_CANONICAL_ATTR)) for frame in frames.values()):
        combined.attrs[NUMERIC_CANONICAL_ATTR] = True
    combined_mapping = dict(first_mapping)
    for role in ("monto", "costo"):
        column = combined_mapping.get(role)
        if column and column in combined.columns and detect_currency(combined[column]).mixta:
            raise ValueError("Las hojas usan monedas incompatibles y no se pueden apilar.")
    return combined, combined_mapping, {
        "mode": "append",
        "sheets": names,
        "rows": len(combined),
        "origin_column": "hoja_origen",
        "optional_columns": {
            name: missing for name, missing in missing_by_sheet.items() if missing
        },
    }


def join_related_frames(
    frames: dict[str, pd.DataFrame],
    mappings: dict[str, dict[str, str]],
    join: dict,
) -> tuple[pd.DataFrame, dict[str, str], dict[str, Any]]:
    left_name = join["left_sheet"]
    right_name = join["right_sheet"]
    left = frames[left_name].copy()
    right = frames[right_name].copy()
    left_keys = join["left_keys"]
    right_keys = join["right_keys"]
    stats = relation_stats(left, left_keys, right, right_keys)
    if not stats.safe:
        raise ValueError(stats.reason or "La relacion no es segura.")
    left_mapping = resolve_mapping([str(column) for column in left.columns], mappings.get(left_name))
    right_mapping = resolve_mapping([str(column) for column in right.columns], mappings.get(right_name))
    before_totals = _metric_totals(left, left_mapping)
    # Un costo unitario del maestro SÍ debe viajar a la venta para poder
    # calcular Cantidad × Costo_Unitario. Se excluyen monto/cantidad del
    # maestro para que nunca se sumen como hechos transaccionales.
    right_metric_columns = {
        column for role, column in right_mapping.items() if role in {"monto", "cantidad"}
    }
    enrich_columns = [
        str(column)
        for column in right.columns
        if str(column) not in right_keys and str(column) not in right_metric_columns
    ]
    right_subset = right[right_keys + enrich_columns].copy()
    rename: dict[str, str] = {}
    for column in enrich_columns:
        if column in left.columns:
            rename[column] = f"{column}_{right_name}"
    right_subset = right_subset.rename(columns=rename)
    merged = left.merge(
        right_subset,
        how="left",
        left_on=left_keys,
        right_on=right_keys,
        validate="many_to_one",
        sort=False,
    )
    if left.attrs.get(NUMERIC_CANONICAL_ATTR):
        merged.attrs[NUMERIC_CANONICAL_ATTR] = True
    redundant_right_keys = [
        right_key
        for left_key, right_key in zip(left_keys, right_keys, strict=True)
        if right_key != left_key and right_key in merged.columns
    ]
    if redundant_right_keys:
        merged = merged.drop(columns=redundant_right_keys)
    derived_cost: dict[str, Any] | None = None
    right_cost_original = right_mapping.get("costo")
    right_cost_column = rename.get(right_cost_original, right_cost_original) if right_cost_original else None
    quantity_column = left_mapping.get("cantidad")
    amount_column = left_mapping.get("monto")
    if (
        right_cost_column
        and right_cost_column in merged.columns
        and is_unit_cost_column(right_cost_original)
        and quantity_column
        and quantity_column in merged.columns
        and amount_column
        and amount_column in merged.columns
    ):
        quantity = _numeric_values(merged, quantity_column).astype(float)
        unit_cost = _numeric_values(merged, right_cost_column).astype(float)
        amount = _numeric_values(merged, amount_column).astype(float)
        paired = quantity.notna() & unit_cost.notna()
        cost_name = "Costo_Venta"
        utility_name = "Utilidad_Bruta"
        margin_name = "Margen_Bruto"
        for base, variable in (
            (cost_name, "cost_name"),
            (utility_name, "utility_name"),
            (margin_name, "margin_name"),
        ):
            candidate = base
            suffix = 2
            while candidate in merged.columns:
                candidate = f"{base}_{suffix}"
                suffix += 1
            if variable == "cost_name":
                cost_name = candidate
            elif variable == "utility_name":
                utility_name = candidate
            else:
                margin_name = candidate
        merged[cost_name] = (quantity * unit_cost).where(paired)
        paired_amount = paired & amount.notna()
        merged[utility_name] = (amount - merged[cost_name]).where(paired_amount)
        merged[margin_name] = (
            merged[utility_name] / amount.where(amount != 0)
        ).where(paired_amount)
        left_mapping = dict(left_mapping)
        left_mapping["costo"] = cost_name
        derived_cost = {
            "columna_costo_unitario": right_cost_column,
            "columna_costo_venta": cost_name,
            "columna_utilidad_bruta": utility_name,
            "columna_margen_bruto": margin_name,
            "filas_con_costo": int(paired.sum()),
            "filas_con_utilidad": int(paired_amount.sum()),
            "cobertura_costos_pct": round(float(paired.mean() * 100), 2) if len(merged) else 0.0,
        }
    after_totals = _metric_totals(merged, left_mapping)
    if len(merged) != len(left):
        raise ValueError("La relacion aumentaria la cantidad de filas.")
    for role, before in before_totals.items():
        after = after_totals.get(role, 0.0)
        if not math.isclose(before, after, rel_tol=1e-9, abs_tol=1e-6):
            raise ValueError(f"La relacion alteraria el total de {role}.")
    left_keys_values = _key_series(left, left_keys)
    right_key_values = set(_key_series(right, right_keys).dropna().tolist())
    unmatched = int((left_keys_values.notna() & ~left_keys_values.isin(right_key_values)).sum())
    return merged, left_mapping, {
        "mode": "join",
        "left_sheet": left_name,
        "right_sheet": right_name,
        "left_keys": left_keys,
        "right_keys": right_keys,
        "cardinality": stats.cardinality,
        "rows_before": len(left),
        "rows_after": len(merged),
        "totals_before": before_totals,
        "totals_after": after_totals,
        "coverage": stats.coverage_left,
        "overlap": stats.overlap,
        "filas_sin_correspondencia": unmatched,
        "costo_derivado": derived_cost,
    }


def build_analysis_frame(
    frames: dict[str, pd.DataFrame],
    mappings: dict[str, dict[str, str]],
    scope: dict,
) -> tuple[pd.DataFrame, dict[str, str], dict[str, Any]]:
    mode = scope["mode"]
    selected = {name: frames[name] for name in scope["sheets"]}
    if mode == "single":
        name = scope["active_sheet"]
        frame = selected[name]
        mapping = resolve_mapping([str(column) for column in frame.columns], mappings.get(name))
        return frame.copy(), mapping, {"mode": "single", "sheets": [name], "rows": len(frame)}
    if mode == "append":
        return append_compatible_frames(selected, mappings)
    if mode == "join":
        return join_related_frames(selected, mappings, scope["join"])

    append_names = scope["append_sheets"]
    append_frames = {name: selected[name] for name in append_names}
    appended, appended_mapping, append_provenance = append_compatible_frames(
        append_frames, mappings, allow_single=True
    )
    right_name = scope["join"]["right_sheet"]
    synthetic_left = "__ventas_apiladas__"
    joined, joined_mapping, join_provenance = join_related_frames(
        {synthetic_left: appended, right_name: selected[right_name]},
        {synthetic_left: appended_mapping, right_name: mappings.get(right_name, {})},
        {
            **scope["join"],
            "left_sheet": synthetic_left,
            "right_sheet": right_name,
        },
    )
    return joined, joined_mapping, {
        "mode": "append_join",
        "append": append_provenance,
        "join": join_provenance,
        "rows": len(joined),
    }
