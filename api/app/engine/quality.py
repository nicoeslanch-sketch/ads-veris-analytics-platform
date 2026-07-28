"""Shared, conservative data-quality checks.

The helpers in this module only classify or measure suspicious records. They
never mutate user data. This lets cleaning, exports and analytics use the same
definition without silently deleting totals, conflicts or accounting errors.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from .mapping import strip_accents_lower
from .standardize import (
    NUMERIC_CANONICAL_ATTR,
    map_unique,
    parse_number,
    physical_missing_mask,
)


OPTIONAL_TEXT_TOKENS = (
    "observa",
    "comentario",
    "nota",
    "glosa",
    "descripcion",
    "referencia",
)


def normalized_header(value: object) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        " ",
        strip_accents_lower(str(value)).replace("_", " "),
    ).strip()


def is_optional_free_text_column(column: object) -> bool:
    header = normalized_header(column)
    return any(token in header for token in OPTIONAL_TEXT_TOKENS)


def structural_total_mask(
    frame: pd.DataFrame,
    date_column: str | None = None,
) -> pd.Series:
    """Detect footer totals such as ``TOTAL 2025`` without deleting them.

    A total label must occur near the start of the row and the row must not
    look like a normal transaction. Requiring a missing transaction date (when
    available) and a sparse row keeps ordinary products such as "Total Care"
    out of this classification.
    """

    mask = pd.Series(False, index=frame.index, dtype=bool)
    if frame.empty:
        return mask
    leading = list(frame.columns[: min(4, len(frame.columns))])
    for column in leading:
        values = frame[column].astype(str).map(strip_accents_lower).str.strip()
        mask |= values.str.match(r"^(?:gran\s+)?(?:sub\s*)?total(?:\s|$)", na=False)
    candidates = mask[mask].index
    if len(candidates) == 0:
        return mask

    # Columnas internas de trazabilidad se agregan después de leer el Excel y
    # siempre vienen completas; no deben hacer que un pie TOTAL parezca una
    # transacción densa.
    business_columns = [
        column for column in frame.columns if not str(column).startswith("_")
    ]
    candidate_frame = frame.loc[candidates, business_columns]
    empty_share = candidate_frame.apply(physical_missing_mask).mean(axis=1)
    confirmed = empty_share >= 0.35
    if date_column and date_column in frame.columns:
        confirmed &= physical_missing_mask(candidate_frame[date_column])
    mask.loc[candidates] = confirmed
    return mask


def numeric_series(frame: pd.DataFrame, column: str | None) -> pd.Series:
    if not column or column not in frame.columns:
        return pd.Series(float("nan"), index=frame.index, dtype=float)
    canonical = bool(frame.attrs.get(NUMERIC_CANONICAL_ATTR))
    return map_unique(
        frame[column].astype(str),
        lambda value: parse_number(
            value,
            dot3_convention="decimal" if canonical else "miles",
            comma3_convention="decimal",
        ),
    ).astype(float)


def find_column(
    columns: Iterable[object],
    *required: str,
    excluded: Iterable[str] = (),
) -> str | None:
    required_tokens = tuple(strip_accents_lower(token) for token in required)
    excluded_tokens = tuple(strip_accents_lower(token) for token in excluded)
    for raw in columns:
        header = normalized_header(raw)
        if all(token in header for token in required_tokens) and not any(
            token in header for token in excluded_tokens
        ):
            return str(raw)
    return None


@dataclass(frozen=True)
class FormulaCheck:
    name: str
    rows: int
    evaluated: int
    examples: list[int]

    def to_dict(self) -> dict:
        return {
            "control": self.name,
            "filas_inconsistentes": self.rows,
            "filas_evaluadas": self.evaluated,
            "filas_ejemplo": self.examples,
        }


@dataclass(frozen=True)
class LineSalesEvidence:
    """Evidence that a row-level amount is a commercial net sale.

    Generic monetary names are intentionally insufficient. Confirmation
    requires quantity, unit selling price, discount, a line/product dimension,
    transaction context and a high agreement with the declared formula.
    """

    confirmed: bool
    amount_column: str | None
    quantity_column: str | None
    unit_price_column: str | None
    discount_column: str | None
    line_dimension_column: str | None
    date_column: str | None
    transaction_id_column: str | None
    evaluated_rows: int
    matching_rows: int
    mismatch_rows: int
    comparable_coverage_pct: float
    formula_match_pct: float

    def to_dict(self) -> dict:
        return {
            "confirmada": self.confirmed,
            "columna_monto": self.amount_column,
            "columna_cantidad": self.quantity_column,
            "columna_precio_unitario": self.unit_price_column,
            "columna_descuento": self.discount_column,
            "columna_dimension_linea": self.line_dimension_column,
            "columna_fecha": self.date_column,
            "columna_identificador": self.transaction_id_column,
            "filas_evaluadas": self.evaluated_rows,
            "filas_coincidentes": self.matching_rows,
            "filas_inconsistentes": self.mismatch_rows,
            "cobertura_comparable_pct": self.comparable_coverage_pct,
            "coincidencia_formula_pct": self.formula_match_pct,
            "formula": "monto = cantidad × precio unitario × (1 − descuento)",
        }


def line_sales_evidence(
    frame: pd.DataFrame,
    roles: dict[str, str] | None = None,
) -> LineSalesEvidence:
    """Confirm line sales from structure plus the commercial formula.

    The check is read-only. Inconsistent rows are reported but never changed
    or silently discarded. Percent discounts may be encoded as 0.10, 10 or
    ``10%``; they are normalized only for this validation calculation.
    """

    roles = roles or {}
    amount = roles.get("monto") or find_column(
        frame.columns, "monto", excluded=("mensual", "cuota", "uf")
    )
    quantity = roles.get("cantidad") or find_column(frame.columns, "cantidad")
    unit_price = find_column(
        frame.columns, "precio", "unitario", excluded=("costo",)
    ) or find_column(
        frame.columns, "precio", "unit", excluded=("costo",)
    )
    discount = (
        find_column(frame.columns, "descuento")
        or find_column(frame.columns, "dcto")
        or find_column(frame.columns, "desc", "pct")
    )
    line_dimension = (
        find_column(frame.columns, "tipo", "linea")
        or find_column(frame.columns, "producto")
        or find_column(frame.columns, "servicio")
        or find_column(frame.columns, "item")
    )
    date = roles.get("fecha") or find_column(frame.columns, "fecha")
    transaction_id = (
        find_column(frame.columns, "id", "linea")
        or find_column(frame.columns, "numero", "ot")
        or find_column(frame.columns, "n", "ot")
        or find_column(frame.columns, "id", "orden")
        or find_column(frame.columns, "documento")
    )
    required = (amount, quantity, unit_price, discount, line_dimension)
    if not all(required) or not (date or transaction_id) or frame.empty:
        return LineSalesEvidence(
            False, amount, quantity, unit_price, discount, line_dimension,
            date, transaction_id, 0, 0, 0, 0.0, 0.0,
        )

    actual = numeric_series(frame, amount)
    units = numeric_series(frame, quantity)
    price = numeric_series(frame, unit_price)
    discount_values = numeric_series(frame, discount)
    discount_ratio = discount_values.where(
        discount_values.abs() <= 1, discount_values / 100.0
    )
    eligible = (
        actual.notna()
        & units.notna()
        & price.notna()
        & discount_ratio.notna()
        & discount_ratio.between(0, 1)
    )
    expected = units * price * (1 - discount_ratio)
    tolerance = expected.abs().mul(0.005).clip(lower=2.0)
    matches = eligible & actual.sub(expected).abs().le(tolerance)
    evaluated = int(eligible.sum())
    matching = int(matches.sum())
    mismatches = max(evaluated - matching, 0)
    populated_amounts = max(int(actual.notna().sum()), 1)
    coverage = evaluated / populated_amounts * 100
    agreement = matching / evaluated * 100 if evaluated else 0.0
    minimum_rows = min(3, populated_amounts)
    confirmed = bool(
        evaluated >= minimum_rows
        and coverage >= 60.0
        and agreement >= 90.0
    )
    return LineSalesEvidence(
        confirmed,
        amount,
        quantity,
        unit_price,
        discount,
        line_dimension,
        date,
        transaction_id,
        evaluated,
        matching,
        mismatches,
        round(coverage, 1),
        round(agreement, 1),
    )


def formula_mismatch(
    name: str,
    actual: pd.Series,
    expected: pd.Series,
    *,
    absolute_tolerance: float = 2.0,
    relative_tolerance: float = 0.005,
    source_rows: list[int] | None = None,
    eligible: pd.Series | None = None,
) -> FormulaCheck:
    comparable = actual.notna() & expected.notna()
    if eligible is not None:
        comparable &= eligible.fillna(False)
    tolerance = expected.abs().mul(relative_tolerance).clip(lower=absolute_tolerance)
    mismatch = comparable & actual.sub(expected).abs().gt(tolerance)
    positions = [int(position) for position in mismatch[mismatch].index[:20]]
    if source_rows:
        examples = [source_rows[position] for position in positions if position < len(source_rows)]
    else:
        examples = [position + 2 for position in positions]
    return FormulaCheck(name, int(mismatch.sum()), int(comparable.sum()), examples)
