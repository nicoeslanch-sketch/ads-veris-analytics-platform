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

    candidate_frame = frame.loc[candidates]
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
