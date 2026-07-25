"""Dashboard determinista por relación entre hojas (Partes 7-10).

Toma una relación validada (misma que usa el modo ``join``), la ejecuta con
``join_related_frames`` —que ya garantiza que la unión no multiplica filas ni
altera totales transaccionales— y calcula KPIs, gráficos, tabla, hallazgos,
alertas y acciones con reglas deterministas. No usa IA. No inventa cifras: si
falta un insumo, el KPI queda "No disponible" y el bloque se oculta.

Reglas clave (Parte 8):
- La hoja transaccional (izquierda) es la fuente de hechos.
- El stock, el costo vigente y la cantidad disponible se calculan desde la
  granularidad original de la hoja correspondiente, NUNCA sumando valores
  repetidos por el join.
- Los valores faltantes no son cero. El margen usa solo ventas pareadas con
  costo. Se informa siempre la cobertura de costos.
- Recencias y periodos se basan en las fechas del Excel (fecha máxima del
  dataset como referencia), no en la fecha del servidor.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .business import _dates, _status_mask, _text_key
from .mapping import resolve_mapping
from .metrics import CurrencyDetection
from .multi_sheet import join_related_frames, relation_stats
from .quality import find_column, numeric_series, structural_total_mask
from .relationships import classify_relationship_template, collapse_inventory_snapshots

# Umbrales de riesgo de inventario, centralizados (Parte 8).
COVERAGE_CRITICAL_DAYS = 7
COVERAGE_HIGH_DAYS = 15
COVERAGE_MEDIUM_DAYS = 30
OVERSTOCK_DAYS = 90
OVERSTOCK_NO_SALES_DAYS = 60

TOP_LIMIT = 10
TABLE_LIMIT = 50
LOW_MARGIN_THRESHOLD = 0.15


def _clean_number(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    return round(float(value), 2)


def _kpi(
    kpi_id: str,
    label: str,
    value: float | str | None,
    fmt: str,
    *,
    help_text: str | None = None,
    tone: str = "default",
) -> dict[str, Any]:
    available = value is not None and not (
        isinstance(value, float) and pd.isna(value)
    )
    return {
        "id": kpi_id,
        "label": label,
        "value": value if available else None,
        "format": fmt,
        "help": help_text,
        "available": bool(available),
        "tone": tone,
    }


def _coverage_state(days: float | None) -> str:
    if days is None:
        return "sin_datos"
    if days < COVERAGE_CRITICAL_DAYS:
        return "critico"
    if days < COVERAGE_HIGH_DAYS:
        return "alto"
    if days < COVERAGE_MEDIUM_DAYS:
        return "medio"
    return "sano"


def _currency_label(results: dict[str, dict], sheet: str) -> str:
    currency = results.get(sheet, {}).get("_moneda")
    if isinstance(currency, CurrencyDetection):
        return currency.dominante
    return "CLP"


def _period_reference(dates: pd.Series) -> pd.Timestamp | None:
    valid = dates.dropna()
    if valid.empty:
        return None
    return valid.max()


def _iso_or_none(value: pd.Timestamp | None) -> str | None:
    if value is None or pd.isna(value):
        return None
    return value.date().isoformat()


def _empty_dashboard(
    relation: dict[str, Any],
    template: str,
    currency: str,
    message: str,
) -> dict[str, Any]:
    return {
        "relation": relation,
        "template": template,
        "period": {"desde": None, "hasta": None, "referencia": None, "meses": []},
        "currency": currency,
        "quality": {
            "rows_before": 0,
            "rows_after": 0,
            "matched_rows": 0,
            "unmatched_rows": 0,
            "coverage_pct": 0.0,
            "warnings": [],
        },
        "kpis": [],
        "charts": [],
        "table": None,
        "findings": [],
        "alerts": [],
        "actions": [],
        "available": False,
        "message": message,
    }


def _date_filter_mask(
    dates: pd.Series, date_from: str | None, date_to: str | None
) -> pd.Series:
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


def _group_sum(
    labels: pd.Series,
    values: pd.Series,
    mask: pd.Series,
    *,
    limit: int = TOP_LIMIT,
) -> list[tuple[str, float]]:
    frame = pd.DataFrame({"label": labels, "value": values})[mask].dropna(subset=["label"])
    if frame.empty:
        return []
    grouped = (
        frame.groupby("label")["value"].sum().sort_values(ascending=False).head(limit)
    )
    return [(str(index), float(total)) for index, total in grouped.items()]


def build_relationship_dashboard(
    frames: dict[str, pd.DataFrame],
    mappings: dict[str, dict[str, str]],
    results: dict[str, dict],
    relationship: dict[str, Any],
    *,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """Construye el dashboard de UNA relación. Nunca lanza por datos: cuando la
    relación no es válida devuelve ``available: False`` con un motivo claro."""

    left_name = str(relationship.get("left_sheet", ""))
    right_name = str(relationship.get("right_sheet", ""))
    left_keys = relationship.get("left_keys") or []
    right_keys = relationship.get("right_keys") or []
    currency = _currency_label(results, left_name) if left_name in results else "CLP"

    if left_name not in frames or right_name not in frames:
        return _empty_dashboard(relationship, "generic", currency, "Las hojas de la relación no están disponibles.")

    left = frames[left_name]
    right = frames[right_name]
    left_mapping = resolve_mapping([str(c) for c in left.columns], mappings.get(left_name))
    right_mapping = resolve_mapping([str(c) for c in right.columns], mappings.get(right_name))
    template, label, purpose = classify_relationship_template(
        left_name, left, left_mapping, right_name, right, right_mapping
    )
    relation_meta = {**relationship, "template": template, "label": label, "purpose": purpose}

    # El inventario multi-snapshot se colapsa al último por clave para el JOIN
    # (así no multiplica ventas). El frame ORIGINAL se conserva para el stock.
    join_right = right
    if template == "sales_inventory":
        join_right = collapse_inventory_snapshots(right, keys=list(right_keys))

    stats = relation_stats(left, list(left_keys), join_right, list(right_keys))
    if not stats.safe:
        return _empty_dashboard(
            relation_meta, template, currency, stats.reason or "La relación no es segura."
        )

    # Bloqueo de monedas incompatibles cuando la relación calcula costos.
    if purpose in {"ventas_costos", "compras_costos"}:
        left_currency = results.get(left_name, {}).get("_moneda")
        right_currency = results.get(right_name, {}).get("_moneda")
        if isinstance(left_currency, CurrencyDetection) and isinstance(
            right_currency, CurrencyDetection
        ):
            if (
                left_currency.mixta
                or right_currency.mixta
                or left_currency.dominante != right_currency.dominante
            ):
                return _empty_dashboard(
                    relation_meta,
                    template,
                    currency,
                    "Las hojas usan monedas incompatibles; los costos y la utilidad quedan bloqueados.",
                )

    join = {
        "left_sheet": left_name,
        "right_sheet": right_name,
        "left_keys": list(left_keys),
        "right_keys": list(right_keys),
        "type": "left",
    }
    try:
        merged, merged_mapping, provenance = join_related_frames(
            {left_name: left, right_name: join_right}, mappings, join
        )
    except (KeyError, ValueError) as exc:
        return _empty_dashboard(relation_meta, template, currency, str(exc))

    context = _DashboardContext(
        left_name=left_name,
        right_name=right_name,
        left_keys=list(left_keys),
        right_keys=list(right_keys),
        merged=merged,
        merged_mapping=merged_mapping,
        right=right,
        right_mapping=right_mapping,
        provenance=provenance,
        relation=relation_meta,
        template=template,
        currency=currency,
        date_from=date_from,
        date_to=date_to,
        derived_cost=provenance.get("costo_derivado"),
    )
    return context.build()


class _DashboardContext:
    def __init__(self, **kwargs: Any) -> None:
        self.left_name: str = kwargs["left_name"]
        self.right_name: str = kwargs["right_name"]
        self.left_keys: list[str] = kwargs["left_keys"]
        self.right_keys: list[str] = kwargs["right_keys"]
        self.merged: pd.DataFrame = kwargs["merged"]
        self.merged_mapping: dict[str, str] = kwargs["merged_mapping"]
        self.right: pd.DataFrame = kwargs["right"]
        self.right_mapping: dict[str, str] = kwargs["right_mapping"]
        self.provenance: dict[str, Any] = kwargs["provenance"]
        self.relation: dict[str, Any] = kwargs["relation"]
        self.template: str = kwargs["template"]
        self.currency: str = kwargs["currency"]
        self.date_from: str | None = kwargs["date_from"]
        self.date_to: str | None = kwargs["date_to"]
        self.derived_cost: dict[str, Any] | None = kwargs["derived_cost"]

        merged = self.merged
        mapping = self.merged_mapping
        self.date_col = mapping.get("fecha") or find_column(merged.columns, "fecha")
        self.amount_col = mapping.get("monto")
        self.quantity_col = mapping.get("cantidad")
        self.cost_col = mapping.get("costo")
        self.product_key = (
            mapping.get("producto")
            or find_column(merged.columns, "sku", "producto")
            or find_column(merged.columns, "id", "producto")
        )
        self.category_col = mapping.get("categoria") or find_column(merged.columns, "categoria")
        self.product_name_col = find_column(merged.columns, "nombre", "producto") or find_column(
            merged.columns, "producto", excluded=("id", "codigo", "sku")
        )
        status_col = find_column(merged.columns, "estado")

        self.dates = _dates(merged, self.date_col)
        self.reference_date = _period_reference(self.dates)
        structural = structural_total_mask(merged, self.date_col)
        cancelled = _status_mask(merged, status_col, r"\b(?:anulad|cancelad|void)\w*")
        period_mask = _date_filter_mask(self.dates, self.date_from, self.date_to)
        self.mask = ~structural & ~cancelled & period_mask
        self.amount = numeric_series(merged, self.amount_col)
        self.quantity = numeric_series(merged, self.quantity_col)
        self.cost = numeric_series(merged, self.cost_col)

    # ── helpers de agregación ────────────────────────────────────────────────
    def _label_series(self, prefer_name: bool = True) -> pd.Series:
        column = None
        if prefer_name and self.product_name_col:
            column = self.product_name_col
        elif self.product_key:
            column = self.product_key
        elif self.product_name_col:
            column = self.product_name_col
        if column is None:
            return pd.Series(None, index=self.merged.index, dtype="object")
        return self.merged[column].astype("object")

    def _period(self) -> dict[str, Any]:
        valid = self.dates.dropna()
        meses = (
            sorted({date.strftime("%Y-%m") for date in valid})
            if not valid.empty
            else []
        )
        return {
            "desde": self.date_from,
            "hasta": self.date_to,
            "referencia": _iso_or_none(self.reference_date),
            "meses": meses,
        }

    def _quality(self) -> dict[str, Any]:
        unmatched = int(self.provenance.get("filas_sin_correspondencia", 0) or 0)
        rows_after = int(self.provenance.get("rows_after", len(self.merged)))
        matched = max(rows_after - unmatched, 0)
        warnings: list[str] = []
        if unmatched:
            warnings.append(
                f"{unmatched:,} filas de {self.left_name} no encontraron correspondencia "
                f"en {self.right_name}.".replace(",", ".")
            )
        return {
            "rows_before": int(self.provenance.get("rows_before", len(self.merged))),
            "rows_after": rows_after,
            "matched_rows": matched,
            "unmatched_rows": unmatched,
            "coverage_pct": round(matched / max(rows_after, 1) * 100, 1),
            "warnings": warnings,
        }

    def _cost_coverage(self) -> tuple[int, int, float | None]:
        if self.cost_col is None:
            return 0, int(self.mask.sum()), None
        with_cost = int((self.mask & self.cost.notna()).sum())
        total = int(self.mask.sum())
        coverage = round(with_cost / total * 100, 1) if total else None
        return with_cost, total, coverage

    # ── despacho por plantilla ───────────────────────────────────────────────
    def build(self) -> dict[str, Any]:
        builders = {
            "products_sales": self._products_sales,
            "sales_costs": self._sales_costs,
            "sales_inventory": self._sales_inventory,
            "sales_customers": lambda: self._dimensional("cliente", "clientes"),
            "sales_sellers": lambda: self._dimensional("vendedor", "vendedores"),
            "sales_branches": lambda: self._dimensional("sucursal", "sucursales"),
            "purchases_costs": self._purchases_costs,
            "expenses_branches": self._expenses_branches,
            "generic": self._generic,
        }
        builder = builders.get(self.template, self._generic)
        kpis, charts, table, findings, alerts, actions = builder()
        available = any(kpi["available"] for kpi in kpis) or table is not None
        return {
            "relation": self.relation,
            "template": self.template,
            "period": self._period(),
            "currency": self.currency,
            "quality": self._quality(),
            "kpis": kpis,
            "charts": charts,
            "table": table,
            "findings": findings,
            "alerts": alerts,
            "actions": actions,
            "available": available,
            "message": None
            if available
            else "La relación no tiene variables suficientes para un dashboard.",
        }

    # ── ventas base (compartido) ─────────────────────────────────────────────
    def _sales_totals(self) -> dict[str, float | int | None]:
        mask = self.mask
        amount_values = self.amount[mask]
        quantity_values = self.quantity[mask]
        ingresos = (
            float(amount_values.sum())
            if self.amount_col and amount_values.notna().any()
            else None
        )
        unidades = (
            float(quantity_values.sum())
            if self.quantity_col and quantity_values.notna().any()
            else None
        )
        registros = int(mask.sum())
        productos = None
        if self.product_key:
            keys = self.merged.loc[mask, self.product_key].astype("object")
            productos = int(keys.dropna().nunique())
        return {
            "ingresos": ingresos,
            "unidades": unidades,
            "registros": registros,
            "productos": productos,
        }

    def _gross_margin(self) -> dict[str, float | None]:
        if self.cost_col is None:
            return {"costo": None, "utilidad": None, "margen": None}
        paired = self.mask & self.amount.notna() & self.cost.notna()
        if not paired.any():
            return {"costo": None, "utilidad": None, "margen": None}
        ingreso_par = float(self.amount[paired].sum())
        costo_par = float(self.cost[paired].sum())
        utilidad = ingreso_par - costo_par
        margen = utilidad / ingreso_par if ingreso_par else None
        return {"costo": costo_par, "utilidad": utilidad, "margen": margen}

    def _top_products_table(
        self, *, with_margin: bool
    ) -> dict[str, Any] | None:
        if not self.product_key:
            return None
        mask = self.mask
        base = pd.DataFrame(
            {
                "clave": self.merged.loc[mask, self.product_key].astype("object"),
                "nombre": self._label_series()[mask],
                "categoria": (
                    self.merged.loc[mask, self.category_col].astype("object")
                    if self.category_col
                    else None
                ),
                "ingresos": self.amount[mask] if self.amount_col else 0.0,
                "unidades": self.quantity[mask] if self.quantity_col else 0.0,
                "costo": self.cost[mask] if self.cost_col else float("nan"),
            }
        ).dropna(subset=["clave"])
        if base.empty:
            return None
        agg = base.groupby("clave").agg(
            nombre=("nombre", "first"),
            categoria=("categoria", "first"),
            ingresos=("ingresos", lambda values: values.sum(min_count=1)),
            unidades=("unidades", lambda values: values.sum(min_count=1)),
            costo=("costo", lambda values: values.sum(min_count=1)),
        )
        agg = agg.sort_values("ingresos", ascending=False)
        columns = [
            {"key": "nombre", "label": "Producto", "format": "text"},
            {"key": "ingresos", "label": "Ingresos", "format": "currency"},
            {"key": "unidades", "label": "Unidades", "format": "number"},
        ]
        if self.category_col:
            columns.insert(1, {"key": "categoria", "label": "Categoría", "format": "text"})
        if with_margin and self.cost_col:
            columns.append({"key": "utilidad", "label": "Utilidad", "format": "currency"})
            columns.append({"key": "margen", "label": "Margen", "format": "percent"})
        rows: list[dict[str, Any]] = []
        for clave, row in agg.head(TABLE_LIMIT).iterrows():
            nombre = row["nombre"] if pd.notna(row["nombre"]) else str(clave)
            entry: dict[str, Any] = {
                "nombre": str(nombre),
                "ingresos": _clean_number(row["ingresos"]),
                "unidades": _clean_number(row["unidades"]),
            }
            if self.category_col:
                entry["categoria"] = (
                    str(row["categoria"]) if pd.notna(row["categoria"]) else "Sin categoría"
                )
            if with_margin and self.cost_col:
                costo = row["costo"]
                utilidad = (
                    row["ingresos"] - costo if pd.notna(costo) else None
                )
                entry["utilidad"] = _clean_number(utilidad)
                entry["margen"] = (
                    _clean_number(utilidad / row["ingresos"])
                    if utilidad is not None and row["ingresos"]
                    else None
                )
            rows.append(entry)
        return {
            "id": "productos",
            "title": "Detalle de productos",
            "columns": columns,
            "rows": rows,
            "total_rows": int(len(agg)),
        }

    def _revenue_by_category_chart(self) -> dict[str, Any] | None:
        if not self.category_col or not self.amount_col:
            return None
        data = _group_sum(
            self.merged[self.category_col].astype("object"), self.amount, self.mask
        )
        if not data:
            return None
        return {
            "id": "ingresos_categoria",
            "kind": "donut" if 2 <= len(data) <= 5 else "bar",
            "title": "Ingresos por categoría",
            "help": "Suma de ingresos del periodo por categoría del producto.",
            "category_key": "categoria",
            "series": [{"key": "ingresos", "label": "Ingresos", "format": "currency"}],
            "data": [{"categoria": name, "ingresos": _clean_number(value)} for name, value in data],
        }

    def _top_products_chart(self) -> dict[str, Any] | None:
        if not self.product_key or not self.amount_col:
            return None
        labels = self._label_series()
        data = _group_sum(labels, self.amount, self.mask)
        if not data:
            return None
        return {
            "id": "top_productos",
            "kind": "bar",
            "title": "Top 10 productos por ingresos",
            "help": "Los 10 productos con mayores ingresos en el periodo.",
            "category_key": "producto",
            "series": [{"key": "ingresos", "label": "Ingresos", "format": "currency"}],
            "data": [{"producto": name, "ingresos": _clean_number(value)} for name, value in data],
        }

    # ── PRODUCTOS ↔ VENTAS ───────────────────────────────────────────────────
    def _products_sales(self):
        totals = self._sales_totals()
        margin = self._gross_margin()
        with_cost, total, coverage = self._cost_coverage()
        top = _group_sum(self._label_series(), self.amount, self.mask) if self.amount_col else []
        top10_share = None
        if totals["ingresos"]:
            top10_share = sum(value for _, value in top) / totals["ingresos"] * 100
        kpis = [
            _kpi("ingresos", "Ingresos totales", _clean_number(totals["ingresos"]), "currency"),
            _kpi("unidades", "Unidades vendidas", _clean_number(totals["unidades"]), "number"),
            _kpi("productos", "Productos vendidos", totals["productos"], "integer",
                 help_text="Identificadores de producto distintos con ventas."),
        ]
        if margin["margen"] is not None:
            kpis.append(_kpi("margen", "Margen bruto", _clean_number(margin["margen"] * 100), "percent",
                             help_text="Solo sobre ventas con costo pareado.", tone="positive"))
        kpis.append(_kpi("top10", "Contribución Top 10", _clean_number(top10_share), "percent",
                         help_text="Participación de los 10 productos líderes en los ingresos."))
        charts = [c for c in (self._top_products_chart(), self._revenue_by_category_chart()) if c]
        table = self._top_products_table(with_margin=margin["margen"] is not None)
        findings, alerts, actions = self._insights_products(totals, margin, coverage, top10_share)
        return kpis, charts, table, findings, alerts, actions

    def _insights_products(self, totals, margin, coverage, top10_share):
        findings: list[dict[str, Any]] = []
        alerts: list[dict[str, Any]] = []
        actions: list[dict[str, Any]] = []
        if top10_share is not None and top10_share >= 60:
            findings.append(_finding(
                "concentracion_top10", "Ventas concentradas en pocos productos",
                f"El Top 10 concentra {top10_share:.0f}% de los ingresos.", "warning",
                evidence=f"{top10_share:.1f}% en 10 productos",
                impact=None, action_id="ver_top_productos",
            ))
            actions.append(_action("ver_top_productos", "Ver Top 10", "highlight", "top_productos"))
        if coverage is not None and coverage < 100:
            alerts.append(_finding(
                "cobertura_costos", "Ventas sin costo asociado",
                f"Solo {coverage:.0f}% de las ventas del periodo tienen costo; el margen se calcula sobre esa porción.",
                "warning", evidence=f"cobertura de costos {coverage:.1f}%", impact=None, action_id=None,
            ))
        return findings, alerts, actions

    # ── VENTAS ↔ COSTOS ──────────────────────────────────────────────────────
    def _sales_costs(self):
        totals = self._sales_totals()
        margin = self._gross_margin()
        with_cost, total, coverage = self._cost_coverage()
        profit = self._product_profit()
        rentables = int((profit["margen"] > 0).sum()) if not profit.empty else None
        riesgo = int((profit["margen"] <= 0).sum()) if not profit.empty else None
        kpis = [
            _kpi("ventas", "Ventas netas", _clean_number(totals["ingresos"]), "currency"),
            _kpi("costo", "Costo de venta", _clean_number(margin["costo"]), "currency"),
            _kpi("utilidad", "Utilidad bruta", _clean_number(margin["utilidad"]), "currency",
                 tone="positive" if (margin["utilidad"] or 0) >= 0 else "risk"),
            _kpi("margen", "Margen bruto",
                 _clean_number(margin["margen"] * 100) if margin["margen"] is not None else None,
                 "percent", help_text="Utilidad bruta / ingresos pareados."),
            _kpi("cobertura", "Cobertura de costos", _clean_number(coverage), "percent",
                 help_text=f"{with_cost} de {total} ventas del periodo tienen costo."),
            _kpi("rentables", "Productos rentables", rentables, "integer", tone="positive"),
            _kpi("riesgo", "Productos en riesgo", riesgo, "integer", tone="risk"),
        ]
        charts = [c for c in (self._profit_by_product_chart(profit), self._margin_by_category_chart()) if c]
        table = self._top_products_table(with_margin=True)
        findings, alerts, actions = self._insights_costs(profit, coverage, margin)
        return kpis, charts, table, findings, alerts, actions

    def _product_profit(self) -> pd.DataFrame:
        if not self.product_key or self.cost_col is None or not self.amount_col:
            return pd.DataFrame(columns=["nombre", "ingresos", "costo", "utilidad", "margen"])
        paired = self.mask & self.amount.notna() & self.cost.notna()
        base = pd.DataFrame(
            {
                "clave": self.merged.loc[paired, self.product_key].astype("object"),
                "nombre": self._label_series()[paired],
                "ingresos": self.amount[paired],
                "costo": self.cost[paired],
            }
        ).dropna(subset=["clave"])
        if base.empty:
            return pd.DataFrame(columns=["nombre", "ingresos", "costo", "utilidad", "margen"])
        agg = base.groupby("clave").agg(
            nombre=("nombre", "first"), ingresos=("ingresos", "sum"), costo=("costo", "sum")
        )
        agg["utilidad"] = agg["ingresos"] - agg["costo"]
        agg["margen"] = agg.apply(
            lambda row: row["utilidad"] / row["ingresos"] if row["ingresos"] else 0.0, axis=1
        )
        return agg

    def _profit_by_product_chart(self, profit: pd.DataFrame) -> dict[str, Any] | None:
        if profit.empty:
            return None
        top = profit.sort_values("utilidad", ascending=False).head(TOP_LIMIT)
        data = [
            {
                "producto": str(row["nombre"]) if pd.notna(row["nombre"]) else str(index),
                "utilidad": _clean_number(row["utilidad"]),
            }
            for index, row in top.iterrows()
        ]
        return {
            "id": "utilidad_producto",
            "kind": "bar",
            "title": "Top productos por utilidad bruta",
            "help": "Utilidad bruta (ingreso − costo pareado) por producto.",
            "category_key": "producto",
            "series": [{"key": "utilidad", "label": "Utilidad", "format": "currency"}],
            "data": data,
        }

    def _margin_by_category_chart(self) -> dict[str, Any] | None:
        if not self.category_col or self.cost_col is None or not self.amount_col:
            return None
        paired = self.mask & self.amount.notna() & self.cost.notna()
        base = pd.DataFrame(
            {
                "categoria": self.merged.loc[paired, self.category_col].astype("object"),
                "ingresos": self.amount[paired],
                "costo": self.cost[paired],
            }
        ).dropna(subset=["categoria"])
        if base.empty:
            return None
        agg = base.groupby("categoria").agg(ingresos=("ingresos", "sum"), costo=("costo", "sum"))
        agg["margen"] = agg.apply(
            lambda row: (row["ingresos"] - row["costo"]) / row["ingresos"] * 100
            if row["ingresos"] else 0.0,
            axis=1,
        )
        agg = agg.sort_values("margen", ascending=False).head(TOP_LIMIT)
        return {
            "id": "margen_categoria",
            "kind": "bar",
            "title": "Margen por categoría",
            "help": "Margen bruto porcentual por categoría (solo ventas pareadas).",
            "category_key": "categoria",
            "series": [{"key": "margen", "label": "Margen", "format": "percent"}],
            "data": [
                {"categoria": str(index), "margen": _clean_number(row["margen"])}
                for index, row in agg.iterrows()
            ],
        }

    def _insights_costs(self, profit, coverage, margin):
        findings: list[dict[str, Any]] = []
        alerts: list[dict[str, Any]] = []
        actions: list[dict[str, Any]] = []
        if not profit.empty:
            negativos = profit[profit["margen"] < 0]
            if not negativos.empty:
                perdida = float(negativos["utilidad"].sum())
                alerts.append(_finding(
                    "margen_negativo", "Productos con margen negativo",
                    f"{len(negativos)} producto(s) venden bajo su costo.",
                    "risk", evidence=f"{len(negativos)} productos bajo costo",
                    impact={"value": _clean_number(perdida), "format": "currency",
                            "label": "Pérdida bruta acumulada"},
                    action_id="ver_criticos",
                ))
                actions.append(_action("ver_criticos", "Ver productos críticos", "highlight", "productos"))
            mejor = profit.sort_values("margen", ascending=False).head(1)
            if not mejor.empty:
                row = mejor.iloc[0]
                findings.append(_finding(
                    "mejor_margen", "Producto más rentable",
                    f"{row['nombre']} lidera el margen con {row['margen'] * 100:.0f}%.",
                    "success", evidence=f"margen {row['margen'] * 100:.1f}%", impact=None, action_id=None,
                ))
        if coverage is not None and coverage < 100:
            alerts.append(_finding(
                "costos_faltantes", "Costos faltantes",
                f"{100 - coverage:.0f}% de las ventas no tienen costo; no se calcula margen sobre ellas.",
                "warning", evidence=f"cobertura {coverage:.1f}%", impact=None, action_id=None,
            ))
        if margin["margen"] is not None and margin["margen"] < LOW_MARGIN_THRESHOLD:
            findings.append(_finding(
                "margen_bajo", "Margen bruto bajo",
                f"El margen bruto del periodo es {margin['margen'] * 100:.0f}%, bajo el umbral de referencia.",
                "warning", evidence=f"margen {margin['margen'] * 100:.1f}%", impact=None, action_id=None,
            ))
        return findings, alerts, actions

    # ── VENTAS ↔ INVENTARIO ──────────────────────────────────────────────────
    def _sales_inventory(self):
        totals = self._sales_totals()
        stock = self._inventory_stock()
        days_observed = self._days_observed()
        rows, total_stock = self._coverage_rows(stock, days_observed)
        risky = [r for r in rows if r["estado"] in {"critico", "alto"}]
        overall = self._overall_risk(rows)
        avg_days = (
            _clean_number(
                sum(r["dias_cobertura"] for r in rows if r["dias_cobertura"] is not None)
                / max(len([r for r in rows if r["dias_cobertura"] is not None]), 1)
            )
            if rows
            else None
        )
        kpis = [
            _kpi("ventas", "Ventas", _clean_number(totals["ingresos"]), "currency"),
            _kpi("unidades", "Unidades vendidas", _clean_number(totals["unidades"]), "number"),
            _kpi("stock", "Stock disponible", _clean_number(total_stock), "number",
                 help_text="Último snapshot válido por producto/sucursal (no se suma por el join)."),
            _kpi("cobertura", "Días de cobertura promedio", avg_days, "days"),
            _kpi("riesgo", "Productos en riesgo", len(risky) if rows else None, "integer", tone="risk"),
            _kpi("nivel", "Nivel general de riesgo", overall, "text",
                 tone="risk" if overall in {"critico", "alto"} else "default"),
        ]
        charts = [c for c in (self._inventory_risk_chart(rows),) if c]
        table = self._inventory_table(rows)
        findings, alerts, actions = self._insights_inventory(rows)
        return kpis, charts, table, findings, alerts, actions

    def _inventory_stock(self) -> pd.DataFrame:
        """Último snapshot válido por producto (y sucursal si existe), sin sumar
        stock repetido por el join. Devuelve columnas clave/[sucursal]/stock.

        La clave se normaliza con la MISMA función del join para que las
        unidades vendidas (de la izquierda) crucen con el stock (de la derecha).
        """
        right = self.right
        stock_col = self.right_mapping.get("cantidad") or find_column(right.columns, "stock")
        # La clave de inventario es la clave derecha de la relación, no un nombre.
        key_col = self.right_keys[0] if self.right_keys else None
        if not stock_col or not key_col or stock_col not in right.columns or key_col not in right.columns:
            return pd.DataFrame(columns=["clave", "sucursal", "stock"])
        branch_col = self.right_mapping.get("sucursal") or find_column(right.columns, "sucursal")
        date_col = find_column(right.columns, "fecha") or find_column(right.columns, "snapshot")
        frame = right.copy()
        frame["_stock"] = numeric_series(frame, stock_col)
        frame["_clave"] = frame[key_col].map(_text_key)
        if branch_col and branch_col in frame.columns:
            frame["_sucursal"] = frame[branch_col].astype("object")
        else:
            frame["_sucursal"] = None
        if date_col and date_col in frame.columns:
            frame["_fecha"] = _dates(frame, date_col)
            if self.date_to:
                text = str(self.date_to).strip()
                end = (
                    pd.Period(text, freq="M").end_time.normalize()
                    if len(text) == 7
                    else pd.to_datetime(text)
                )
                frame = frame[frame["_fecha"].isna() | frame["_fecha"].le(end)]
            frame = frame.sort_values("_fecha")
        frame = frame.dropna(subset=["_clave"])
        latest = frame.groupby(["_clave", "_sucursal"], dropna=False).tail(1)
        return latest[["_clave", "_sucursal", "_stock"]].rename(
            columns={"_clave": "clave", "_sucursal": "sucursal", "_stock": "stock"}
        )

    def _days_observed(self) -> int:
        valid = self.dates[self.mask].dropna()
        if valid.empty:
            return 0
        return max(int((valid.max() - valid.min()).days) + 1, 1)

    def _coverage_rows(self, stock: pd.DataFrame, days_observed: int):
        left_key = self.left_keys[0] if self.left_keys else None
        if stock.empty or not left_key or left_key not in self.merged.columns:
            return [], None
        # Unidades vendidas por producto en el periodo, cruzadas por la MISMA
        # clave normalizada del join (no por el nombre para mostrar).
        sold = pd.DataFrame(
            {
                "clave": self.merged.loc[self.mask, left_key].map(_text_key),
                "nombre": self._label_series()[self.mask],
                "categoria": (
                    self.merged.loc[self.mask, self.category_col].astype("object")
                    if self.category_col
                    else None
                ),
                "unidades": self.quantity[self.mask] if self.quantity_col else 0.0,
            }
        ).dropna(subset=["clave"])
        sold_agg = sold.groupby("clave").agg(
            nombre=("nombre", "first"),
            categoria=("categoria", "first"),
            unidades=("unidades", "sum"),
        )
        stock_agg = stock.groupby("clave")["stock"].sum()
        total_stock = float(stock_agg.sum())
        rows: list[dict[str, Any]] = []
        for clave, stock_value in stock_agg.items():
            sold_row = sold_agg.loc[clave] if clave in sold_agg.index else None
            unidades = float(sold_row["unidades"]) if sold_row is not None else 0.0
            daily = unidades / days_observed if days_observed and unidades else None
            dias = (
                round(float(stock_value) / daily, 1)
                if daily and daily > 0
                else None
            )
            rotacion = round(unidades / float(stock_value), 2) if stock_value else None
            estado = _coverage_state(dias if unidades else None)
            nombre = (
                sold_row["nombre"]
                if sold_row is not None and pd.notna(sold_row["nombre"])
                else str(clave)
            )
            rows.append({
                "producto": str(nombre),
                "categoria": (
                    str(sold_row["categoria"])
                    if sold_row is not None and pd.notna(sold_row["categoria"])
                    else "Sin categoría"
                ),
                "unidades": _clean_number(unidades),
                "stock": _clean_number(float(stock_value)),
                "dias_cobertura": dias,
                "rotacion": rotacion,
                "estado": estado,
            })
        rows.sort(key=lambda r: (r["dias_cobertura"] is None, r["dias_cobertura"] or 0))
        return rows, total_stock

    def _overall_risk(self, rows) -> str | None:
        if not rows:
            return None
        states = [r["estado"] for r in rows]
        for level in ("critico", "alto", "medio"):
            if states.count(level) >= max(1, len(states) // 5):
                return level
        return "sano"

    def _inventory_risk_chart(self, rows) -> dict[str, Any] | None:
        risky = [r for r in rows if r["dias_cobertura"] is not None][:TOP_LIMIT]
        if not risky:
            return None
        return {
            "id": "riesgo_quiebre",
            "kind": "bar",
            "title": "Top productos con riesgo de quiebre",
            "help": "Días de cobertura = stock disponible / venta diaria promedio.",
            "category_key": "producto",
            "series": [{"key": "dias_cobertura", "label": "Días de cobertura", "format": "days"}],
            "data": [{"producto": r["producto"], "dias_cobertura": r["dias_cobertura"]} for r in risky],
        }

    def _inventory_table(self, rows) -> dict[str, Any] | None:
        if not rows:
            return None
        columns = [
            {"key": "producto", "label": "Producto", "format": "text"},
            {"key": "categoria", "label": "Categoría", "format": "text"},
            {"key": "unidades", "label": "Unidades vendidas", "format": "number"},
            {"key": "stock", "label": "Stock disponible", "format": "number"},
            {"key": "dias_cobertura", "label": "Días cobertura", "format": "days"},
            {"key": "rotacion", "label": "Rotación", "format": "number"},
            {"key": "estado", "label": "Estado", "format": "text"},
        ]
        return {
            "id": "inventario_critico",
            "title": "Inventario crítico",
            "columns": columns,
            "rows": rows[:TABLE_LIMIT],
            "total_rows": len(rows),
        }

    def _insights_inventory(self, rows):
        findings: list[dict[str, Any]] = []
        alerts: list[dict[str, Any]] = []
        actions: list[dict[str, Any]] = []
        criticos = [r for r in rows if r["estado"] == "critico"]
        if criticos:
            alerts.append(_finding(
                "riesgo_quiebre", "Riesgo de quiebre de stock",
                f"{len(criticos)} producto(s) tienen menos de {COVERAGE_CRITICAL_DAYS} días de cobertura.",
                "risk", evidence=f"{len(criticos)} productos críticos", impact=None,
                action_id="ver_inventario",
            ))
            actions.append(_action("ver_inventario", "Ver inventario crítico", "highlight", "inventario_critico"))
        sobre = [
            r for r in rows
            if r["dias_cobertura"] is not None and r["dias_cobertura"] > OVERSTOCK_DAYS
        ]
        if sobre:
            findings.append(_finding(
                "sobreinventario", "Sobreinventario",
                f"{len(sobre)} producto(s) superan {OVERSTOCK_DAYS} días de cobertura.",
                "warning", evidence=f"{len(sobre)} productos con exceso", impact=None, action_id=None,
            ))
        return findings, alerts, actions

    # ── DIMENSIONAL (clientes / vendedores / sucursales) ─────────────────────
    def _dimensional(self, role: str, plural: str):
        column = self.merged_mapping.get(role) or find_column(self.merged.columns, role)
        totals = self._sales_totals()
        margin = self._gross_margin()
        kpis = [
            _kpi("ingresos", "Ingresos", _clean_number(totals["ingresos"]), "currency"),
            _kpi("ticket", "Ticket promedio",
                 _clean_number(totals["ingresos"] / totals["registros"])
                 if totals["ingresos"] and totals["registros"] else None,
                 "currency"),
        ]
        distinct = None
        if column and column in self.merged.columns:
            distinct = int(self.merged.loc[self.mask, column].astype("object").dropna().nunique())
        kpis.append(_kpi(f"n_{plural}", f"{plural.capitalize()}", distinct, "integer"))
        if margin["margen"] is not None:
            kpis.append(_kpi("margen", "Margen bruto", _clean_number(margin["margen"] * 100), "percent"))
        chart = None
        table = None
        top10_share = None
        if column and column in self.merged.columns and self.amount_col:
            data = _group_sum(self.merged[column].astype("object"), self.amount, self.mask)
            identified_total = float(
                self.amount[self.mask & self.merged[column].astype("object").notna()].sum()
            )
            if identified_total:
                top10_share = sum(v for _, v in data) / identified_total * 100
            if data:
                chart = {
                    "id": "ranking",
                    "kind": "bar",
                    "title": f"Top {plural} por ingresos",
                    "help": f"Ingresos por {role} identificado.",
                    "category_key": role,
                    "series": [{"key": "ingresos", "label": "Ingresos", "format": "currency"}],
                    "data": [{role: name, "ingresos": _clean_number(v)} for name, v in data],
                }
                table = {
                    "id": "ranking_tabla",
                    "title": f"Desempeño por {role}",
                    "columns": [
                        {"key": role, "label": role.capitalize(), "format": "text"},
                        {"key": "ingresos", "label": "Ingresos", "format": "currency"},
                    ],
                    "rows": [{role: name, "ingresos": _clean_number(v)} for name, v in data],
                    "total_rows": len(data),
                }
        kpis.append(_kpi("concentracion", "Concentración Top 10", _clean_number(top10_share), "percent",
                         help_text="Sobre ingresos con identificador presente."))
        findings: list[dict[str, Any]] = []
        alerts: list[dict[str, Any]] = []
        actions: list[dict[str, Any]] = []
        if top10_share is not None and top10_share >= 60:
            findings.append(_finding(
                "concentracion", "Alta concentración",
                f"El Top 10 concentra {top10_share:.0f}% de los ingresos identificados.",
                "warning", evidence=f"{top10_share:.1f}%", impact=None, action_id=None,
            ))
        return kpis, [c for c in (chart,) if c], table, findings, alerts, actions

    # ── COMPRAS ↔ COSTOS ─────────────────────────────────────────────────────
    def _purchases_costs(self):
        totals = self._sales_totals()
        kpis = [
            _kpi("compras", "Compras totales", _clean_number(totals["ingresos"]), "currency"),
            _kpi("unidades", "Unidades compradas", _clean_number(totals["unidades"]), "number"),
            _kpi("productos", "Productos comprados", totals["productos"], "integer"),
        ]
        charts = [c for c in (self._top_products_chart(),) if c]
        table = self._top_products_table(with_margin=False)
        return kpis, charts, table, [], [], []

    # ── GASTOS ↔ SUCURSALES ──────────────────────────────────────────────────
    def _expenses_branches(self):
        totals = self._sales_totals()
        column = self.merged_mapping.get("sucursal") or find_column(self.merged.columns, "sucursal")
        distinct = None
        avg = None
        chart = None
        if column and column in self.merged.columns and self.amount_col:
            distinct = int(self.merged.loc[self.mask, column].astype("object").dropna().nunique())
            if distinct:
                avg = totals["ingresos"] / distinct if totals["ingresos"] else None
            data = _group_sum(self.merged[column].astype("object"), self.amount, self.mask)
            if data:
                chart = {
                    "id": "gastos_sucursal",
                    "kind": "bar",
                    "title": "Gastos por sucursal",
                    "help": "Suma de gastos del periodo por sucursal.",
                    "category_key": "sucursal",
                    "series": [{"key": "gastos", "label": "Gastos", "format": "currency"}],
                    "data": [{"sucursal": name, "gastos": _clean_number(v)} for name, v in data],
                }
        kpis = [
            _kpi("gastos", "Gastos totales", _clean_number(totals["ingresos"]), "currency"),
            _kpi("sucursales", "Sucursales", distinct, "integer"),
            _kpi("promedio", "Gasto promedio por sucursal", _clean_number(avg), "currency"),
        ]
        return kpis, [c for c in (chart,) if c], None, [], [], []

    # ── RELACIÓN GENÉRICA ────────────────────────────────────────────────────
    def _generic(self):
        quality = self._quality()
        kpis = [
            _kpi("filas", "Filas de la tabla principal", quality["rows_after"], "integer"),
            _kpi("relacionados", "Registros relacionados", quality["matched_rows"], "integer"),
            _kpi("sin_correspondencia", "Sin correspondencia", quality["unmatched_rows"], "integer",
                 tone="warning" if quality["unmatched_rows"] else "default"),
            _kpi("cobertura", "Cobertura", quality["coverage_pct"], "percent"),
            _kpi("cardinalidad", "Cardinalidad", self.relation.get("cardinality"), "text"),
        ]
        charts: list[dict[str, Any]] = []
        cat = self.category_col or find_column(self.merged.columns, "tipo")
        if cat and self.amount_col:
            chart = self._revenue_by_category_chart()
            if chart:
                charts.append(chart)
        table = None
        return kpis, charts, table, [], [], []


def _finding(
    finding_id: str,
    title: str,
    detail: str,
    severity: str,
    *,
    evidence: str | None,
    impact: dict[str, Any] | None,
    action_id: str | None,
) -> dict[str, Any]:
    return {
        "id": finding_id,
        "title": title,
        "detail": detail,
        "severity": severity,
        "evidence": evidence,
        "impact": impact,
        "action_id": action_id,
    }


def _action(action_id: str, label: str, kind: str, target: str | None) -> dict[str, Any]:
    return {"id": action_id, "label": label, "kind": kind, "target": target}
