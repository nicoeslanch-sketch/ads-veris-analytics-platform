"""Bounded, ID-based product history and conservative recurring-peak evidence."""

import pandas as pd

from .standardize import physical_missing_mask


def product_patterns(keys, names, dates, amounts, *, complete_months):
    if amounts.isin([float('inf'), float('-inf')]).any():
        return None
    data = pd.DataFrame({"id": keys.astype("string").str.strip(),
                         "nombre": names.astype("string"), "fecha": dates,
                         "importe": amounts})
    data = data.loc[~physical_missing_mask(keys) & amounts.notna()]
    undated = set(data.loc[data.fecha.isna() & data.importe.gt(0), "id"])
    data = data.loc[data.fecha.notna()].copy()
    if data.empty:
        return None
    data["mes"] = data.fecha.dt.strftime("%Y-%m")
    data["positivas"] = data.importe.clip(lower=0)
    totals = data.groupby("id", sort=False).positivas.sum().sort_values(ascending=False, kind="stable")
    names_by_id = data.sort_values("fecha").groupby("id").nombre.last()
    monthly = data.groupby(["id", "mes"])[["importe", "positivas"]].sum()
    if monthly.isin([float('inf'), float('-inf')]).any().any():
        return None
    observed = set(data.mes)
    # A missing month is not proof of zero activity. Only years observed in all
    # twelve months, with non-partial bounds, qualify for repeated-peak claims.
    complete = set(complete_months) & observed
    years = sorted(year for year in {m[:4] for m in complete}
                   if all(f"{year}-{month:02d}" in complete for month in range(1, 13)))
    years = years[-5:]
    peaks = []
    total_peaks = 0
    if len(years) >= 2:
        candidates = monthly.reset_index()
        candidates['ano'] = candidates.mes.str[:4]
        candidates = candidates.loc[candidates.ano.isin(years)]
        yearly = candidates.groupby(['id', 'ano']).positivas.agg(['sum', 'max'])
        candidates = candidates.join(yearly, on=['id', 'ano'])
        candidates = candidates.loc[candidates.positivas.eq(candidates['max'])
                                    & candidates['sum'].gt(0)
                                    & candidates.positivas.ge(candidates['sum'] * .30)]
        candidates['month'] = candidates.mes.str[-2:]
        eligibility = candidates.groupby('id').agg(rows=('ano', 'size'), years=('ano', 'nunique'), months=('month', 'nunique'))
        eligible = eligibility.loc[eligibility.rows.eq(len(years)) & eligibility.years.eq(len(years)) & eligibility.months.eq(1)]
        eligible = eligible.loc[~eligible.index.isin(undated)]
        total_peaks = len(eligible)
        leaders = totals.loc[totals.index.isin(eligible.index)].head(8).index
        candidates = candidates.loc[candidates.id.isin(leaders)]
        for identity, rows in candidates.groupby('id', sort=False):
            evidence = [{"ano": row.ano, "mes": int(row.mes[-2:]),
                         "ventas_positivas": round(float(row.positivas), 2),
                         "participacion_pct": round(float(row.positivas / row['sum'] * 100), 1)}
                        for _, row in rows.sort_values('ano').iterrows()]
            if len(evidence) == len(years) and len({e["mes"] for e in evidence}) == 1:
                peaks.append({"id": str(identity), "nombre": str(names_by_id[identity]),
                              "mes": evidence[0]["mes"], "evidencia": evidence})
    peaks.sort(key=lambda p: (-float(totals[p["id"]]), p["id"]))
    # Always detect over the full population, then bound only the presentation.
    visible = list(dict.fromkeys([p["id"] for p in peaks[:4]] + list(totals.index[:8])))[:12]
    months = sorted(observed)[-36:]
    series = []
    for identity in visible:
        values = monthly.loc[identity]
        series.append({"id": str(identity), "nombre": str(names_by_id[identity]),
                       "valores": [{"mes": month,
                                    "ventas_netas": round(float(values.loc[month, "importe"]), 2) if month in values.index else 0,
                                    "ventas_positivas": round(float(values.loc[month, "positivas"]), 2) if month in values.index else 0}
                                   for month in months]})
    return {"meses": months, "anos_comparables": years, "productos_revisados": len(totals),
            "series": series, "picos_recurrentes": peaks[:8], "total_picos": total_peaks,
            "criterio": "Mismo mes con al menos 30% de las ventas positivas anuales en dos o mas anos con doce meses observados. No es una prueba estadistica ni una prediccion.",
            "limite": "Ceros indican ausencia de ventas en los registros fechados de ese mes; no prueban stock disponible ni cobertura completa del negocio. Ventas positivas excluyen devoluciones; ventas netas las incluyen."}
