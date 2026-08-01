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

from .business import (
    _applicable_unit_cost,
    _dates,
    _declared_sales_period,
    _sheet_kind,
    _status_mask,
    _text_key,
)
from .mapping import resolve_mapping
from .metrics import CurrencyDetection
from .multi_sheet import append_compatible_frames, join_related_frames, relation_stats
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


def _service_temporal_dashboard(
    left_name: str,
    left: pd.DataFrame,
    right_name: str,
    right: pd.DataFrame,
    relationship: dict[str, Any],
    currency: str,
    date_from: str | None,
    date_to: str | None,
) -> dict[str, Any] | None:
    """Dashboards auditables para los dos cruces temporales del modelo servicio."""

    strategy = relationship.get("join_strategy")
    if strategy == "vigencia_por_fecha":
        tech_left = find_column(left.columns, "cod", "tecnico")
        work_date = find_column(left.columns, "fecha")
        hours_col = find_column(left.columns, "horas")
        billable_col = find_column(left.columns, "factura")
        hour_type = find_column(left.columns, "tipo")
        tech_right = find_column(right.columns, "cod", "tecnico")
        valid_from = find_column(right.columns, "vigente", "desde")
        valid_to = find_column(right.columns, "vigente", "hasta")
        cost_rate = find_column(right.columns, "costo", "hora")
        sale_rate = find_column(right.columns, "valor", "hora", "venta")
        if not all(
            (
                tech_left,
                work_date,
                hours_col,
                billable_col,
                tech_right,
                valid_from,
                valid_to,
                cost_rate,
                sale_rate,
            )
        ):
            return _empty_dashboard(
                relationship,
                "generic",
                currency,
                "Faltan columnas para aplicar la vigencia de tarifas.",
            )
        work = left.copy()
        work["__row"] = range(len(work))
        work["__tech"] = work[tech_left].map(_text_key)
        work["__date"] = _dates(work, work_date)
        work["__hours"] = numeric_series(work, hours_col)
        work["__billable"] = (
            work[billable_col]
            .astype(str)
            .str.strip()
            .str.casefold()
            .isin({"sí", "si", "s", "1", "x", "true"})
        )
        work["__multiplier"] = (
            work[hour_type]
            .astype(str)
            .str.casefold()
            .str.contains("extra", na=False)
            .map({True: 1.5, False: 1.0})
            if hour_type
            else 1.0
        )
        work = work.loc[
            _date_filter_mask(work["__date"], date_from, date_to)
        ].copy()
        rates = right.copy()
        rates["__tech"] = rates[tech_right].map(_text_key)
        rates["__from"] = _dates(rates, valid_from)
        rates["__to"] = _dates(rates, valid_to)
        rates["__cost_rate"] = numeric_series(rates, cost_rate)
        rates["__sale_rate"] = numeric_series(rates, sale_rate)
        matched = work.merge(
            rates[
                [
                    "__tech",
                    "__from",
                    "__to",
                    "__cost_rate",
                    "__sale_rate",
                ]
            ],
            on="__tech",
            how="left",
        )
        matched = matched.loc[
            matched["__date"].between(
                matched["__from"], matched["__to"], inclusive="both"
            )
        ].copy()
        counts = matched.groupby("__row").size()
        if (counts > 1).any():
            return _empty_dashboard(
                relationship,
                "generic",
                currency,
                "Los tramos de tarifa se superponen y duplicarían horas.",
            )
        matched["ingreso"] = (
            matched["__hours"]
            * matched["__sale_rate"]
            * matched["__multiplier"]
        ).where(matched["__billable"], 0.0)
        matched["costo"] = (
            matched["__hours"]
            * matched["__cost_rate"]
            * matched["__multiplier"]
        )
        matched["utilidad"] = matched["ingreso"] - matched["costo"]
        matched_rows = int(matched["__row"].nunique())
        rows_before = len(work)
        revenue = float(matched["ingreso"].sum())
        cost = float(matched["costo"].sum())
        utility = revenue - cost
        total_hours = float(work["__hours"].sum())
        billable_hours = float(
            work.loc[work["__billable"], "__hours"].sum()
        )
        grouped = (
            matched.groupby(tech_left)
            .agg(
                horas=("__hours", "sum"),
                ingreso=("ingreso", "sum"),
                costo=("costo", "sum"),
                utilidad=("utilidad", "sum"),
            )
            .sort_values("utilidad", ascending=False)
            .head(TOP_LIMIT)
            .reset_index()
        )
        valid_dates = work["__date"].dropna()
        months = sorted(
            {value.strftime("%Y-%m") for value in valid_dates}
        )
        relation_meta = {
            **relationship,
            "template": "generic",
            "label": f"{left_name} ↔ {right_name}",
            "purpose": "service_rates_temporal",
            "cardinality": "muchos_a_uno_temporal",
            "safe": True,
            "coverage_left": round(matched_rows / max(rows_before, 1), 4),
            "coverage_right": 1.0,
            "overlap": round(matched_rows / max(rows_before, 1), 4),
        }
        return {
            "relation": relation_meta,
            "template": "generic",
            "period": {
                "desde": date_from,
                "hasta": date_to,
                "referencia": _iso_or_none(_period_reference(valid_dates)),
                "meses": months,
            },
            "currency": currency,
            "quality": {
                "rows_before": rows_before,
                "rows_after": rows_before,
                "matched_rows": matched_rows,
                "unmatched_rows": rows_before - matched_rows,
                "coverage_pct": round(matched_rows / max(rows_before, 1) * 100, 1),
                "warnings": [
                    "La tarifa se aplica por técnico y fecha dentro de su vigencia; unir solo por técnico duplicaría cada hora."
                ],
            },
            "kpis": [
                _kpi("ingreso_horas", "Ingreso por horas", _clean_number(revenue), "currency"),
                _kpi("costo_horas", "Costo de horas", _clean_number(cost), "currency"),
                _kpi("utilidad_horas", "Utilidad de horas", _clean_number(utility), "currency"),
                _kpi(
                    "margen_horas",
                    "Margen de horas",
                    _clean_number(utility / revenue * 100) if revenue else None,
                    "percent",
                ),
                _kpi("horas", "Horas registradas", _clean_number(total_hours), "number"),
                _kpi(
                    "utilizacion",
                    "Utilización",
                    _clean_number(billable_hours / total_hours * 100)
                    if total_hours
                    else None,
                    "percent",
                ),
            ],
            "charts": [
                {
                    "id": "utilidad_tecnico",
                    "kind": "bar",
                    "title": "Ingreso, costo y utilidad por técnico",
                    "help": "Montos calculados con la tarifa vigente en la fecha de cada registro.",
                    "category_key": "tecnico",
                    "orientation": "horizontal",
                    "series": [
                        {"key": "ingreso", "label": "Ingreso", "format": "currency"},
                        {"key": "costo", "label": "Costo", "format": "currency", "color_role": "cost"},
                        {"key": "utilidad", "label": "Utilidad", "format": "currency", "color_role": "profit"},
                    ],
                    "data": [
                        {
                            "tecnico": str(row[tech_left]),
                            "ingreso": _clean_number(row["ingreso"]),
                            "costo": _clean_number(row["costo"]),
                            "utilidad": _clean_number(row["utilidad"]),
                        }
                        for _, row in grouped.iterrows()
                    ],
                }
            ],
            "table": {
                "id": "tecnicos_tarifa",
                "title": "Rentabilidad por técnico",
                "columns": [
                    {"key": "tecnico", "label": "Técnico", "format": "text"},
                    {"key": "horas", "label": "Horas", "format": "number"},
                    {"key": "ingreso", "label": "Ingreso", "format": "currency"},
                    {"key": "costo", "label": "Costo", "format": "currency"},
                    {"key": "utilidad", "label": "Utilidad", "format": "currency"},
                ],
                "rows": [
                    {
                        "tecnico": str(row[tech_left]),
                        "horas": _clean_number(row["horas"]),
                        "ingreso": _clean_number(row["ingreso"]),
                        "costo": _clean_number(row["costo"]),
                        "utilidad": _clean_number(row["utilidad"]),
                    }
                    for _, row in grouped.iterrows()
                ],
                "total_rows": int(matched[tech_left].nunique()),
                "matched_rows": matched_rows,
                "unmatched_rows": rows_before - matched_rows,
            },
            "findings": [],
            "alerts": [],
            "actions": [],
            "available": True,
            "message": None,
        }

    if strategy == "periodo_moneda_uf":
        period_left = find_column(left.columns, "periodo")
        amount_col = find_column(left.columns, "monto")
        currency_col = find_column(left.columns, "moneda")
        period_right = find_column(right.columns, "periodo")
        uf_value = find_column(right.columns, "valor", "uf")
        if not all(
            (period_left, amount_col, currency_col, period_right, uf_value)
        ):
            return _empty_dashboard(
                relationship,
                "generic",
                currency,
                "Faltan columnas para convertir las cuotas en UF.",
            )
        work = left.copy()
        work["__period"] = (
            work[period_left].astype(str).str.replace("/", "-", regex=False).str[:7]
        )
        work["__amount"] = numeric_series(work, amount_col)
        work["__currency"] = (
            work[currency_col].astype(str).str.casefold().str.replace(".", "", regex=False).str.strip()
        )
        uf_rows = right.copy()
        uf_rows["__period"] = (
            uf_rows[period_right].astype(str).str.replace("/", "-", regex=False).str[:7]
        )
        uf_rows["__uf"] = numeric_series(uf_rows, uf_value)
        if uf_rows["__period"].duplicated().any():
            return _empty_dashboard(
                relationship,
                "generic",
                currency,
                "Valor_UF repite periodos y no puede usarse como referencia única.",
            )
        merged = work.merge(
            uf_rows[["__period", "__uf"]],
            on="__period",
            how="left",
            validate="many_to_one",
        )
        is_uf = merged["__currency"].eq("uf")
        converted_mask = is_uf & merged["__uf"].notna()
        merged["__clp"] = merged["__amount"].where(
            ~is_uf,
            merged["__amount"] * merged["__uf"],
        ).round()
        grouped = (
            merged.groupby("__period")
            .agg(
                cuotas=("__amount", "size"),
                ingreso_clp=("__clp", "sum"),
                cuotas_uf=("__currency", lambda values: int(values.eq("uf").sum())),
            )
            .reset_index()
            .sort_values("__period")
        )
        total = float(merged["__clp"].sum())
        uf_total = float(merged.loc[is_uf, "__clp"].sum())
        matched_rows = int(converted_mask.sum())
        relation_meta = {
            **relationship,
            "template": "generic",
            "label": f"{left_name} ↔ {right_name}",
            "purpose": "service_uf_period",
            "cardinality": "muchos_a_uno",
            "safe": True,
            "coverage_left": round(matched_rows / max(int(is_uf.sum()), 1), 4),
            "coverage_right": 1.0,
            "overlap": round(matched_rows / max(int(is_uf.sum()), 1), 4),
        }
        months = grouped["__period"].astype(str).tolist()
        return {
            "relation": relation_meta,
            "template": "generic",
            "period": {
                "desde": date_from,
                "hasta": date_to,
                "referencia": None,
                "meses": months,
            },
            "currency": "CLP",
            "quality": {
                "rows_before": len(work),
                "rows_after": len(work),
                "matched_rows": matched_rows,
                "unmatched_rows": int(is_uf.sum()) - matched_rows,
                "coverage_pct": round(matched_rows / max(int(is_uf.sum()), 1) * 100, 1),
                "warnings": [
                    "Valor UF es una referencia mensual: se multiplica por cada cuota en UF y nunca se suma como monto."
                ],
            },
            "kpis": [
                _kpi("ingreso_recurrente", "Ingreso recurrente", _clean_number(total), "currency"),
                _kpi("ingreso_uf", "Cuotas UF convertidas", _clean_number(uf_total), "currency"),
                _kpi("cuotas_uf", "Cuotas en UF", int(is_uf.sum()), "integer"),
                _kpi("periodos", "Periodos con UF", int(uf_rows["__period"].nunique()), "integer"),
            ],
            "charts": [
                {
                    "id": "cuotas_periodo",
                    "kind": "bar",
                    "title": "Ingreso recurrente convertido por periodo",
                    "help": "Cuotas CLP más cuotas UF convertidas con el valor del mismo periodo.",
                    "category_key": "periodo",
                    "series": [
                        {"key": "ingreso_clp", "label": "Ingreso CLP", "format": "currency"}
                    ],
                    "data": [
                        {
                            "periodo": str(row["__period"]),
                            "ingreso_clp": _clean_number(row["ingreso_clp"]),
                        }
                        for _, row in grouped.iterrows()
                    ],
                }
            ],
            "table": {
                "id": "cuotas_periodo",
                "title": "Cuotas por periodo",
                "columns": [
                    {"key": "periodo", "label": "Periodo", "format": "text"},
                    {"key": "cuotas", "label": "Cuotas", "format": "integer"},
                    {"key": "cuotas_uf", "label": "Cuotas UF", "format": "integer"},
                    {"key": "ingreso_clp", "label": "Ingreso CLP", "format": "currency"},
                ],
                "rows": [
                    {
                        "periodo": str(row["__period"]),
                        "cuotas": int(row["cuotas"]),
                        "cuotas_uf": int(row["cuotas_uf"]),
                        "ingreso_clp": _clean_number(row["ingreso_clp"]),
                    }
                    for _, row in grouped.iterrows()
                ],
                "total_rows": len(grouped),
                "matched_rows": matched_rows,
                "unmatched_rows": int(is_uf.sum()) - matched_rows,
            },
            "findings": [],
            "alerts": [],
            "actions": [],
            "available": True,
            "message": None,
        }

    if (
        strategy is None
        and _sheet_kind(left_name, left) == "ordenes_trabajo"
        and _sheet_kind(right_name, right) == "contratos"
    ):
        contract_left = find_column(left.columns, "cod", "contrato")
        response_col = (
            find_column(left.columns, "resp", "h")
            or find_column(left.columns, "hora", "respuesta")
        )
        contract_right = find_column(right.columns, "cod", "contrato")
        sla_col = find_column(right.columns, "sla")
        contract_type = find_column(right.columns, "tipo")
        if not all((contract_left, response_col, contract_right, sla_col)):
            return None
        if right[contract_right].map(_text_key).replace("", pd.NA).dropna().duplicated().any():
            return _empty_dashboard(
                relationship,
                "generic",
                currency,
                "Contratos repite claves y podría multiplicar órdenes.",
            )
        contract_columns = [
            contract_right,
            sla_col,
            *([contract_type] if contract_type else []),
        ]
        merged = left.merge(
            right[contract_columns],
            left_on=contract_left,
            right_on=contract_right,
            how="left",
            validate="many_to_one",
        )
        response_hours = pd.to_numeric(
            merged[response_col]
            .astype(str)
            .str.replace(",", ".", regex=False)
            .str.extract(r"([-+]?\d+(?:\.\d+)?)", expand=False),
            errors="coerce",
        )
        sla_hours = numeric_series(merged, sla_col)
        matched = merged[contract_right].notna()
        evaluable = matched & response_hours.notna() & sla_hours.notna()
        compliance = response_hours.le(sla_hours)
        compliance_pct = (
            float(compliance.loc[evaluable].mean() * 100)
            if evaluable.any()
            else None
        )
        grouped_rows: list[dict[str, Any]] = []
        if contract_type:
            grouped = pd.DataFrame(
                {
                    "tipo": merged[contract_type],
                    "evaluada": evaluable,
                    "cumple": compliance & evaluable,
                }
            ).loc[evaluable]
            if not grouped.empty:
                summary = grouped.groupby("tipo").agg(
                    ordenes=("evaluada", "size"),
                    cumplen=("cumple", "sum"),
                )
                summary["cumplimiento_pct"] = (
                    summary["cumplen"] / summary["ordenes"] * 100
                )
                grouped_rows = [
                    {
                        "tipo": str(index),
                        "ordenes": int(row["ordenes"]),
                        "cumplen": int(row["cumplen"]),
                        "cumplimiento_pct": _clean_number(row["cumplimiento_pct"]),
                    }
                    for index, row in summary.sort_values(
                        "ordenes", ascending=False
                    ).iterrows()
                ]
        matched_rows = int(matched.sum())
        relation_meta = {
            **relationship,
            "template": "generic",
            "label": f"{left_name} ↔ {right_name}",
            "purpose": "service_contract_sla",
            "cardinality": "muchos_a_uno",
            "safe": True,
            "coverage_left": round(matched_rows / max(len(left), 1), 4),
            "coverage_right": 1.0,
            "overlap": 1.0,
        }
        return {
            "relation": relation_meta,
            "template": "generic",
            "period": {
                "desde": date_from,
                "hasta": date_to,
                "referencia": None,
                "meses": [],
            },
            "currency": currency,
            "quality": {
                "rows_before": len(left),
                "rows_after": len(left),
                "matched_rows": matched_rows,
                "unmatched_rows": len(left) - matched_rows,
                "coverage_pct": round(matched_rows / max(len(left), 1) * 100, 1),
                "warnings": [
                    "La relación es opcional: las OT sin contrato se conservan y no participan del KPI de SLA."
                ],
            },
            "kpis": [
                _kpi("ot_contrato", "OT con contrato", matched_rows, "integer"),
                _kpi(
                    "cumplimiento_sla",
                    "Cumplimiento de SLA",
                    _clean_number(compliance_pct),
                    "percent",
                ),
                _kpi(
                    "respuesta_media",
                    "Respuesta media",
                    _clean_number(float(response_hours.loc[evaluable].mean()))
                    if evaluable.any()
                    else None,
                    "number",
                    help_text="Horas reales de respuesta en OT con SLA evaluable.",
                ),
                _kpi(
                    "ot_incumplen",
                    "OT que incumplen",
                    int((~compliance.loc[evaluable]).sum())
                    if evaluable.any()
                    else None,
                    "integer",
                    tone="risk",
                ),
            ],
            "charts": (
                [
                    {
                        "id": "sla_tipo_contrato",
                        "kind": "bar",
                        "title": "Cumplimiento de SLA por tipo de contrato",
                        "help": "Porcentaje de OT cuya respuesta real no supera el SLA.",
                        "category_key": "tipo",
                        "series": [
                            {
                                "key": "cumplimiento_pct",
                                "label": "Cumplimiento",
                                "format": "percent",
                            }
                        ],
                        "data": grouped_rows,
                    }
                ]
                if grouped_rows
                else []
            ),
            "table": (
                {
                    "id": "sla_tipo_contrato",
                    "title": "SLA por tipo de contrato",
                    "columns": [
                        {"key": "tipo", "label": "Tipo", "format": "text"},
                        {"key": "ordenes", "label": "OT", "format": "integer"},
                        {"key": "cumplen", "label": "Cumplen", "format": "integer"},
                        {
                            "key": "cumplimiento_pct",
                            "label": "Cumplimiento",
                            "format": "percent",
                        },
                    ],
                    "rows": grouped_rows,
                    "total_rows": len(grouped_rows),
                    "matched_rows": matched_rows,
                    "unmatched_rows": len(left) - matched_rows,
                }
                if grouped_rows
                else None
            ),
            "findings": [],
            "alerts": [],
            "actions": [],
            "available": True,
            "message": None,
        }
    return None


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
    append_sheets = list(dict.fromkeys(relationship.get("append_sheets") or []))
    left_keys = relationship.get("left_keys") or []
    right_keys = relationship.get("right_keys") or []
    currency = _currency_label(results, left_name) if left_name in results else "CLP"

    if (
        left_name not in frames
        or right_name not in frames
        or any(name not in frames for name in append_sheets)
    ):
        return _empty_dashboard(relationship, "generic", currency, "Las hojas de la relación no están disponibles.")

    if append_sheets:
        try:
            left, left_mapping, _ = append_compatible_frames(
                {name: frames[name] for name in append_sheets},
                mappings,
                allow_single=True,
            )
        except ValueError as exc:
            return _empty_dashboard(
                relationship,
                "generic",
                currency,
                f"Los periodos seleccionados no se pueden consolidar: {exc}",
            )
    else:
        left = frames[left_name]
        left_mapping = resolve_mapping([str(c) for c in left.columns], mappings.get(left_name))
    right = frames[right_name]
    right_mapping = resolve_mapping([str(c) for c in right.columns], mappings.get(right_name))
    template, label, purpose = classify_relationship_template(
        left_name, left, left_mapping, right_name, right, right_mapping
    )
    if purpose.startswith("ventas_") and date_from is None and date_to is None:
        declared_from, declared_to = _declared_sales_period(frames)
        if declared_from is not None and declared_to is not None:
            date_from = declared_from.date().isoformat()
            date_to = declared_to.date().isoformat()
    relation_meta = {
        **relationship,
        "template": template,
        "label": (
            f"Todas las ventas ↔ {right_name}"
            if append_sheets
            else label
        ),
        "purpose": purpose,
    }

    temporal_dashboard = _service_temporal_dashboard(
        left_name,
        left,
        right_name,
        right,
        relationship,
        currency,
        date_from,
        date_to,
    )
    if temporal_dashboard is not None:
        return temporal_dashboard

    # El inventario multi-snapshot se colapsa al último por clave para el JOIN
    # (así no multiplica ventas). El frame ORIGINAL se conserva para el stock.
    join_right = right
    if template == "sales_inventory":
        join_right = collapse_inventory_snapshots(right, keys=list(right_keys))

    if _sheet_kind(right_name, right) == "historial_costos" and purpose == "ventas_costos":
        product_key = (
            left_mapping.get("producto")
            or find_column(left.columns, "sku", "producto")
            or find_column(left.columns, "id", "producto")
        )
        date_column = left_mapping.get("fecha") or find_column(left.columns, "fecha")
        quantity_column = left_mapping.get("cantidad") or find_column(
            left.columns, "cantidad"
        )
        unit_cost, cost_source, _ = _applicable_unit_cost(
            left,
            product_key,
            _dates(left, date_column),
            None,
            None,
            None,
            right,
        )
        quantity = numeric_series(left, quantity_column)
        historical_cost = (quantity * unit_cost).where(
            quantity.notna() & unit_cost.notna() & cost_source.eq("historial_asof")
        )
        merged = left.copy()
        cost_column = "Costo_Venta_Historico"
        suffix = 2
        while cost_column in merged.columns:
            cost_column = f"Costo_Venta_Historico_{suffix}"
            suffix += 1
        merged[cost_column] = historical_cost
        merged_mapping = dict(left_mapping)
        merged_mapping["costo"] = cost_column
        matched_rows = int(historical_cost.notna().sum())
        provenance = {
            "mode": "asof",
            "left_sheet": left_name,
            "right_sheet": right_name,
            "rows_before": len(left),
            "rows_after": len(left),
            "filas_sin_correspondencia": int(len(left) - matched_rows),
            "coverage": round(matched_rows / max(len(left), 1), 4),
            "join_strategy": "vigencia_por_fecha",
        }
        relation_meta.update(
            {
                "cardinality": "muchos_a_uno_temporal",
                "coverage_left": provenance["coverage"],
                "coverage_right": 1.0,
                "overlap": provenance["coverage"],
                "safe": True,
            }
        )
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
            derived_cost=None,
            append_sheets=append_sheets,
        )
        return context.build()

    stats = relation_stats(left, list(left_keys), join_right, list(right_keys))
    relation_meta["cardinality"] = stats.cardinality
    relation_meta["coverage_left"] = stats.coverage_left
    relation_meta["coverage_right"] = stats.coverage_right
    relation_meta["overlap"] = stats.overlap
    relation_meta["safe"] = stats.safe
    if not stats.safe:
        return _empty_dashboard(
            relation_meta, template, currency, stats.reason or "La relación no es segura."
        )

    # Bloqueo de monedas incompatibles cuando la relación calcula costos.
    if purpose in {"ventas_costos", "compras_costos"}:
        currency_sheets = append_sheets or [left_name]
        detections = [
            results.get(sheet, {}).get("_moneda")
            for sheet in [*currency_sheets, right_name]
        ]
        typed_detections = [
            detection
            for detection in detections
            if isinstance(detection, CurrencyDetection)
        ]
        if typed_detections and (
            any(detection.mixta for detection in typed_detections)
            or len({detection.dominante for detection in typed_detections}) > 1
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
        append_sheets=append_sheets,
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
        self.append_sheets: list[str] = kwargs.get("append_sheets", [])

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
            left_label = (
                "las ventas consolidadas"
                if self.append_sheets
                else self.left_name
            )
            warnings.append(
                f"{unmatched:,} filas de {left_label} no encontraron correspondencia "
                f"en {self.right_name}.".replace(",", ".")
            )
        if self.derived_cost:
            non_positive = int(
                self.derived_cost.get("filas_costo_no_positivo", 0) or 0
            )
            extreme = int(self.derived_cost.get("filas_costo_extremo", 0) or 0)
            if non_positive:
                formatted_non_positive = f"{non_positive:,}".replace(",", ".")
                warnings.append(
                    f"{formatted_non_positive} costo(s) unitario(s) del maestro quedaron "
                    "fuera del cálculo porque eran cero o negativos."
                )
            if extreme:
                # No se excluyen del cálculo (son datos reales), solo se marcan
                # para revisión -- distinto de los no positivos, que sí se excluyen.
                formatted_extreme = f"{extreme:,}".replace(",", ".")
                warnings.append(
                    f"{formatted_extreme} costo(s) unitario(s) del maestro son extremos "
                    "(fuera del rango típico) pero se mantienen en el cálculo; "
                    "revísalos antes de certificar el resultado."
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
        base["pareada"] = base["ingresos"].notna() & base["costo"].notna()
        base["ingreso_pareado"] = base["ingresos"].where(base["pareada"])
        base["costo_pareado"] = base["costo"].where(base["pareada"])
        agg = base.groupby("clave").agg(
            nombre=("nombre", "first"),
            categoria=("categoria", "first"),
            ingresos=("ingresos", lambda values: values.sum(min_count=1)),
            unidades=("unidades", lambda values: values.sum(min_count=1)),
            ingreso_pareado=("ingreso_pareado", lambda values: values.sum(min_count=1)),
            costo_pareado=("costo_pareado", lambda values: values.sum(min_count=1)),
            filas=("pareada", "size"),
            filas_pareadas=("pareada", "sum"),
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
            utility_label = "Utilidad estimada" if self.derived_cost else "Utilidad"
            margin_label = "Margen estimado" if self.derived_cost else "Margen"
            columns.append(
                {"key": "ingresos_pareados", "label": "Ingresos con costo", "format": "currency"}
            )
            columns.append({"key": "cobertura", "label": "Cobertura", "format": "percent"})
            columns.append({"key": "utilidad", "label": utility_label, "format": "currency"})
            columns.append({"key": "margen", "label": margin_label, "format": "percent"})
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
                ingreso_pareado = row["ingreso_pareado"]
                costo = row["costo_pareado"]
                utilidad = (
                    ingreso_pareado - costo
                    if pd.notna(ingreso_pareado) and pd.notna(costo)
                    else None
                )
                entry["ingresos_pareados"] = _clean_number(ingreso_pareado)
                entry["cobertura"] = _clean_number(
                    row["filas_pareadas"] / row["filas"] * 100 if row["filas"] else None
                )
                entry["utilidad"] = _clean_number(utilidad)
                entry["margen"] = (
                    _clean_number(utilidad / ingreso_pareado * 100)
                    if utilidad is not None and ingreso_pareado
                    else None
                )
            rows.append(entry)
        return {
            "id": "productos",
            "title": (
                "Rentabilidad por producto con costo pareado"
                if with_margin and self.cost_col
                else "Detalle de productos"
            ),
            "columns": columns,
            "rows": rows,
            "total_rows": int(len(agg)),
            "matched_rows": int((agg["filas_pareadas"] > 0).sum())
            if with_margin and self.cost_col
            else None,
            "unmatched_rows": int((agg["filas_pareadas"] == 0).sum())
            if with_margin and self.cost_col
            else None,
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
        estimated = bool(self.derived_cost)
        kpis = [
            _kpi("ventas", "Ventas netas", _clean_number(totals["ingresos"]), "currency"),
            _kpi(
                "costo",
                "Costo de venta estimado" if estimated else "Costo de venta",
                _clean_number(margin["costo"]),
                "currency",
                help_text="Cantidad vendida × costo unitario válido del maestro actual."
                if estimated else None,
            ),
            _kpi("utilidad", "Utilidad bruta estimada" if estimated else "Utilidad bruta",
                 _clean_number(margin["utilidad"]), "currency",
                 tone="positive" if (margin["utilidad"] or 0) >= 0 else "risk"),
            _kpi("margen", "Margen bruto estimado" if estimated else "Margen bruto",
                 _clean_number(margin["margen"] * 100) if margin["margen"] is not None else None,
                 "percent", help_text="Utilidad bruta / ingresos pareados; usa el costo unitario actual."
                 if estimated else "Utilidad bruta / ingresos pareados."),
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
            "orientation": "horizontal",
            "title": "Top productos por utilidad bruta estimada"
            if self.derived_cost else "Top productos por utilidad bruta",
            "help": "Utilidad bruta estimada (ingreso − costo unitario actual × cantidad) por producto."
            if self.derived_cost else "Utilidad bruta (ingreso − costo pareado) por producto.",
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
        agg = agg.sort_values("ingresos", ascending=False).head(TOP_LIMIT)
        return {
            "id": "margen_categoria",
            "kind": "combo",
            "title": "Ventas, costos y margen estimado por categoría"
            if self.derived_cost else "Ventas, costos y margen por categoría",
            "help": "Compara ventas y costos estimados con el maestro actual; la línea usa el eje derecho para el margen."
            if self.derived_cost else "Compara ventas y costos pareados; la línea usa el eje derecho para el margen.",
            "category_key": "categoria",
            "series": [
                {
                    "key": "ingresos",
                    "label": "Ventas netas",
                    "format": "currency",
                    "kind": "bar",
                    "axis": "left",
                    "color_role": "primary",
                },
                {
                    "key": "costo",
                    "label": "Costo de venta",
                    "format": "currency",
                    "kind": "bar",
                    "axis": "left",
                    "color_role": "cost",
                },
                {
                    "key": "margen",
                    "label": "Margen bruto",
                    "format": "percent",
                    "kind": "line",
                    "axis": "right",
                    "color_role": "profit",
                },
            ],
            "note": "El margen se calcula solo sobre ventas con costo válido; las ventas sin costo o con costo inválido no se tratan como costo cero.",
            "data": [
                {
                    "categoria": str(index),
                    "ingresos": _clean_number(row["ingresos"]),
                    "costo": _clean_number(row["costo"]),
                    "margen": _clean_number(row["margen"]),
                }
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
            valid_snapshots = frame["_fecha"].dropna()
            if not valid_snapshots.empty:
                frame = frame.loc[frame["_fecha"].eq(valid_snapshots.max())]
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
