"""Observed product inactivity, never inferred from a truncated top ranking."""

import pandas as pd

from .quality import find_column
from .standardize import physical_missing_mask


def product_activity(frame, product_column, dates, amounts, monthly):
    key = (find_column(frame.columns, "sku", "producto")
           or find_column(frame.columns, "id", "producto")
           or find_column(frame.columns, "codigo", "producto"))
    if not key or not product_column:
        return None
    complete = sorted(row["mes"] for row in monthly if not row.get("parcial") and row.get("ingresos") is not None)
    if len(complete) < 3:
        return None
    end = pd.Period(complete[-1], freq="M")
    window = [str(end - offset) for offset in (2, 1, 0)]
    if complete[-3:] != window:
        return None
    known_key = ~physical_missing_mask(frame[key])
    data = pd.DataFrame({
        "key": frame[key].astype("string").str.strip(),
        "name": frame[product_column].astype("string"),
        "date": dates, "amount": amounts,
    }).loc[known_key]
    positive = data[data["amount"] > 0]
    # An undated positive sale could invalidate any inactivity claim for its ID.
    unknown_dates = set(positive.loc[positive["date"].isna(), "key"])
    dated = positive[positive["date"].notna() & (positive["date"] < (end + 1).start_time)]
    if dated.empty:
        return None
    last = dated.groupby("key", sort=False)["date"].max()
    names = dated.sort_values("date").groupby("key", sort=False)["name"].last()
    totals = dated.groupby("key", sort=False)["amount"].sum()
    rows = []
    for identity, last_date in last.items():
        gap = end.ordinal - last_date.to_period("M").ordinal
        if gap >= 3 and identity not in unknown_dates:
            rows.append({"id": str(identity), "nombre": str(names[identity]),
                         "ultima_venta": last_date.strftime("%Y-%m-%d"), "meses_sin_venta_observada": gap,
                         "ingresos_historicos": round(float(totals[identity]), 2)})
    rows.sort(key=lambda row: (-row["meses_sin_venta_observada"], -row["ingresos_historicos"], row["id"]))
    return {"clave": key, "fecha_corte": end.end_time.strftime("%Y-%m-%d"),
            "meses_revisados": window, "productos_revisados": len(last), "total_sin_ventas": len(rows),
            "productos": rows[:10], "limite": "Ausencia de ventas positivas en el alcance observado; no prueba falta de demanda ni que el archivo contenga todas las ventas."}
