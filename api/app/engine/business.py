"""Safe multi-sheet business analysis for small and medium businesses.

The module keeps every grain separate and only performs many-to-one lookups or
explicit pre-aggregations. It never joins raw collections, cost history or
inventory directly to sales, which prevents accidental row multiplication.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd

from .mapping import strip_accents_lower
from .quality import (
    find_column,
    formula_mismatch,
    normalized_header,
    numeric_series,
    structural_total_mask,
)
from .standardize import map_unique, parse_date, physical_missing_mask


def _text_key(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = " ".join(strip_accents_lower(str(value)).split())
    return text or None


def _keys(series: pd.Series) -> pd.Series:
    return series.map(_text_key)


def _dates(frame: pd.DataFrame, column: str | None) -> pd.Series:
    if not column or column not in frame.columns:
        return pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns]")
    return pd.to_datetime(map_unique(frame[column].astype(str), parse_date), errors="coerce")


def _status_mask(frame: pd.DataFrame, column: str | None, pattern: str) -> pd.Series:
    if not column or column not in frame.columns:
        return pd.Series(False, index=frame.index)
    values = frame[column].astype(str).map(strip_accents_lower).str.strip()
    return values.str.contains(pattern, regex=True, na=False)


def _date_filter(dates: pd.Series, date_from: str | None, date_to: str | None) -> pd.Series:
    mask = pd.Series(True, index=dates.index)
    if date_from:
        mask &= dates.ge(pd.to_datetime(date_from))
    if date_to:
        text = str(date_to).strip()
        end = (
            pd.Period(text, freq="M").end_time.normalize()
            if len(text) == 7
            else pd.to_datetime(text)
        )
        mask &= dates.le(end)
    if date_from or date_to:
        mask &= dates.notna()
    return mask


def _sheet_kind(name: str, frame: pd.DataFrame) -> str:
    sheet = normalized_header(name)
    sheet_tokens = set(sheet.split())
    headers = " | ".join(normalized_header(column) for column in frame.columns)
    if sheet_tokens & {"venta", "ventas"} or (
        "id documento" in headers and "monto venta" in headers
    ):
        return "ventas"
    if "historial" in sheet and "costo" in sheet:
        return "historial_costos"
    if "costo" in sheet and "producto" in sheet:
        return "costos"
    if "inventario" in sheet or "stock sistema" in headers:
        return "inventario"
    if "compra" in sheet or "id compra" in headers:
        return "compras"
    if "gasto" in sheet or "id gasto" in headers:
        return "gastos"
    if "cobran" in sheet or "id pago" in headers:
        return "cobranzas"
    if "meta" in sheet or "meta venta" in headers:
        return "metas"
    if "producto" in sheet or ("sku producto" in headers and "precio lista" in headers):
        return "productos"
    if "cliente" in sheet or "id cliente" in headers:
        return "clientes"
    if "proveedor" in sheet or "id proveedor" in headers:
        return "proveedores"
    if "sucursal" in sheet or ("id sucursal" in headers and "comuna" in headers):
        return "sucursales"
    if "vendedor" in sheet or "id vendedor" in headers:
        return "vendedores"
    return "otra"


def classify_business_sheets(frames: dict[str, pd.DataFrame]) -> dict[str, list[str]]:
    classified: dict[str, list[str]] = defaultdict(list)
    for name, frame in frames.items():
        classified[_sheet_kind(name, frame)].append(name)
    return dict(classified)


def _append_sales(frames: dict[str, pd.DataFrame], names: list[str]) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    canonical = True
    for name in names:
        part = frames[name].copy()
        canonical &= bool(part.attrs.get("adsveris_numeric_canonical"))
        part["_hoja_origen"] = name
        parts.append(part)
    combined = pd.concat(parts, ignore_index=True, sort=False) if parts else pd.DataFrame()
    if canonical:
        combined.attrs["adsveris_numeric_canonical"] = True
    return combined


def _unique_reference(
    frame: pd.DataFrame | None,
    key_column: str | None,
    value_columns: list[str],
) -> tuple[pd.DataFrame, dict[str, int]]:
    if frame is None or not key_column or key_column not in frame.columns:
        return pd.DataFrame(), {"claves": 0, "duplicadas": 0, "conflictivas": 0}
    reference = frame[[key_column, *[c for c in value_columns if c in frame.columns]]].copy()
    reference["_key"] = _keys(reference[key_column])
    reference = reference[reference["_key"].notna()]
    duplicated = reference["_key"].duplicated(keep=False)
    conflict_keys: set[str] = set()
    for key, group in reference.loc[duplicated].groupby("_key", sort=False):
        if len(group.drop(columns=[key_column, "_key"]).drop_duplicates()) > 1:
            conflict_keys.add(str(key))
    safe = reference[~reference["_key"].isin(conflict_keys)].drop_duplicates(
        subset=["_key"], keep="first"
    )
    safe.attrs.update(frame.attrs)
    return safe, {
        "claves": int(reference["_key"].nunique()),
        "duplicadas": int(reference.loc[duplicated, "_key"].nunique()),
        "conflictivas": len(conflict_keys),
    }


def _relation_quality(
    source: pd.DataFrame | None,
    source_column: str | None,
    reference: pd.DataFrame | None,
    reference_column: str | None,
    label: str,
) -> dict[str, Any] | None:
    if (
        source is None
        or reference is None
        or not source_column
        or not reference_column
        or source_column not in source.columns
        or reference_column not in reference.columns
    ):
        return None
    source_keys = _keys(source[source_column])
    reference_key_series = _keys(reference[reference_column]).dropna()
    reference_keys = set(reference_key_series)
    informed = source_keys.notna()
    orphan = informed & ~source_keys.isin(reference_keys)
    missing = ~informed
    valid = informed & ~orphan
    # P1-8: un maestro con la clave repetida hace que "válida" sea ambigua —
    # cuál de las filas duplicadas es la referencia real. Se informa aparte
    # de huérfanas/sin_clave, sin bloquear ni alterar el conteo de arriba.
    key_counts = reference_key_series.value_counts()
    duplicated_master_keys = int((key_counts > 1).sum())
    return {
        "relacion": label,
        "tipo": "clave",
        "filas": int(len(source)),
        "validas": int(valid.sum()),
        "huerfanas": int(orphan.sum()),
        "sin_clave": int(missing.sum()),
        "conflictos": 0,
        "maestro_duplicado": duplicated_master_keys,
        "maestro_conflictivo": 0,
        "cobertura_pct": round(float(valid.sum()) / max(len(source), 1) * 100, 1),
        "ejemplos": sorted({str(value) for value in source.loc[orphan, source_column].head(8)}),
    }


def _attribute_consistency(
    source: pd.DataFrame | None,
    source_key: str | None,
    source_attr: str | None,
    reference: pd.DataFrame | None,
    reference_key: str | None,
    reference_attr: str | None,
    label: str,
) -> dict[str, Any] | None:
    """Para filas cuya CLAVE sí existe en el maestro, cuenta cuántas traen un
    ATRIBUTO (p. ej. el nombre del producto) distinto al del maestro. Una clave
    válida con nombre incoherente no es huérfana, pero delata un error de
    captura que un join a ciegas propagaría (SKU correcto, producto equivocado).
    """
    if (
        source is None
        or reference is None
        or not source_key
        or not source_attr
        or not reference_key
        or not reference_attr
        or source_key not in source.columns
        or source_attr not in source.columns
        or reference_key not in reference.columns
        or reference_attr not in reference.columns
    ):
        return None
    ref = reference[[reference_key, reference_attr]].copy()
    ref["_k"] = _keys(ref[reference_key])
    ref = ref[ref["_k"].notna()]
    # P1-8: un maestro duplicado hace que "el nombre correcto" para esa clave
    # sea ambiguo. Se cuenta aparte de los conflictos de atributo por fila —
    # keep="first" sigue siendo la referencia usada para comparar (no cambia
    # el criterio de negocio), pero ahora se informa cuándo esa elección era
    # arbitraria entre valores REALMENTE distintos (maestro conflictivo) o
    # solo copias exactas repetidas (maestro duplicado sin conflicto).
    dedup_keys = ref["_k"].value_counts()
    duplicated_keys = dedup_keys[dedup_keys > 1].index
    maestro_duplicado = int(len(duplicated_keys))
    maestro_conflictivo = 0
    if maestro_duplicado:
        attr_variety = (
            ref[ref["_k"].isin(duplicated_keys)]
            .assign(_attr_norm=ref[reference_attr].map(_text_key))
            .groupby("_k")["_attr_norm"]
            .nunique(dropna=True)
        )
        maestro_conflictivo = int((attr_variety > 1).sum())
    ref = ref.drop_duplicates(subset=["_k"], keep="first")
    ref_map = {
        key: _text_key(value)
        for key, value in zip(ref["_k"], ref[reference_attr])
        if _text_key(value) is not None
    }
    source_keys = _keys(source[source_key])
    source_attr_norm = source[source_attr].map(_text_key)
    # Solo filas con la clave presente en el maestro y ambos nombres legibles.
    resolvable = source_keys.map(lambda key: key in ref_map) & source_attr_norm.notna()
    expected = source_keys.map(ref_map)
    mismatch = resolvable & (source_attr_norm != expected)
    checked = int(resolvable.sum())
    conflicts = int(mismatch.sum())
    return {
        "relacion": label,
        "tipo": "atributo",
        "filas": checked,
        "validas": checked - conflicts,
        # No son huérfanas: la CLAVE existe en el maestro. Ver "conflictos".
        "huerfanas": 0,
        "sin_clave": 0,
        "conflictos": conflicts,
        "maestro_duplicado": maestro_duplicado,
        "maestro_conflictivo": maestro_conflictivo,
        "cobertura_pct": round((checked - conflicts) / max(checked, 1) * 100, 1),
        "ejemplos": sorted({str(value) for value in source.loc[mismatch, source_key].head(8)}),
    }


def _group_profit(
    frame: pd.DataFrame,
    column: str | None,
    amount: pd.Series,
    cost: pd.Series,
    limit: int = 15,
) -> list[dict[str, Any]]:
    if not column or column not in frame.columns:
        return []
    labels = frame[column].copy()
    labels = labels.mask(physical_missing_mask(labels), "Sin clasificar")
    grouped = pd.DataFrame(
        {
            "nombre": labels.astype(str).str.strip().replace("", "Sin clasificar"),
            "ingresos": amount,
            "costo": cost,
        }
    )
    grouped["pareada"] = grouped["ingresos"].notna() & grouped["costo"].notna()
    grouped["ingreso_pareado"] = grouped["ingresos"].where(grouped["pareada"])
    grouped["costo_pareado"] = grouped["costo"].where(grouped["pareada"])
    total_positive = float(grouped.loc[grouped["ingresos"] > 0, "ingresos"].sum())
    rows: list[dict[str, Any]] = []
    for name, values in grouped.groupby("nombre", dropna=False):
        income = float(values["ingresos"].dropna().sum())
        paired_income = float(values["ingreso_pareado"].dropna().sum())
        paired_cost = float(values["costo_pareado"].dropna().sum())
        paired_rows = int(values["pareada"].sum())
        profit = paired_income - paired_cost if paired_rows else None
        rows.append(
            {
                "nombre": str(name) or "Sin clasificar",
                "ingresos": round(income, 2),
                "participacion_pct": round(
                    float(values.loc[values["ingresos"] > 0, "ingresos"].sum())
                    / total_positive
                    * 100,
                    2,
                )
                if total_positive
                else None,
                "costo": round(paired_cost, 2) if paired_rows else None,
                "utilidad": round(profit, 2) if profit is not None else None,
                "margen_pct": round(profit / paired_income * 100, 2)
                if profit is not None and paired_income
                else None,
                "filas": int(len(values)),
                "filas_pareadas": paired_rows,
                "cobertura_costos_pct": round(paired_rows / max(len(values), 1) * 100, 1),
            }
        )
    rows.sort(key=lambda item: item["ingresos"], reverse=True)
    return rows[:limit]


def _reference_values(
    source: pd.DataFrame,
    source_key: str | None,
    reference: pd.DataFrame | None,
    reference_key: str | None,
    value_column: str | None,
) -> pd.Series:
    """Many-to-one lookup that refuses conflicting reference keys."""

    if not source_key or not reference_key or not value_column:
        return pd.Series(None, index=source.index, dtype=object)
    safe, _ = _unique_reference(reference, reference_key, [value_column])
    if safe.empty or value_column not in safe.columns:
        return pd.Series(None, index=source.index, dtype=object)
    lookup = dict(zip(safe["_key"], safe[value_column], strict=False))
    return _keys(source[source_key]).map(lookup)


def _cost_outlier_limit(values: pd.Series) -> float | None:
    positive = values[values > 0].dropna()
    if len(positive) < 20:
        return None
    q1, q3 = positive.quantile(0.25), positive.quantile(0.75)
    spread = float(q3 - q1)
    return float(q3 + 5 * spread) if spread > 0 else None


def _cost_outlier_mask(values: pd.Series, groups: pd.Series | None = None) -> pd.Series:
    """P1-6: máscara de costos atípicos -- NUNCA se usa para excluir datos
    reales de un cálculo, solo para marcarlos aparte y que alguien los
    revise (un costo alto de verdad no deja de ser un costo real).

    Con ``groups`` (ej. categoría/subcategoría), el límite se calcula POR
    GRUPO cuando el grupo trae evidencia suficiente (>=20 valores
    positivos, mismo mínimo que el límite global) -- un costo de
    electrónica no debe compararse contra el de un insumo de aseo. Un
    grupo sin evidencia propia usa el límite global como respaldo: ningún
    valor queda sin evaluar solo por pertenecer a un grupo chico."""
    positive = values > 0
    mask = pd.Series(False, index=values.index)
    if not positive.any():
        return mask
    global_limit = _cost_outlier_limit(values)
    if groups is None or groups[positive].notna().sum() < 2:
        if global_limit is not None:
            mask = positive & (values > global_limit)
        return mask
    for _group_name, group_values in values[positive].groupby(groups[positive], dropna=True):
        local_limit = _cost_outlier_limit(group_values)
        limit = local_limit if local_limit is not None else global_limit
        if limit is not None:
            mask.loc[group_values.index] = group_values > limit
    return mask


def _applicable_unit_cost(
    sales: pd.DataFrame,
    product_key: str | None,
    sales_dates: pd.Series,
    current_costs: pd.DataFrame | None,
    cost_key: str | None,
    unit_cost_col: str | None,
    cost_history: pd.DataFrame | None,
    cost_category_col: str | None = None,
) -> tuple[pd.Series, pd.Series, pd.Series, dict[str, Any]]:
    """Return one applicable cost per sale without multiplying rows.

    Historical costs use an as-of match (last effective date not after the
    sale). When history does not cover a row, a trustworthy current catalogue
    value is exposed as an estimate. Its provenance remains separate so it can
    improve the management view without turning a historical estimate into a
    certifiable accounting result.

    P1-6: el tercer valor devuelto es una máscara booleana (alineada con
    `sales`) marcando qué filas tomaron un costo del catálogo actual
    considerado atípico frente al resto del catálogo. Esos costos NUNCA se
    excluyen del cálculo -- se usan igual porque son datos reales -- pero
    quedan identificados para que el llamador pueda mostrar el efecto
    monetario y dejarlos en revisión.
    """

    empty_cost = pd.Series(float("nan"), index=sales.index, dtype=float)
    empty_source = pd.Series(None, index=sales.index, dtype=object)
    empty_atypical = pd.Series(False, index=sales.index, dtype=bool)
    if not product_key or product_key not in sales.columns:
        return empty_cost, empty_source, empty_atypical, {
            "metodo": "sin_clave_producto",
            "filas_historicas": 0,
            "filas_catalogo_actual": 0,
            "claves_historicas_conflictivas": 0,
        }

    history_key = (
        (
            find_column(cost_history.columns, "sku", "producto")
            or find_column(cost_history.columns, "id", "producto")
        )
        if cost_history is not None
        else None
    )
    history_date = (
        find_column(cost_history.columns, "vigencia")
        if cost_history is not None
        else None
    )
    history_cost = (
        find_column(cost_history.columns, "costo", "unitario")
        if cost_history is not None
        else None
    )
    cost = empty_cost.copy()
    source = empty_source.copy()
    historical_rows = 0
    usable_history = False
    conflicting_pairs: set[tuple[str, object]] = set()
    if cost_history is not None and history_key and history_date and history_cost:
        history = pd.DataFrame(
            {
                "_key": _keys(cost_history[history_key]),
                "_effective": _dates(cost_history, history_date),
                "_cost": numeric_series(cost_history, history_cost),
            }
        ).dropna(subset=["_key", "_effective", "_cost"])
        duplicate_key_date = history.duplicated(["_key", "_effective"], keep=False)
        conflicting_pairs = {
            (str(key), date)
            for (key, date), group in history.loc[duplicate_key_date].groupby(
                ["_key", "_effective"], sort=False
            )
            if group["_cost"].nunique(dropna=True) > 1
        }
        if conflicting_pairs:
            keep = pd.Series(
                [
                    (str(key), date) not in conflicting_pairs
                    for key, date in zip(history["_key"], history["_effective"], strict=False)
                ],
                index=history.index,
            )
            history = history.loc[keep]
        history = history.drop_duplicates(["_key", "_effective"], keep="last")
        history = history[history["_cost"] > 0]
        if not history.empty:
            usable_history = True
            left = pd.DataFrame(
                {
                    "_row": range(len(sales)),
                    "_key": _keys(sales[product_key]),
                    "_effective": sales_dates,
                },
                index=sales.index,
            ).dropna(subset=["_key", "_effective"])
            matched = pd.merge_asof(
                left.sort_values(["_effective", "_key"]),
                history.sort_values(["_effective", "_key"]),
                on="_effective",
                by="_key",
                direction="backward",
                allow_exact_matches=True,
            )
            valid = matched["_cost"].notna()
            positions = matched.loc[valid, "_row"].astype(int)
            cost.iloc[positions] = matched.loc[valid, "_cost"].astype(float).to_numpy()
            source.iloc[positions] = "historial_asof"
            historical_rows = int(valid.sum())

    safe_current, reference_quality = _unique_reference(
        current_costs, cost_key, [unit_cost_col] if unit_cost_col else []
    )
    if safe_current.empty or not unit_cost_col:
        return cost, source, empty_atypical, {
            "metodo": "historial_asof" if usable_history else "sin_costos_utilizables",
            "filas_historicas": historical_rows,
            "filas_catalogo_actual": 0,
            "filas_catalogo_actual_atipico": 0,
            "claves_historicas_conflictivas": len(conflicting_pairs),
            **reference_quality,
        }
    current_values = numeric_series(safe_current, unit_cost_col)
    positive = current_values.gt(0)
    # P1-6: un costo atípico (ej. un monitor caro entre accesorios baratos)
    # antes se EXCLUÍA del lookup -- la venta quedaba "sin costo" en vez de
    # usar su valor real, y nada lo informaba. Ahora SIEMPRE se usa (nunca
    # se descarta un dato real sin mostrarlo); solo se marca aparte para
    # que quien certifique el resultado sepa qué filas conviene revisar.
    category_groups = (
        current_costs.loc[safe_current.index, cost_category_col]
        if cost_category_col and current_costs is not None and cost_category_col in current_costs.columns
        else None
    )
    atypical_mask = _cost_outlier_mask(current_values, category_groups)
    atypical_keys = set(safe_current.loc[positive & atypical_mask, "_key"])
    lookup = dict(
        zip(
            safe_current.loc[positive, "_key"],
            current_values.loc[positive],
            strict=False,
        )
    )
    sale_keys = _keys(sales[product_key])
    current_cost = sale_keys.map(lookup).astype(float)
    atypical_sale = sale_keys.isin(atypical_keys)
    if usable_history:
        fallback = cost.isna() & current_cost.notna()
        cost.loc[fallback] = current_cost.loc[fallback]
        source.loc[fallback] = "catalogo_actual_estimado"
        method = "historial_asof_con_respaldo_actual"
        current_rows = int(fallback.sum())
        atypical_row_mask = fallback & atypical_sale
    else:
        cost = current_cost
        source.loc[cost.notna()] = "catalogo_actual"
        method = "catalogo_actual"
        current_rows = int(cost.notna().sum())
        atypical_row_mask = cost.notna() & atypical_sale
    return cost, source, atypical_row_mask, {
        "metodo": method,
        "filas_historicas": historical_rows,
        "filas_catalogo_actual": current_rows,
        "filas_catalogo_actual_atipico": int(atypical_row_mask.sum()),
        "claves_historicas_conflictivas": len(conflicting_pairs),
        **reference_quality,
    }


def _formula_controls(frames: dict[str, pd.DataFrame], kinds: dict[str, list[str]]) -> list[dict]:
    controls: list[dict] = []

    for name in kinds.get("ventas", []):
        frame = frames[name]
        amount_col = find_column(frame.columns, "monto", "venta")
        quantity_col = find_column(frame.columns, "cantidad")
        price_col = find_column(frame.columns, "precio", "unitario")
        discount_col = find_column(frame.columns, "descuento")
        tax_col = find_column(frame.columns, "iva")
        total_col = find_column(frame.columns, "total", "documento")
        amount = numeric_series(frame, amount_col)
        quantity = numeric_series(frame, quantity_col)
        price = numeric_series(frame, price_col)
        discount = numeric_series(frame, discount_col).fillna(0.0)
        expected_amount = quantity * price * (1 - discount)
        source_rows = list(frame.attrs.get("adsveris_source_rows", []))
        controls.append(
            {"hoja": name, **formula_mismatch(
                "monto_venta",
                amount,
                expected_amount,
                source_rows=source_rows,
                eligible=discount.between(0, 1),
                relative_tolerance=0.02,
                absolute_tolerance=50,
            ).to_dict()}
        )
        tax = numeric_series(frame, tax_col)
        comparable = amount.notna() & tax.notna() & (amount.abs() > 0)
        # P1-4: filas exentas (IVA=0 con monto>0) son un caso válido y
        # frecuente en Chile (productos exentos, servicios sin IVA, etc.),
        # no un error -- se excluyen de la inferencia de tasa para que un
        # catálogo mixto (afecto + exento) no arrastre la tasa dominante
        # hacia abajo.
        taxed = comparable & tax.ne(0)
        rate = float((tax[taxed] / amount[taxed]).abs().median()) if taxed.any() else 0.19
        if not 0.03 <= rate <= 0.35:
            rate = 0.19
        # Solo se evalúa la fórmula sobre filas afectas: una fila exenta no
        # se compara contra la tasa de las afectas, así que no se marca
        # como inconsistente por no llevar el 19% que no le corresponde.
        controls.append(
            {"hoja": name, **formula_mismatch(
                "iva_venta",
                tax,
                amount * rate,
                source_rows=source_rows,
                eligible=taxed,
                relative_tolerance=0.0,
            ).to_dict()}
        )
        controls.append(
            {"hoja": name, **formula_mismatch(
                "total_documento",
                numeric_series(frame, total_col),
                amount + tax,
                source_rows=source_rows,
                relative_tolerance=0.0,
            ).to_dict()}
        )

    for name in kinds.get("inventario", []):
        frame = frames[name]
        system = numeric_series(frame, find_column(frame.columns, "stock", "sistema"))
        physical = numeric_series(frame, find_column(frame.columns, "stock", "fisico"))
        committed = numeric_series(frame, find_column(frame.columns, "unidades", "comprometidas"))
        unit_cost = numeric_series(frame, find_column(frame.columns, "costo", "unitario"))
        source_rows = list(frame.attrs.get("adsveris_source_rows", []))
        checks = (
            ("stock_disponible", numeric_series(frame, find_column(frame.columns, "stock", "disponible")), system - committed, 0.0),
            ("valor_inventario", numeric_series(frame, find_column(frame.columns, "valor", "inventario")), system * unit_cost, 2.0),
            ("diferencia_conteo", numeric_series(frame, find_column(frame.columns, "diferencia", "conteo")), physical - system, 0.0),
        )
        controls.extend(
            {"hoja": name, **formula_mismatch(
                label,
                actual,
                expected,
                source_rows=source_rows,
                absolute_tolerance=absolute_tolerance,
                relative_tolerance=0.0,
            ).to_dict()}
            for label, actual, expected, absolute_tolerance in checks
        )

    for name in kinds.get("compras", []):
        frame = frames[name]
        quantity = numeric_series(frame, find_column(frame.columns, "cantidad", "comprada"))
        unit_cost = numeric_series(frame, find_column(frame.columns, "costo", "unitario"))
        discount = numeric_series(frame, find_column(frame.columns, "descuento")).fillna(0)
        freight = numeric_series(frame, find_column(frame.columns, "flete")).fillna(0)
        net = numeric_series(frame, find_column(frame.columns, "monto", "neto"))
        tax = numeric_series(frame, find_column(frame.columns, "iva"))
        total = numeric_series(frame, find_column(frame.columns, "total", "compra"))
        source_rows = list(frame.attrs.get("adsveris_source_rows", []))
        controls.append({"hoja": name, **formula_mismatch(
            "neto_compra", net, quantity * unit_cost * (1 - discount) + freight,
            source_rows=source_rows, eligible=discount.between(0, 1),
        ).to_dict()})
        controls.append({"hoja": name, **formula_mismatch(
            "total_compra", total, net + tax, source_rows=source_rows,
            relative_tolerance=0.0,
        ).to_dict()})

    for name in kinds.get("gastos", []):
        frame = frames[name]
        net = numeric_series(frame, find_column(frame.columns, "monto", "neto"))
        tax = numeric_series(frame, find_column(frame.columns, "iva"))
        total = numeric_series(frame, find_column(frame.columns, "total", "gasto"))
        controls.append({"hoja": name, **formula_mismatch(
            "total_gasto", total, net + tax,
            source_rows=list(frame.attrs.get("adsveris_source_rows", [])),
            relative_tolerance=0.0,
        ).to_dict()})
    return controls


def _ratio(
    key: str,
    label: str,
    value: float | None,
    status: str,
    formula: str,
    note: str,
    required: list[str],
) -> dict[str, Any]:
    return {
        "id": key,
        "nombre": label,
        "valor": round(value, 2) if value is not None else None,
        "estado": status,
        "formula": formula,
        "nota": note,
        "requiere": required,
    }


def analyze_business_workbook(
    frames: dict[str, pd.DataFrame],
    mappings: dict[str, dict[str, str]],
    results: dict[str, dict],
    *,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any] | None:
    """Build an executive and diagnostic view without mixing table grains."""

    kinds = classify_business_sheets(frames)
    sales_names = kinds.get("ventas", [])
    if not sales_names:
        return None
    sales = _append_sales(frames, sales_names)
    if sales.empty:
        return None

    mapping = {}
    for name in sales_names:
        for role, column in mappings.get(name, {}).items():
            if column in sales.columns and role not in mapping:
                mapping[role] = column
    date_col = mapping.get("fecha") or find_column(sales.columns, "fecha", "venta")
    amount_col = mapping.get("monto") or find_column(sales.columns, "monto", "venta")
    quantity_col = mapping.get("cantidad") or find_column(sales.columns, "cantidad")
    product_key = find_column(sales.columns, "sku", "producto") or find_column(sales.columns, "id", "producto")
    document_key = find_column(sales.columns, "id", "documento")
    status_col = find_column(sales.columns, "estado")
    sales_dates = _dates(sales, date_col)
    structural = structural_total_mask(sales, date_col)
    cancelled = _status_mask(sales, status_col, r"\b(?:anulad|cancelad|void)\w*")
    period_mask = _date_filter(sales_dates, date_from, date_to)
    indicator_mask = ~structural & ~cancelled & period_mask

    amount = numeric_series(sales, amount_col)
    quantity = numeric_series(sales, quantity_col)
    document_keys = _keys(sales[document_key]) if document_key else pd.Series(None, index=sales.index)
    duplicated_document = document_keys.notna() & document_keys.duplicated(keep=False)
    duplicate_groups = int(document_keys[duplicated_document].nunique())
    duplicate_extra_rows = int(duplicated_document.sum() - duplicate_groups)
    # Un ID repetido cae en exactamente una de tres categorías: conflicto real
    # de negocio (difiere en una columna que no es Observación), duplicado
    # idéntico (fila igual en todas las columnas) o solo difiere en una
    # columna Observación.* (no es conflicto, pero tampoco copia exacta).
    conflicting_document_keys: set[str] = set()
    identical_document_keys: set[str] = set()
    observation_only_document_keys: set[str] = set()
    if document_key and duplicate_groups:
        compare_columns = [
            column for column in sales.columns
            if column not in {document_key, "_hoja_origen"}
            and "observa" not in normalized_header(column)
        ]
        all_columns = [
            column for column in sales.columns
            if column not in {document_key, "_hoja_origen"}
        ]
        for key, group in sales.loc[duplicated_document].groupby(document_keys[duplicated_document]):
            key_str = str(key)
            if len(group[compare_columns].drop_duplicates()) > 1:
                conflicting_document_keys.add(key_str)
            elif len(group[all_columns].drop_duplicates()) > 1:
                observation_only_document_keys.add(key_str)
            else:
                identical_document_keys.add(key_str)
    conflict_groups = len(conflicting_document_keys)
    identical_groups = len(identical_document_keys)
    observation_only_groups = len(observation_only_document_keys)
    duplicate_extra = document_keys.notna() & document_keys.duplicated(keep="first")
    conflicting_document = document_keys.isin(conflicting_document_keys)
    # Exact copies contribute once. Reused IDs with conflicting payload stay
    # entirely outside certifiable figures until a person resolves them.
    certified_mask = indicator_mask & ~duplicate_extra & ~conflicting_document

    current_cost_name = (kinds.get("costos") or [None])[0]
    if not current_cost_name:
        # Una PyME pequeña suele tener un solo "Productos" con ID, categoria
        # Y costo unitario en la misma hoja, sin nombrarla "Costos_...". Se
        # acepta como fuente de costo si trae clave de producto + costo por
        # unidad reales, igual que ya reconoce join_related_frames en
        # multi_sheet.py para la misma combinacion de columnas.
        for name in kinds.get("productos", []):
            candidate = frames[name]
            candidate_headers = " | ".join(
                normalized_header(column) for column in candidate.columns
            )
            if "costo" in candidate_headers and "unitario" in candidate_headers:
                current_cost_name = name
                break
    current_costs = frames.get(current_cost_name) if current_cost_name else None
    cost_history_name = (kinds.get("historial_costos") or [None])[0]
    cost_history = frames.get(cost_history_name) if cost_history_name else None
    cost_key = (
        (
            find_column(current_costs.columns, "sku", "producto")
            or find_column(current_costs.columns, "id", "producto")
        )
        if current_costs is not None
        else None
    )
    unit_cost_col = (
        find_column(current_costs.columns, "costo", "unitario", excluded=("ultima",))
        if current_costs is not None
        else None
    )
    safe_costs, cost_reference_quality = _unique_reference(
        current_costs, cost_key, [unit_cost_col] if unit_cost_col else []
    )
    # P1-6: con columna de categoria, un costo atipico se compara contra su
    # propia categoria (electronica vs. aseo), no contra todo el catalogo.
    cost_category_col = (
        find_column(current_costs.columns, "categoria") if current_costs is not None else None
    )
    unit_cost, cost_source, atypical_cost_row, cost_method = _applicable_unit_cost(
        sales,
        product_key,
        sales_dates,
        current_costs,
        cost_key,
        unit_cost_col,
        cost_history,
        cost_category_col,
    )
    cost_of_sales = (quantity * unit_cost).where(quantity.notna() & unit_cost.notna())
    paired = indicator_mask & amount.notna() & cost_of_sales.notna()
    historical_cost = cost_source.eq("historial_asof")
    estimated_current_cost = cost_source.eq("catalogo_actual_estimado")
    current_catalogue_only = cost_method.get("metodo") == "catalogo_actual"
    certifiable_cost = historical_cost | (
        current_catalogue_only & cost_source.eq("catalogo_actual")
    )
    certified_paired = (
        certified_mask & amount.notna() & cost_of_sales.notna() & certifiable_cost
    )

    observed_sales = float(amount[indicator_mask].dropna().sum())
    certified_sales = float(amount[certified_mask].dropna().sum())
    paired_sales = float(amount[paired].sum())
    paired_cost = float(cost_of_sales[paired].sum())
    gross_profit = paired_sales - paired_cost if paired.any() else None
    gross_margin = gross_profit / paired_sales * 100 if gross_profit is not None and paired_sales else None
    # P1-6: costos atípicos NUNCA se excluyen del escenario oficial de
    # arriba (paired/gross_profit) -- son datos reales. Este es solo un
    # escenario ALTERNATIVO, informativo, para ver cuánto pesan si alguien
    # decide excluirlos tras revisarlos a mano.
    paired_without_atypical = paired & ~atypical_cost_row
    atypical_cost_amount = float(cost_of_sales[paired & atypical_cost_row].sum())
    sales_without_atypical = float(amount[paired_without_atypical].sum())
    cost_without_atypical = float(cost_of_sales[paired_without_atypical].sum())
    profit_without_atypical = (
        sales_without_atypical - cost_without_atypical
        if paired_without_atypical.any()
        else None
    )
    margin_without_atypical = (
        profit_without_atypical / sales_without_atypical * 100
        if profit_without_atypical is not None and sales_without_atypical
        else None
    )
    certified_paired_sales = float(amount[certified_paired].sum())
    certified_cost = float(cost_of_sales[certified_paired].sum())
    certified_profit = certified_paired_sales - certified_cost if certified_paired.any() else None
    certified_margin = (
        certified_profit / certified_paired_sales * 100
        if certified_profit is not None and certified_paired_sales
        else None
    )
    cost_coverage = round(int(paired.sum()) / max(int((indicator_mask & amount.notna()).sum()), 1) * 100, 1)
    historical_cost_coverage = round(
        int((indicator_mask & amount.notna() & cost_of_sales.notna() & historical_cost).sum())
        / max(int((indicator_mask & amount.notna()).sum()), 1)
        * 100,
        1,
    )
    certified_cost_coverage = round(
        int(certified_paired.sum())
        / max(int((certified_mask & amount.notna()).sum()), 1)
        * 100,
        1,
    )
    paired_months = set(sales_dates.loc[paired].dt.to_period("M").astype(str))

    expenses_total = None
    expenses_period_total = None
    expenses_rows = 0
    fixed_expenses = None
    variable_expenses = None
    expense_mask = pd.Series(dtype=bool)
    expense_values = pd.Series(dtype=float)
    expense_frame = frames.get((kinds.get("gastos") or [None])[0]) if kinds.get("gastos") else None
    if expense_frame is not None:
        expense_date_col = find_column(expense_frame.columns, "fecha", "gasto")
        expense_status = find_column(expense_frame.columns, "estado")
        expense_mask = ~_status_mask(expense_frame, expense_status, r"\b(?:anulad|cancelad)\w*")
        expense_dates = _dates(expense_frame, expense_date_col)
        expense_mask &= _date_filter(expense_dates, date_from, date_to)
        expense_values = numeric_series(
            expense_frame,
            find_column(expense_frame.columns, "total", "gasto")
            or find_column(expense_frame.columns, "monto", "neto"),
        )
        expenses_period_total = float(expense_values[expense_mask].dropna().sum())
        comparable_expense_mask = expense_mask & expense_dates.dt.to_period("M").astype(
            str
        ).isin(paired_months)
        expenses_total = float(expense_values[comparable_expense_mask].dropna().sum())
        expenses_rows = int((comparable_expense_mask & expense_values.notna()).sum())
        expense_type = find_column(expense_frame.columns, "tipo", "gasto")
        if expense_type:
            normalized_type = expense_frame[expense_type].astype(str).map(strip_accents_lower)
            fixed_mask = comparable_expense_mask & normalized_type.str.contains(r"\bfij", regex=True, na=False)
            variable_mask = comparable_expense_mask & normalized_type.str.contains(
                r"\bvariab", regex=True, na=False
            )
            fixed_expenses = float(expense_values[fixed_mask].dropna().sum())
            variable_expenses = float(expense_values[variable_mask].dropna().sum())
    operating_result = (
        gross_profit - expenses_total
        if gross_profit is not None and expenses_total is not None
        else None
    )
    operating_margin = (
        operating_result / paired_sales * 100
        if operating_result is not None and paired_sales
        else None
    )
    # Full operating expenses cannot be subtracted from a partial revenue/cost
    # subset: that would manufacture a loss whenever historical cost coverage
    # is incomplete. Keep the management estimate above, and expose a
    # certifiable operating result only when the cost base is effectively full.
    certified_operating_result = (
        certified_profit - expenses_total
        if certified_profit is not None
        and expenses_total is not None
        and certified_cost_coverage >= 99.5
        else None
    )
    certified_operating_margin = (
        certified_operating_result / certified_paired_sales * 100
        if certified_operating_result is not None and certified_paired_sales
        else None
    )

    inventory_frame = frames.get((kinds.get("inventario") or [None])[0]) if kinds.get("inventario") else None
    inventory_value = None
    if inventory_frame is not None:
        inventory_values = numeric_series(
            inventory_frame, find_column(inventory_frame.columns, "valor", "inventario")
        )
        inventory_value = float(inventory_values.dropna().sum()) if inventory_values.notna().any() else None

    purchase_frame = frames.get((kinds.get("compras") or [None])[0]) if kinds.get("compras") else None
    purchases_total = None
    if purchase_frame is not None:
        purchase_mask = ~_status_mask(
            purchase_frame,
            find_column(purchase_frame.columns, "estado"),
            r"\b(?:anulad|cancelad)\w*",
        )
        purchase_mask &= _date_filter(
            _dates(purchase_frame, find_column(purchase_frame.columns, "fecha", "compra")),
            date_from,
            date_to,
        )
        purchases = numeric_series(
            purchase_frame, find_column(purchase_frame.columns, "total", "compra")
        )
        purchases_total = float(purchases[purchase_mask].dropna().sum())

    collections_frame = frames.get((kinds.get("cobranzas") or [None])[0]) if kinds.get("cobranzas") else None
    collected_total = None
    overpaid_documents = 0
    collection_coverage = None
    collection_duplicates_excluded = 0
    if collections_frame is not None:
        # Exact duplicate payment rows are preserved in the source but cannot
        # be summed twice in a certifiable collection diagnostic.
        collection_rows = collections_frame.drop_duplicates().reset_index(drop=True)
        collection_duplicates_excluded = len(collections_frame) - len(collection_rows)
        collection_rows.attrs.update(collections_frame.attrs)
        payment_status = find_column(collection_rows.columns, "estado", "pago")
        payment_date = find_column(collection_rows.columns, "fecha", "pago")
        applied = _status_mask(collection_rows, payment_status, r"aplicad")
        applied &= _date_filter(
            _dates(collection_rows, payment_date), date_from, date_to
        )
        payment_amount = numeric_series(
            collection_rows, find_column(collection_rows.columns, "monto", "pago")
        )
        collected_total = float(payment_amount[applied].dropna().sum())
        payment_document = find_column(collection_rows.columns, "id", "documento")
        sales_total_col = find_column(sales.columns, "total", "documento")
        if payment_document and document_key and sales_total_col:
            payments = pd.DataFrame(
                {"key": _keys(collection_rows[payment_document]), "pago": payment_amount.where(applied)}
            ).dropna(subset=["key", "pago"]).groupby("key")["pago"].sum()
            unique_sales = sales.loc[certified_mask].copy()
            totals = numeric_series(unique_sales, sales_total_col)
            documents = pd.DataFrame(
                {"key": _keys(unique_sales[document_key]), "total": totals}
            ).dropna(subset=["key", "total"]).drop_duplicates("key")
            documents["pago"] = documents["key"].map(payments).fillna(0)
            # Notas de credito y otros documentos negativos no son cuentas por
            # cobrar. Compararlos con pagos positivos generaba cientos de falsos
            # "sobrepagados" y distorsionaba la cobertura de cobranza.
            receivables = documents.loc[documents["total"] > 0].copy()
            overpaid_documents = int(
                (receivables["pago"] > receivables["total"] * 1.005 + 2).sum()
            )
            document_total = float(receivables["total"].sum())
            collection_coverage = (
                min(float(receivables["pago"].sum()) / document_total * 100, 999.9)
                if document_total
                else None
            )

    month_frame = pd.DataFrame(
        {
            "mes": sales_dates.dt.to_period("M").astype(str),
            "ingresos": amount.where(indicator_mask),
            "costo": cost_of_sales.where(indicator_mask),
        }
    )
    month_frame.loc[sales_dates.isna(), "mes"] = None
    month_frame["ingresos_pareados"] = amount.where(paired)
    monthly = month_frame.dropna(subset=["mes"]).groupby("mes").sum(numeric_only=True)
    expense_monthly: dict[str, float] = {}
    if expense_frame is not None:
        expense_dates = _dates(expense_frame, find_column(expense_frame.columns, "fecha", "gasto"))
        exp = pd.DataFrame(
            {
                "mes": expense_dates.dt.to_period("M").astype(str),
                "valor": expense_values.where(expense_mask),
            }
        )
        exp.loc[expense_dates.isna(), "mes"] = None
        expense_monthly = exp.dropna(subset=["mes"]).groupby("mes")["valor"].sum().to_dict()
    monthly_rows: list[dict[str, Any]] = []
    for month, row in monthly.sort_index().iterrows():
        month_sales = float(row["ingresos"])
        month_cost = float(row["costo"])
        month_paired_sales = float(row["ingresos_pareados"])
        month_profit = month_paired_sales - month_cost if month_paired_sales or month_cost else None
        month_expense = float(expense_monthly.get(str(month), 0.0)) if expense_frame is not None else None
        monthly_rows.append(
            {
                "mes": str(month),
                "ventas": round(month_sales, 2),
                "costo": round(month_cost, 2),
                "utilidad_bruta": round(month_profit, 2) if month_profit is not None else None,
                "gastos_operacionales": round(month_expense, 2) if month_expense is not None else None,
                "resultado_operacional": round(month_profit - month_expense, 2)
                if month_profit is not None and month_expense is not None
                else None,
            }
        )

    products_frame = frames.get((kinds.get("productos") or [None])[0]) if kinds.get("productos") else None
    clients_frame = frames.get((kinds.get("clientes") or [None])[0]) if kinds.get("clientes") else None
    branches_frame = frames.get((kinds.get("sucursales") or [None])[0]) if kinds.get("sucursales") else None
    sellers_frame = frames.get((kinds.get("vendedores") or [None])[0]) if kinds.get("vendedores") else None
    suppliers_frame = frames.get((kinds.get("proveedores") or [None])[0]) if kinds.get("proveedores") else None

    product_ref_key = (
        (
            find_column(products_frame.columns, "sku", "producto")
            or find_column(products_frame.columns, "id", "producto")
        )
        if products_frame is not None
        else None
    )
    client_ref_key = find_column(clients_frame.columns, "id", "cliente") if clients_frame is not None else None
    branch_ref_key = find_column(branches_frame.columns, "id", "sucursal") if branches_frame is not None else None
    seller_ref_key = find_column(sellers_frame.columns, "id", "vendedor") if sellers_frame is not None else None

    product_col = mapping.get("producto") or find_column(
        sales.columns, "producto", excluded=("sku", "id")
    )
    channel_col = mapping.get("canal") or find_column(sales.columns, "canal")
    branch_col = mapping.get("sucursal") or find_column(sales.columns, "id", "sucursal")
    client_col = mapping.get("cliente") or find_column(sales.columns, "id", "cliente")
    seller_col = mapping.get("vendedor") or find_column(sales.columns, "id", "vendedor")

    product_name_ref = (
        find_column(products_frame.columns, "nombre", "producto")
        or find_column(products_frame.columns, "descripcion", "producto")
        if products_frame is not None
        else None
    )
    category_ref = find_column(products_frame.columns, "categoria") if products_frame is not None else None
    client_name_ref = (
        find_column(clients_frame.columns, "razon", "social")
        or find_column(clients_frame.columns, "nombre", "cliente")
        if clients_frame is not None
        else None
    )
    client_segment_ref = (
        find_column(clients_frame.columns, "segmento")
        or find_column(clients_frame.columns, "tipo", "cliente")
        if clients_frame is not None
        else None
    )
    branch_name_ref = (
        find_column(branches_frame.columns, "nombre", "sucursal")
        or find_column(branches_frame.columns, "sucursal", excluded=("id",))
        if branches_frame is not None
        else None
    )
    seller_name_ref = (
        find_column(sellers_frame.columns, "nombre", "vendedor")
        or find_column(sellers_frame.columns, "vendedor", excluded=("id",))
        if sellers_frame is not None
        else None
    )

    if product_key:
        sales["_producto_analisis"] = _reference_values(
            sales, product_key, products_frame, product_ref_key, product_name_ref
        ).fillna(sales[product_key])
        sales["_categoria_analisis"] = _reference_values(
            sales, product_key, products_frame, product_ref_key, category_ref
        )
    if client_col:
        sales["_cliente_analisis"] = _reference_values(
            sales, client_col, clients_frame, client_ref_key, client_name_ref
        ).fillna(sales[client_col])
        sales["_segmento_cliente"] = _reference_values(
            sales, client_col, clients_frame, client_ref_key, client_segment_ref
        )
    if branch_col:
        sales["_sucursal_analisis"] = _reference_values(
            sales, branch_col, branches_frame, branch_ref_key, branch_name_ref
        ).fillna(sales[branch_col])
    if seller_col:
        sales["_vendedor_analisis"] = _reference_values(
            sales, seller_col, sellers_frame, seller_ref_key, seller_name_ref
        ).fillna(sales[seller_col])

    product_group_col = "_producto_analisis" if "_producto_analisis" in sales else product_col or product_key
    category_group_col = "_categoria_analisis" if "_categoria_analisis" in sales else mapping.get("categoria") or find_column(sales.columns, "categoria")
    branch_group_col = "_sucursal_analisis" if "_sucursal_analisis" in sales else branch_col
    client_group_col = "_cliente_analisis" if "_cliente_analisis" in sales else client_col
    seller_group_col = "_vendedor_analisis" if "_vendedor_analisis" in sales else seller_col
    analytic_sales = sales.loc[indicator_mask].reset_index(drop=True)
    analytic_amount = amount.loc[indicator_mask].reset_index(drop=True)
    analytic_cost = cost_of_sales.loc[indicator_mask].reset_index(drop=True)
    groupings = {
        "productos": _group_profit(analytic_sales, product_group_col, analytic_amount, analytic_cost, 60),
        "categorias": _group_profit(analytic_sales, category_group_col, analytic_amount, analytic_cost),
        "canales": _group_profit(analytic_sales, channel_col, analytic_amount, analytic_cost),
        "sucursales": _group_profit(analytic_sales, branch_group_col, analytic_amount, analytic_cost),
        "clientes": _group_profit(analytic_sales, client_group_col, analytic_amount, analytic_cost),
        "segmentos_clientes": _group_profit(
            analytic_sales,
            "_segmento_cliente" if "_segmento_cliente" in analytic_sales else None,
            analytic_amount,
            analytic_cost,
        ),
        "vendedores": _group_profit(analytic_sales, seller_group_col, analytic_amount, analytic_cost),
    }
    eligible_products = [
        row for row in groupings["productos"]
        if row["margen_pct"] is not None and row["participacion_pct"] is not None
    ]
    portfolio: list[dict[str, Any]] = []
    thresholds = None
    if len(eligible_products) >= 4:
        margin_median = float(pd.Series([row["margen_pct"] for row in eligible_products]).median())
        share_median = float(pd.Series([row["participacion_pct"] for row in eligible_products]).median())
        thresholds = {
            "margen_mediano_pct": round(margin_median, 2),
            "participacion_mediana_pct": round(share_median, 2),
        }
        for row in eligible_products:
            high_volume = row["participacion_pct"] >= share_median
            high_margin = row["margen_pct"] >= margin_median
            quadrant = (
                "estrella" if high_volume and high_margin
                else "vaca_lechera" if high_volume
                else "oportunidad" if high_margin
                else "problema"
            )
            portfolio.append({**row, "cuadrante": quadrant})

    # Columna de NOMBRE de producto (no la clave): "Producto" descriptivo, nunca
    # la columna de SKU/ID/código.
    def _name_column(frame: pd.DataFrame | None, key_column: str | None) -> str | None:
        if frame is None:
            return None
        for column in frame.columns:
            header = normalized_header(column)
            if (
                "producto" in header
                and column != key_column
                and not any(term in header for term in ("sku", "id", "cod"))
            ):
                return str(column)
        return None

    sales_product_name = _name_column(sales, product_key)
    products_product_name = _name_column(products_frame, product_ref_key)

    integrity = [
        _relation_quality(sales.loc[~structural], product_key, products_frame, product_ref_key, "Ventas → Productos"),
        _attribute_consistency(
            sales.loc[~structural], product_key, sales_product_name,
            products_frame, product_ref_key, products_product_name,
            "Ventas → Productos (nombre)",
        ),
        _relation_quality(sales.loc[~structural], product_key, current_costs, cost_key, "Ventas → Costos"),
        _relation_quality(sales.loc[~structural], client_col, clients_frame, client_ref_key, "Ventas → Clientes"),
        _relation_quality(sales.loc[~structural], branch_col, branches_frame, branch_ref_key, "Ventas → Sucursales"),
        _relation_quality(sales.loc[~structural], seller_col, sellers_frame, seller_ref_key, "Ventas → Vendedores"),
        _relation_quality(products_frame, find_column(products_frame.columns, "id", "proveedor") if products_frame is not None else None, suppliers_frame, find_column(suppliers_frame.columns, "id", "proveedor") if suppliers_frame is not None else None, "Productos → Proveedores"),
        _relation_quality(
            purchase_frame,
            (
                find_column(purchase_frame.columns, "sku", "producto")
                or find_column(purchase_frame.columns, "id", "producto")
            ) if purchase_frame is not None else None,
            products_frame, product_ref_key, "Compras → Productos",
        ),
        _relation_quality(purchase_frame, find_column(purchase_frame.columns, "id", "proveedor") if purchase_frame is not None else None, suppliers_frame, find_column(suppliers_frame.columns, "id", "proveedor") if suppliers_frame is not None else None, "Compras → Proveedores"),
        _relation_quality(collections_frame, find_column(collections_frame.columns, "id", "documento") if collections_frame is not None else None, sales.loc[~structural], document_key, "Cobranzas → Ventas"),
        _relation_quality(sellers_frame, find_column(sellers_frame.columns, "id", "sucursal") if sellers_frame is not None else None, branches_frame, find_column(branches_frame.columns, "id", "sucursal") if branches_frame is not None else None, "Vendedores → Sucursales"),
    ]
    integrity = [item for item in integrity if item is not None]

    formula_controls = _formula_controls(frames, kinds)
    formula_issues = sum(item["filas_inconsistentes"] for item in formula_controls)
    orphan_rows = sum(item["huerfanas"] + item["sin_clave"] for item in integrity)

    cost_values = numeric_series(current_costs, unit_cost_col) if current_costs is not None else pd.Series(dtype=float)
    # P1-6: análisis contextual -- un límite ÚNICO para todo el catálogo
    # compara un costo de electrónica contra uno de un insumo de aseo. Con
    # columna de categoría disponible (ya detectada arriba, la misma que usa
    # `_applicable_unit_cost` para marcar `atypical_cost_row`), el límite se
    # calcula POR CATEGORÍA; sin ella, se degrada al límite global.
    cost_categories = current_costs[cost_category_col] if cost_category_col and current_costs is not None else None
    extreme_mask = _cost_outlier_mask(cost_values, cost_categories)
    upper = _cost_outlier_limit(cost_values)
    cost_quality = {
        **cost_reference_quality,
        **cost_method,
        "faltantes": int(cost_values.isna().sum()),
        "negativos": int((cost_values < 0).sum()),
        "ceros": int((cost_values == 0).sum()),
        "extremos": int(extreme_mask.sum()),
        "limite_extremo": round(upper, 2) if upper is not None else None,
        "analisis_por_categoria": cost_category_col is not None,
        "ventas_con_costo_pct": cost_coverage,
        "ventas_certificables_con_costo_pct": certified_cost_coverage,
        "filas_costo_historico": int((cost_source == "historial_asof").sum()),
        "filas_costo_actual": int((cost_source == "catalogo_actual").sum()),
        "filas_costo_actual_estimado": int(
            (cost_source == "catalogo_actual_estimado").sum()
        ),
        # P1-6: escenario ALTERNATIVO informativo -- el escenario oficial de
        # arriba (utilidad_bruta, margen_bruto_pct) NUNCA excluye costos
        # atípicos por sí solo, son datos reales. Esto muestra cuánto
        # pesarían si alguien decide excluirlos tras revisarlos a mano.
        "escenario_sin_atipicos": {
            "monto_costo_atipico_incluido": round(atypical_cost_amount, 2),
            "ventas_pareadas": round(sales_without_atypical, 2),
            "costo_pareado": round(cost_without_atypical, 2),
            "utilidad_bruta": round(profit_without_atypical, 2)
            if profit_without_atypical is not None
            else None,
            "margen_bruto_pct": round(margin_without_atypical, 2)
            if margin_without_atypical is not None
            else None,
            "estado_revision": "requiere_revision" if atypical_cost_row.any() else "sin_atipicos",
        },
    }

    goals_frame = frames.get((kinds.get("metas") or [None])[0]) if kinds.get("metas") else None
    goals = {
        "disponible": False,
        "meta_venta": None,
        "venta_comparable": None,
        "cumplimiento_pct": None,
        "meta_margen_pct": None,
        "meta_nuevos_clientes": None,
        "por_mes": [],
        "nota": "No hay una hoja de metas comparable.",
    }
    if goals_frame is not None:
        goal_date_col = find_column(goals_frame.columns, "mes") or find_column(
            goals_frame.columns, "fecha"
        )
        goal_amount_col = find_column(goals_frame.columns, "meta", "venta")
        goal_margin_col = find_column(goals_frame.columns, "meta", "margen")
        goal_clients_col = find_column(goals_frame.columns, "meta", "nuevo", "cliente")
        goal_dates = _dates(goals_frame, goal_date_col)
        goal_period = _date_filter(goal_dates, date_from, date_to)
        goal_amount = numeric_series(goals_frame, goal_amount_col)
        goal_margin = numeric_series(goals_frame, goal_margin_col)
        goal_clients = numeric_series(goals_frame, goal_clients_col)
        comparable_goals = goal_period & goal_dates.notna() & goal_amount.notna()
        if comparable_goals.any():
            goal_month = goal_dates.dt.to_period("M").astype(str)
            target_by_month = (
                pd.DataFrame(
                    {"mes": goal_month.where(comparable_goals), "meta": goal_amount}
                )
                .dropna(subset=["mes", "meta"])
                .groupby("mes")["meta"]
                .sum()
            )
            actual_by_month = (
                pd.DataFrame(
                    {
                        "mes": sales_dates.dt.to_period("M").astype(str),
                        "venta": amount.where(indicator_mask),
                    }
                )
                .loc[lambda value: value["mes"].isin(target_by_month.index)]
                .groupby("mes")["venta"]
                .sum()
            )
            monthly_goals = []
            for month, target in target_by_month.sort_index().items():
                actual = float(actual_by_month.get(month, 0.0))
                monthly_goals.append(
                    {
                        "mes": str(month),
                        "meta_venta": round(float(target), 2),
                        "venta": round(actual, 2),
                        "cumplimiento_pct": round(actual / float(target) * 100, 2)
                        if target
                        else None,
                    }
                )
            total_target = float(target_by_month.sum())
            total_actual = float(actual_by_month.sum())
            goals = {
                "disponible": True,
                "meta_venta": round(total_target, 2),
                "venta_comparable": round(total_actual, 2),
                "cumplimiento_pct": round(total_actual / total_target * 100, 2)
                if total_target
                else None,
                "meta_margen_pct": round(float(goal_margin[goal_period].mean()) * 100, 2)
                if goal_margin[goal_period].notna().any()
                else None,
                "meta_nuevos_clientes": round(float(goal_clients[goal_period].sum()), 2)
                if goal_clients[goal_period].notna().any()
                else None,
                "por_mes": monthly_goals,
                "nota": "Las ventas se comparan solo en los meses que tienen una meta informada.",
            }
            goal_index = {row["mes"]: row for row in monthly_goals}
            for row in monthly_rows:
                match = goal_index.get(row["mes"])
                if match:
                    row["meta_venta"] = match["meta_venta"]
                    row["cumplimiento_meta_pct"] = match["cumplimiento_pct"]

    contribution = (
        gross_profit - variable_expenses
        if gross_profit is not None and variable_expenses is not None
        else gross_profit
    )
    contribution_margin = (
        contribution / paired_sales if contribution is not None and paired_sales else None
    )
    monthly_fixed_expenses = (
        fixed_expenses / len(paired_months)
        if fixed_expenses is not None and paired_months
        else None
    )
    break_even_sales = (
        monthly_fixed_expenses / contribution_margin
        if monthly_fixed_expenses is not None
        and contribution_margin
        and contribution_margin > 0
        else None
    )
    inventory_turnover = (
        paired_cost / inventory_value
        if inventory_value is not None and inventory_value > 0 and paired.any()
        else None
    )
    target_compliance = goals.get("cumplimiento_pct") if goals["disponible"] else None

    sensitivity = {
        "base_utilidad_bruta": round(gross_profit, 2) if gross_profit is not None else None,
        "costo_mas_5": round(gross_profit - paired_cost * 0.05, 2)
        if gross_profit is not None
        else None,
        "costo_mas_10": round(gross_profit - paired_cost * 0.10, 2)
        if gross_profit is not None
        else None,
        "nota": (
            "Escenario mecánico sobre ventas y volumen constantes; no es un pronóstico."
            if gross_profit is not None
            else "No hay cobertura suficiente para simular costos."
        ),
    }

    ratios = [
        _ratio(
            "margen_bruto", "Margen bruto certificable", certified_margin,
            "available"
            if certified_margin is not None and certified_cost_coverage >= 99.5 and not duplicate_groups
            else "partial" if certified_margin is not None else "unavailable",
            "Utilidad certificable / ventas certificables pareadas",
            (
                f"Cobertura de costos en documentos no repetidos: "
                f"{certified_cost_coverage}%."
            ),
            ["ventas", "cantidad", "costo unitario"],
        ),
        _ratio(
            "margen_operacional", "Margen operacional certificable", certified_operating_margin,
            "available"
            if certified_operating_margin is not None and certified_cost_coverage >= 99.5 and not duplicate_groups
            else "partial" if certified_operating_margin is not None else "unavailable",
            "(Utilidad certificable - gastos operacionales) / ventas certificables pareadas",
            "Es parcial cuando faltan costos o quedan documentos repetidos.",
            ["ventas", "costos", "gastos operacionales"],
        ),
        _ratio(
            "tasa_cobranza", "Cobranza sobre documentos", collection_coverage,
            "partial" if collection_coverage is not None else "unavailable",
            "Pagos aplicados / total documentado",
            "Es una aproximación operativa; no reemplaza un auxiliar contable de cuentas por cobrar.",
            ["ventas con total documento", "cobranzas aplicadas"],
        ),
        _ratio(
            "punto_equilibrio_ventas",
            "Punto de equilibrio mensual",
            break_even_sales,
            "partial" if break_even_sales is not None else "unavailable",
            "Gasto fijo mensual promedio / margen de contribución",
            "Aproximación sobre los meses con costo pareado y la clasificación fijo/variable de gastos.",
            ["ventas", "costos", "gastos fijos y variables"],
        ),
        _ratio(
            "rotacion_inventario",
            "Rotación de inventario aproximada",
            inventory_turnover,
            "partial" if inventory_turnover is not None else "unavailable",
            "Costo de venta pareado / inventario al corte",
            "Usa un solo corte de inventario; no equivale al inventario promedio contable.",
            ["costo de venta", "inventario valorizado"],
        ),
        _ratio(
            "cumplimiento_meta_ventas",
            "Cumplimiento de meta de ventas",
            target_compliance,
            "available" if target_compliance is not None else "unavailable",
            "Venta neta comparable / meta de venta",
            goals["nota"],
            ["ventas", "metas mensuales"],
        ),
        _ratio("liquidez_corriente", "Razón corriente", None, "unavailable", "Activo corriente / pasivo corriente", "No hay balance con activos y pasivos corrientes.", ["activo corriente", "pasivo corriente"]),
        _ratio("prueba_acida", "Prueba ácida", None, "unavailable", "(Activo corriente - inventario) / pasivo corriente", "No hay balance de situación.", ["activo corriente", "inventario", "pasivo corriente"]),
        _ratio("roe", "ROE", None, "unavailable", "Utilidad neta / patrimonio", "No hay utilidad neta ni patrimonio contable.", ["utilidad neta", "patrimonio"]),
        _ratio("roa", "ROA", None, "unavailable", "Utilidad neta / activos", "No hay utilidad neta ni activos totales.", ["utilidad neta", "activos totales"]),
        _ratio("ebitda", "EBITDA", None, "unavailable", "Resultado operacional + depreciación + amortización", "Falta clasificación contable de depreciación y amortización.", ["resultado operacional", "depreciación", "amortización"]),
    ]

    decisions: list[dict[str, Any]] = []
    if duplicate_extra_rows:
        decisions.append({
            "severidad": "alta",
            "titulo": f"Resolver {duplicate_groups} documentos repetidos antes de certificar ventas",
            "evidencia": f"Hay {duplicate_extra_rows} filas adicionales y {conflict_groups} grupos con contenido distinto.",
            "accion": "Revisa los conflictos en Limpieza; los indicadores certificados los excluyen hasta que decidas.",
            "confianza": 1.0,
        })
    if cost_coverage < 99.5:
        decisions.append({
            "severidad": "alta",
            "titulo": "Completar la cobertura de costos",
            "evidencia": f"Solo {cost_coverage}% de las ventas con monto tiene costo relacionado.",
            "accion": "Corrige SKU huérfanos o costos faltantes antes de usar margen y utilidad como resultado final.",
            "confianza": 1.0,
        })
    estimated_cost_rows = int((indicator_mask & estimated_current_cost).sum())
    if estimated_cost_rows:
        decisions.append({
            "severidad": "media",
            "titulo": "Confirmar costos historicos estimados con el catalogo actual",
            "evidencia": (
                f"{estimated_cost_rows} ventas sin vigencia historica usan el costo actual; "
                f"la cobertura historica directa es {historical_cost_coverage}%."
            ),
            "accion": (
                "Completa fechas de vigencia anteriores si necesitas certificar el margen historico; "
                "la estimacion ya queda identificada y separada."
            ),
            "confianza": 1.0,
        })
    if cost_quality["negativos"] or cost_quality["ceros"] or cost_quality["extremos"]:
        atypical_amount_note = (
            f" El costo atípico incluido en el resultado suma {round(atypical_cost_amount, 2)}."
            if atypical_cost_amount
            else ""
        )
        decisions.append({
            "severidad": "alta",
            "titulo": "Validar costos que distorsionan el margen",
            "evidencia": (
                f"{cost_quality['negativos']} negativos, {cost_quality['ceros']} en cero y "
                f"{cost_quality['extremos']} extremos"
                + (" (comparados por categoría)." if cost_quality["analisis_por_categoria"] else ".")
                + atypical_amount_note
            ),
            "accion": "Confirma el costo vigente por SKU; no se reemplazó ningún valor automáticamente.",
            "confianza": 0.98,
        })
    if formula_issues:
        decisions.append({
            "severidad": "media",
            "titulo": "Reconciliar cálculos internos",
            "evidencia": f"{formula_issues} filas no cuadran con las fórmulas declaradas en ventas, inventario, compras o gastos.",
            "accion": "Abre Observaciones en la descarga y revisa los casos antes de cerrar el periodo.",
            "confianza": 0.98,
        })
    if orphan_rows:
        decisions.append({
            "severidad": "media",
            "titulo": "Corregir claves sin correspondencia",
            "evidencia": f"{orphan_rows} referencias faltantes o huérfanas impiden enriquecer datos de forma segura.",
            "accion": "Completa SKU, clientes, sucursales, vendedores, proveedores o documentos en sus tablas maestras.",
            "confianza": 1.0,
        })
    if overpaid_documents:
        decisions.append({
            "severidad": "media",
            "titulo": f"Revisar {overpaid_documents} documentos posiblemente sobrepagados",
            "evidencia": "Los pagos aplicados acumulados superan el total del documento.",
            "accion": "Valida anticipos, notas de crédito, reversas o pagos asignados al documento equivocado.",
            "confianza": 0.95,
        })
    negative_margin = sorted(
        [row for row in groupings["productos"] if (row.get("margen_pct") or 0) < 0],
        key=lambda row: row.get("utilidad") or 0,
    )
    if negative_margin:
        decisions.append({
            "severidad": "alta",
            "titulo": f"Revisar {len(negative_margin)} productos con margen negativo",
            "evidencia": f"El mayor impacto corresponde a {negative_margin[0]['nombre']}.",
            "accion": "Valida costo y descuento; si son correctos, ajusta precio o descontinúa la combinación no rentable.",
            "confianza": 0.9,
        })
    if target_compliance is not None and target_compliance < 100:
        gap = float(goals["meta_venta"] or 0) - float(goals["venta_comparable"] or 0)
        decisions.append({
            "severidad": "media" if target_compliance >= 90 else "alta",
            "titulo": "Cerrar la brecha de la meta de ventas",
            "evidencia": f"Cumplimiento {target_compliance:.1f}% y brecha de {max(gap, 0):.0f} en los meses comparables.",
            "accion": "Prioriza los meses y sucursales con menor cumplimiento antes de aumentar descuentos generales.",
            "confianza": 0.98,
        })
    top_clients = groupings.get("clientes", [])
    if top_clients and (top_clients[0].get("participacion_pct") or 0) >= 20:
        decisions.append({
            "severidad": "media",
            "titulo": "Reducir dependencia del principal cliente",
            "evidencia": f"{top_clients[0]['nombre']} concentra {top_clients[0]['participacion_pct']:.1f}% de las ventas positivas.",
            "accion": "Protege esa cuenta y desarrolla clientes alternativos para reducir el riesgo comercial.",
            "confianza": 0.95,
        })
    problem_products = [row for row in portfolio if row.get("cuadrante") == "problema"]
    if problem_products:
        decisions.append({
            "severidad": "media",
            "titulo": f"Revisar {len(problem_products)} productos de bajo volumen y margen",
            "evidencia": "Quedaron en el cuadrante problema frente a las medianas del portafolio.",
            "accion": "Evalúa precio, costo, promoción o descontinuación; la matriz es relativa al archivo analizado.",
            "confianza": 0.85,
        })

    quality_penalty = min(45.0, duplicate_groups * 0.15 + formula_issues * 0.015 + orphan_rows * 0.01)
    confidence = max(0.0, min(100.0, certified_cost_coverage - quality_penalty))
    certification = (
        "blocked"
        if duplicate_groups or conflict_groups or certified_cost_coverage < 95 or cost_quality["negativos"]
        else "partial"
        if formula_issues or orphan_rows or certified_cost_coverage < 99.5
        else "certified"
    )
    used_sheets = {
        *sales_names,
        *[
            name
            for name in (
                current_cost_name,
                cost_history_name,
                (kinds.get("gastos") or [None])[0],
                (kinds.get("inventario") or [None])[0],
                (kinds.get("compras") or [None])[0],
                (kinds.get("cobranzas") or [None])[0],
                (kinds.get("productos") or [None])[0],
                (kinds.get("clientes") or [None])[0],
                (kinds.get("sucursales") or [None])[0],
                (kinds.get("vendedores") or [None])[0],
                (kinds.get("proveedores") or [None])[0],
                (kinds.get("metas") or [None])[0],
            )
            if name
        ],
    }

    return {
        "version": 1,
        "estado_certificacion": certification,
        "confianza_pct": round(confidence, 1),
        "alcance": {
            "hojas_ventas": sales_names,
            "hoja_costos": current_cost_name,
            "hoja_historial_costos": cost_history_name,
            "hojas_utilizadas": sorted(used_sheets),
            "filas_ventas_fisicas": int(len(sales)),
            "filas_totales_estructurales": int(structural.sum()),
            "filas_anuladas": int(cancelled.sum()),
            "filas_indicadores": int(indicator_mask.sum()),
            "documentos_repetidos": duplicate_groups,
            "filas_adicionales_documento": duplicate_extra_rows,
            "documentos_conflictivos": conflict_groups,
            "documentos_identicos": identical_groups,
            "documentos_solo_observacion_distinta": observation_only_groups,
        },
        "estado_resultados": {
            "ventas_observadas": round(observed_sales, 2),
            "ventas_certificables": round(certified_sales, 2),
            "ventas_pareadas": round(paired_sales, 2),
            "costo_venta_conocido": round(paired_cost, 2),
            "costo_venta_estimado_catalogo": round(
                float(cost_of_sales[indicator_mask & estimated_current_cost].sum()), 2
            ),
            "utilidad_bruta": round(gross_profit, 2) if gross_profit is not None else None,
            "margen_bruto_pct": round(gross_margin, 2) if gross_margin is not None else None,
            "gastos_operacionales": round(expenses_total, 2) if expenses_total is not None else None,
            "gastos_operacionales_periodo": round(expenses_period_total, 2)
            if expenses_period_total is not None
            else None,
            "filas_gastos": expenses_rows,
            "resultado_operacional": round(operating_result, 2) if operating_result is not None else None,
            "margen_operacional_pct": round(operating_margin, 2) if operating_margin is not None else None,
            "cobertura_costos_pct": cost_coverage,
            "cobertura_costos_historica_pct": historical_cost_coverage,
            "cobertura_costos_certificable_pct": certified_cost_coverage,
            "ventas_certificables_pareadas": round(certified_paired_sales, 2),
            "costo_certificable": round(certified_cost, 2),
            "utilidad_certificable": round(certified_profit, 2) if certified_profit is not None else None,
            "margen_certificable_pct": round(certified_margin, 2) if certified_margin is not None else None,
            "resultado_operacional_certificable": round(certified_operating_result, 2)
            if certified_operating_result is not None
            else None,
            "margen_operacional_certificable_pct": round(certified_operating_margin, 2)
            if certified_operating_margin is not None
            else None,
        },
        "operacion": {
            "cobrado_aplicado": round(collected_total, 2) if collected_total is not None else None,
            "cobranza_sobre_documentos_pct": round(collection_coverage, 2) if collection_coverage is not None else None,
            "documentos_sobrepagados": overpaid_documents,
            "pagos_duplicados_excluidos": collection_duplicates_excluded,
            "valor_inventario": round(inventory_value, 2) if inventory_value is not None else None,
            "compras_efectivas": round(purchases_total, 2) if purchases_total is not None else None,
            "gastos_fijos": round(fixed_expenses, 2) if fixed_expenses is not None else None,
            "gastos_variables": round(variable_expenses, 2) if variable_expenses is not None else None,
            "gasto_fijo_mensual_promedio": round(monthly_fixed_expenses, 2)
            if monthly_fixed_expenses is not None
            else None,
            "punto_equilibrio_ventas": round(break_even_sales, 2) if break_even_sales is not None else None,
            "rotacion_inventario_aprox": round(inventory_turnover, 2) if inventory_turnover is not None else None,
        },
        "evolucion": monthly_rows,
        "agrupaciones": groupings,
        "portafolio": {"umbrales": thresholds, "productos": portfolio},
        "metas": goals,
        "sensibilidad": sensitivity,
        "calidad": {
            "costos": cost_quality,
            "integridad_referencial": integrity,
            "controles_formula": formula_controls,
            "filas_inconsistentes_formula": formula_issues,
            "referencias_problematicas": orphan_rows,
        },
        "ratios": ratios,
        "decisiones": decisions,
    }
