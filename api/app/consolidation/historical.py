"""Estrategias de cohorte y anexado histórico conservador."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


def build_cohort_ids(ids: Iterable[object], cohort: int, strategy: str = "cohort_and_id") -> tuple[pd.Series, str]:
    normalized = pd.Series(ids, dtype="string").str.strip()
    if normalized.isna().any() or normalized.eq("").any():
        raise ValueError("No se puede construir cohorte_id con id_aux vacío.")
    if strategy != "cohort_and_id":
        raise ValueError(f"Estrategia de cohorte_id no soportada: {strategy}")
    result = str(cohort) + ":" + normalized
    if result.duplicated().any():
        raise ValueError("cohorte_id resultó duplicado.")
    return result, "generated_fallback"


def append_historical(
    historical: pd.DataFrame,
    annual: pd.DataFrame,
    *,
    cohort_column: str = "cohorte",
    cohort: int = 2026,
) -> tuple[pd.DataFrame | None, list[str]]:
    warnings: list[str] = []
    if cohort_column in historical.columns:
        existing = historical[cohort_column].astype("string").str.strip()
        if existing.eq(str(cohort)).any():
            return None, ["historical_already_contains_cohort"]
    if list(historical.columns) != list(annual.columns):
        return None, ["historical_schema_incompatible"]
    combined = pd.concat([historical, annual], ignore_index=True, copy=False)
    if len(combined) != len(historical) + len(annual):
        raise RuntimeError("El anexado histórico perdió filas.")
    return combined, warnings
