"""Resolución determinística de Oferta 2026 sin keep=first."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

import pandas as pd

from ..codebooks import normalize_code


def resolve_offer_frame(
    offer: pd.DataFrame,
    output_columns: Sequence[str],
    *,
    cohort_value: str = "OFE_2026",
) -> tuple[pd.DataFrame, dict[str, int]]:
    required = {"Año", "Demre", *output_columns}
    missing = sorted(required - set(offer.columns))
    if missing:
        raise ValueError(f"Oferta no contiene columnas declaradas: {', '.join(missing)}")
    scoped = offer.loc[offer["Año"].astype("string").str.strip() == cohort_value, ["Demre", "Vigencia", *output_columns]].copy()
    scoped["Demre"] = scoped["Demre"].map(normalize_code)
    records: list[dict[str, object]] = []
    counts: Counter[str] = Counter()
    for code, group in scoped.groupby("Demre", sort=False, dropna=False):
        if not code:
            continue
        signatures = {
            tuple(str(value).strip() if value is not None else "" for value in row)
            for row in group[list(output_columns)].itertuples(index=False, name=None)
        }
        resolution = "offer_unique"
        chosen: tuple[str, ...] | None = None
        if len(signatures) == 1:
            chosen = next(iter(signatures))
        else:
            active = group[group["Vigencia"].astype("string").str.strip().str.casefold() == "vigente con estudiantes nuevos"]
            active_signatures = {
                tuple(str(value).strip() if value is not None else "" for value in row)
                for row in active[list(output_columns)].itertuples(index=False, name=None)
            }
            if len(active_signatures) == 1:
                chosen = next(iter(active_signatures))
                resolution = "offer_resolved_by_vigencia"
        if chosen is None:
            counts["offer_ambiguous"] += 1
            continue
        record = {"codigo_carrera": code, "offer_resolution": resolution}
        record.update(dict(zip(output_columns, chosen, strict=True)))
        records.append(record)
        counts[resolution] += 1
    return pd.DataFrame.from_records(records), dict(counts)
