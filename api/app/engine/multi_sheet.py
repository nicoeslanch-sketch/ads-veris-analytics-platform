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
from .metrics import detect_currency
from .standardize import detect_value_type_confidence, parse_number

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


def validate_analysis_scope(raw: dict | None, available_sheets: list[str]) -> dict:
    """Contrato compacto, estricto y serializable del alcance compartido."""
    if not raw:
        active = available_sheets[0] if available_sheets else None
        return {"mode": "single", "sheets": [active] if active else [], "active_sheet": active}
    if not isinstance(raw, dict):
        raise ValueError("analysis_scope debe ser un objeto JSON.")
    unknown = set(raw) - {"mode", "sheets", "active_sheet", "join", "append_sheets"}
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
    minimum = 1 if mode == "single" else (3 if mode == "append_join" else 2)
    if len(sheets) < minimum:
        raise ValueError(f"El modo {mode} requiere al menos {minimum} hoja(s).")
    active = raw.get("active_sheet")
    active_sheet = str(active).strip() if isinstance(active, str) and active.strip() else sheets[0]
    if active_sheet not in sheets:
        raise ValueError("analysis_scope.active_sheet debe estar incluido en sheets.")
    normalized: dict[str, Any] = {"mode": mode, "sheets": sheets, "active_sheet": active_sheet}
    append_sheets: list[str] = []
    if mode == "append_join":
        append_raw = raw.get("append_sheets")
        if not isinstance(append_raw, list) or not all(isinstance(item, str) for item in append_raw):
            raise ValueError("append_join requiere append_sheets.")
        append_sheets = list(dict.fromkeys(item.strip() for item in append_raw if item.strip()))
        if len(append_sheets) < 2 or any(name not in sheets for name in append_sheets):
            raise ValueError("append_join requiere al menos dos hojas compatibles incluidas.")
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
    left_valid = left_series.dropna()
    right_valid = right_series.dropna()
    coverage_left = len(left_valid) / max(len(left), 1)
    coverage_right = len(right_valid) / max(len(right), 1)
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
    """Candidatas sin valores de usuario: solo nombres y estadisticas."""
    del mappings  # reservado para reglas semanticas adicionales
    candidates: list[dict[str, Any]] = []
    for first_name, second_name in itertools.combinations(frames, 2):
        first = frames[first_name]
        second = frames[second_name]
        pairs = _candidate_pairs(first, second)
        safe_single = False
        for first_key, second_key in pairs:
            orientations = [
                (first_name, second_name, first, second, [first_key], [second_key]),
                (second_name, first_name, second, first, [second_key], [first_key]),
            ]
            best = max(
                orientations,
                key=lambda item: relation_stats(item[2], item[4], item[3], item[5]).unique_right,
            )
            stats = relation_stats(best[2], best[4], best[3], best[5])
            safe_single = safe_single or stats.safe
            candidates.append(
                {
                    "left_sheet": best[0],
                    "right_sheet": best[1],
                    "left_keys": best[4],
                    "right_keys": best[5],
                    "type": "left",
                    **stats.to_dict(),
                }
            )
        if safe_single or len(pairs) < 2:
            continue
        for pair_combo in itertools.combinations(pairs[:6], 2):
            first_keys = [pair[0] for pair in pair_combo]
            second_keys = [pair[1] for pair in pair_combo]
            orientations = [
                (first_name, second_name, first, second, first_keys, second_keys),
                (second_name, first_name, second, first, second_keys, first_keys),
            ]
            for left_name, right_name, left, right, left_keys, right_keys in orientations:
                stats = relation_stats(left, left_keys, right, right_keys)
                if stats.safe:
                    candidates.append(
                        {
                            "left_sheet": left_name,
                            "right_sheet": right_name,
                            "left_keys": left_keys,
                            "right_keys": right_keys,
                            "type": "left",
                            **stats.to_dict(),
                        }
                    )
                    break
            if candidates and candidates[-1].get("safe"):
                break
    candidates.sort(key=lambda item: (not item["safe"], -item["overlap"], -item["coverage_left"]))
    return candidates


def _metric_totals(frame: pd.DataFrame, mapping: dict[str, str]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for role in METRIC_ROLES:
        column = mapping.get(role)
        if not column or column not in frame.columns:
            continue
        values = frame[column].map(parse_number)
        totals[role] = float(pd.to_numeric(values, errors="coerce").sum())
    return totals


def append_compatible_frames(
    frames: dict[str, pd.DataFrame], mappings: dict[str, dict[str, str]]
) -> tuple[pd.DataFrame, dict[str, str], dict[str, Any]]:
    if len(frames) < 2:
        raise ValueError("Se necesitan al menos dos hojas para apilar.")
    names = list(frames)
    first_name = names[0]
    first = frames[first_name]
    columns = [str(column) for column in first.columns]
    if "hoja_origen" in columns:
        raise ValueError("Ya existe una columna hoja_origen.")
    first_types = {column: _column_type(first, column) for column in columns}
    first_mapping = resolve_mapping(columns, mappings.get(first_name))
    parts: list[pd.DataFrame] = []
    for name in names:
        frame = frames[name]
        if set(map(str, frame.columns)) != set(columns):
            raise ValueError("Las hojas seleccionadas no tienen columnas compatibles.")
        current = frame.reindex(columns=columns)
        current_types = {column: _column_type(current, column) for column in columns}
        if current_types != first_types:
            raise ValueError("Las hojas seleccionadas tienen tipos incompatibles.")
        current_mapping = resolve_mapping(columns, mappings.get(name))
        for role, column in first_mapping.items():
            if current_mapping.get(role) != column:
                raise ValueError("Las hojas seleccionadas tienen interpretaciones incompatibles.")
        part = current.copy()
        part.insert(0, "hoja_origen", name)
        parts.append(part)
    combined = pd.concat(parts, ignore_index=True)
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
        and quantity_column
        and quantity_column in merged.columns
        and amount_column
        and amount_column in merged.columns
    ):
        quantity = merged[quantity_column].map(parse_number).astype(float)
        unit_cost = merged[right_cost_column].map(parse_number).astype(float)
        amount = merged[amount_column].map(parse_number).astype(float)
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
            "filas_con_costo": int(paired_amount.sum()),
            "cobertura_costos_pct": round(float(paired_amount.mean() * 100), 1) if len(merged) else 0.0,
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
        append_frames, mappings
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
