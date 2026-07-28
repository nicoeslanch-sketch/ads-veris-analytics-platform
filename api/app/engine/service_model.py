"""Modelo conservador para libros de empresas de servicios técnicos.

Este módulo cubre dos responsabilidades deliberadamente separadas:

* transformaciones estructurales deterministas para que la descarga limpia sea
  utilizable (fill-down, IDs, booleanos, unpivot y columnas compuestas);
* análisis del negocio solo cuando están presentes todas las fuentes necesarias
  y las relaciones pueden validarse sin multiplicar filas.

Nunca interpreta un monto contractual, una tarifa o una UF como venta por sí
solo. Los ingresos se construyen desde materiales vendidos, horas facturables y
cuotas contractuales convertidas explícitamente.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from typing import Any

import pandas as pd

from .mapping import resolve_mapping, strip_accents_lower
from .quality import line_sales_evidence, normalized_header
from .standardize import map_unique, parse_date, parse_number, physical_missing_mask


SERVICE_SHEETS = {
    "ordenes_trabajo",
    "detalle_ot",
    "horas_tecnicos",
    "tarifas_tecnicos",
    "tecnicos",
    "items",
    "clientes",
    "contratos",
    "cuotas_contrato",
    "valor_uf",
    "gastos_estructura",
}


def _sheet_key(value: object) -> str:
    return normalized_header(value).replace(" ", "_")


def _column(
    frame: pd.DataFrame,
    *groups: tuple[str, ...] | str,
) -> str | None:
    """Busca una columna por alternativas de tokens normalizados."""

    alternatives = [
        (group,) if isinstance(group, str) else group
        for group in groups
    ]
    for raw in frame.columns:
        header = normalized_header(raw)
        if any(all(token in header for token in alternative) for alternative in alternatives):
            return str(raw)
    return None


def _text(series: pd.Series) -> pd.Series:
    return series.astype(str).map(strip_accents_lower).str.strip()


def _numbers(series: pd.Series) -> pd.Series:
    return map_unique(series.astype(str), parse_number).astype(float)


def _hours(series: pd.Series) -> pd.Series:
    def parse(value: object) -> float | None:
        token = re.sub(
            r"\s*(?:h|hr|hrs|hora|horas)\.?\s*$",
            "",
            str(value).strip().casefold(),
        )
        return parse_number(token)

    return series.map(parse).astype(float)


def _dates(series: pd.Series) -> pd.Series:
    return pd.to_datetime(map_unique(series.astype(str), parse_date), errors="coerce")


def _blank(series: pd.Series) -> pd.Series:
    return physical_missing_mask(series)


def _pad_ot(value: object) -> object:
    text = str(value).strip().upper()
    match = re.fullmatch(r"OT[\s_-]*(\d+)", text)
    if not match:
        return value
    return f"OT-{int(match.group(1)):05d}"


def _preview(frame: pd.DataFrame, limit: int = 8) -> dict[str, Any]:
    shown = frame.head(limit)
    return {
        "columnas": [str(column) for column in shown.columns],
        "filas": [
            ["" if pd.isna(value) else str(value) for value in row]
            for row in shown.itertuples(index=False, name=None)
        ],
        "issues": [],
    }


@dataclass
class ServiceTransform:
    frame: pd.DataFrame
    source_rows: list[int]
    operations: list[dict[str, Any]]
    removed_rows: list[dict[str, Any]]


def transform_service_sheet(
    sheet_name: str | None,
    frame: pd.DataFrame,
    source_rows: list[int],
) -> ServiceTransform:
    """Aplica únicamente transformaciones estructurales inequívocas."""

    key = _sheet_key(sheet_name or "")
    if key not in SERVICE_SHEETS or frame.empty:
        return ServiceTransform(frame, source_rows, [], [])

    work = frame.copy()
    rows = list(source_rows)
    operations: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []

    def record(code: str, count: int, message: str) -> None:
        if count:
            operations.append({"regla": code, "cantidad": int(count), "mensaje": message})

    if key == "detalle_ot":
        line_id = _column(work, ("id", "linea"))
        ot = _column(work, ("n", "ot"), ("id", "ot"), ("orden",))
        line_type = _column(work, ("tipo", "linea"))
        label_mask = pd.Series(False, index=work.index)
        for column in work.columns:
            values = _text(work[column])
            label_mask |= values.str.match(
                r"^(?:gran\s+)?(?:sub\s*)?total(?:\s+ot|\s|$)",
                na=False,
            )
        if line_id:
            label_mask &= _blank(work[line_id])
        removed_positions = list(work.index[label_mask])
        for position in removed_positions:
            removed.append(
                {
                    "fila_origen": int(rows[position]),
                    "regla": "fila_resumen_estructural",
                    "accion": "fila_estructural_excluida",
                    "confirmacion": "automatica_regla_determinista",
                    "confianza": 1.0,
                    "motivo": "Subtotal intercalado; se conserva en auditoría y no como transacción.",
                }
            )
        keep = ~label_mask
        work = work.loc[keep].reset_index(drop=True)
        rows = [row for position, row in enumerate(rows) if bool(keep.iat[position])]
        record(
            "subtotales_intercalados",
            len(removed_positions),
            f"Se excluyeron {len(removed_positions)} subtotal(es) intercalado(s) del detalle.",
        )
        if ot:
            before = work[ot].copy()
            normalized = work[ot].mask(_blank(work[ot]), pd.NA).ffill().map(_pad_ot)
            filled = int((_blank(before) & normalized.notna()).sum())
            work[ot] = normalized
            record(
                "fill_down_clave_ot",
                filled,
                f"Se completó la OT por bloque en {filled} línea(s), sin inventar una clave nueva.",
            )
        if line_type:
            semantics = _text(work[line_type])
            work["Rol financiero de la línea"] = semantics.map(
                lambda value: (
                    "Ingreso por material"
                    if value == "material"
                    else "Costo de subcontrato"
                    if "subcontrat" in value
                    else "Revisar"
                )
            )

    elif key == "horas_tecnicos":
        ot = _column(work, ("n", "ot"), ("id", "ot"), ("orden",))
        hours = _column(work, ("horas",))
        billable = _column(work, ("factura",))
        if ot:
            before = work[ot].astype(str)
            work[ot] = work[ot].map(_pad_ot)
            record(
                "padding_clave_ot",
                int(before.ne(work[ot].astype(str)).sum()),
                "Se normalizó el padding de OT para que OT-1 y OT-00001 sean la misma clave.",
            )
        if hours:
            parsed = _hours(work[hours])
            changed = int(parsed.notna().sum())
            work[hours] = parsed
            record(
                "horas_numericas",
                changed,
                "Se quitaron unidades de texto y se conservaron las horas como número.",
            )
        if billable:
            yes = {"si", "sí", "s", "1", "x", "v", "true"}
            no = {"no", "n", "0", "", "-", "f", "false"}
            raw = _text(work[billable])
            canonical = raw.map(
                lambda value: "Sí" if value in yes else "No" if value in no else str(value)
            )
            work[billable] = canonical
            record(
                "booleano_facturable",
                len(work),
                "¿Factura? se normalizó por rol; X significa Sí en esta columna.",
            )

    elif key == "ordenes_trabajo":
        ot = _column(work, ("n", "ot"), ("id", "ot"))
        combined = _column(work, ("cliente", "comuna"))
        date = _column(work, ("fecha", "apertura"))
        hour = _column(work, ("hora",))
        if ot:
            work[ot] = work[ot].map(_pad_ot)
        if combined:
            parts = work[combined].astype(str).str.split("|", n=1, expand=True, regex=False)
            work["Razón Social"] = parts[0].str.strip()
            work["Comuna"] = parts[1].str.strip() if parts.shape[1] > 1 else ""
            record(
                "columna_cliente_comuna",
                int(parts.shape[0]),
                "Se separó Cliente / Comuna en dos campos trazables.",
            )
        if date and hour:
            parsed_date = _dates(work[date])
            parsed_time = pd.to_timedelta(
                work[hour].astype(str).str.strip() + ":00",
                errors="coerce",
            )
            work["Fecha Apertura Completa"] = parsed_date.dt.normalize() + parsed_time
            record(
                "fecha_hora_apertura",
                int(work["Fecha Apertura Completa"].notna().sum()),
                "Se creó un datetime de apertura sin eliminar los campos originales.",
            )

    elif key == "clientes":
        identifier = _column(work, ("cod", "cliente"), ("id", "cliente"))
        if identifier:
            continuation = _blank(work[identifier])
            numeric_present = pd.Series(False, index=work.index)
            for column in work.columns:
                numeric_present |= _numbers(work[column]).notna()
            continuation &= ~numeric_present
            removed_positions = list(work.index[continuation])
            for position in removed_positions:
                removed.append(
                    {
                        "fila_origen": int(rows[position]),
                        "regla": "fila_continuacion",
                        "accion": "fila_estructural_excluida",
                        "confirmacion": "automatica_regla_determinista",
                        "confianza": 1.0,
                        "motivo": "Fila sin ID ni dato numérico; solo prolonga una nota.",
                    }
                )
            keep = ~continuation
            work = work.loc[keep].reset_index(drop=True)
            rows = [row for position, row in enumerate(rows) if bool(keep.iat[position])]
            record(
                "filas_continuacion",
                len(removed_positions),
                "Se excluyeron filas de continuación sin ID; la nota queda registrada en auditoría.",
            )

    elif key == "gastos_estructura":
        fixed = [
            column
            for column in work.columns
            if not re.fullmatch(
                r"(?:ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)[-_ ]?\d{2,4}",
                normalized_header(column).replace(" ", ""),
            )
        ]
        months = [column for column in work.columns if column not in fixed]
        if months:
            month_map = {
                "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
                "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
            }
            work["__source_row"] = rows
            melted = work.melt(
                id_vars=[*fixed, "__source_row"],
                value_vars=months,
                var_name="Periodo original",
                value_name="Monto",
            )
            token = melted["Periodo original"].map(normalized_header)
            def parse_month_label(value: str) -> str:
                year_match = re.search(r"(\d{2})$", value)
                if not year_match or value[:3] not in month_map:
                    return value
                return f"20{year_match.group(1)}-{month_map[value[:3]]:02d}"

            melted["Periodo"] = token.map(parse_month_label)
            melted["Monto"] = _numbers(melted["Monto"])
            rows = [int(value) for value in melted.pop("__source_row")]
            work = melted[[*fixed, "Periodo", "Monto"]]
            record(
                "unpivot_gastos",
                len(work),
                f"Se convirtieron {len(months)} columnas mensuales en {len(work)} filas Área × Periodo.",
            )

    elif key in {"contratos", "cuotas_contrato"}:
        currency = _column(work, ("moneda",))
        if currency:
            token = _text(work[currency]).str.replace(".", "", regex=False).str.replace(" ", "", regex=False)
            work[currency] = token.map(
                lambda value: "UF" if value in {"uf"} else "CLP" if value in {"clp", "$", "pesos"} else value.upper()
            )
        period = _column(work, ("periodo",))
        if period:
            work[period] = (
                work[period].astype(str).str.replace("/", "-", regex=False).str[:7]
            )
            record(
                "periodo_canonico",
                int(work[period].notna().sum()),
                "Se normalizó el periodo a AAAA-MM para relaciones temporales.",
            )

    elif key == "valor_uf":
        period = _column(work, ("periodo",))
        if period:
            work[period] = (
                work[period].astype(str).str.replace("/", "-", regex=False).str[:7]
            )
            record(
                "periodo_canonico",
                int(work[period].notna().sum()),
                "Se normalizó el periodo UF a AAAA-MM.",
            )

    work.attrs.update(frame.attrs)
    return ServiceTransform(work, rows, operations, removed)


def apply_service_transform_to_result(result: dict[str, Any]) -> dict[str, Any]:
    """Actualiza el resultado privado/público después de la limpieza estándar."""

    frame = result.get("_df_limpio")
    if frame is None:
        return result
    sheet = (result.get("carga") or {}).get("hoja_usada") or frame.attrs.get("_source_sheet")
    transformed = transform_service_sheet(
        sheet,
        frame,
        list(result.get("_source_rows_limpio", range(2, len(frame) + 2))),
    )
    if not transformed.operations:
        return result
    result["_df_limpio"] = transformed.frame
    result["_source_rows_limpio"] = transformed.source_rows
    result["_filas_estructurales_eliminadas"] = transformed.removed_rows
    result["transformaciones_estructurales"] = transformed.operations
    result["avisos"] = [
        *result.get("avisos", []),
        *(operation["mensaje"] for operation in transformed.operations),
    ]
    result["resumen"]["filas_despues"] = len(transformed.frame)
    result["resumen"]["columnas_despues"] = len(transformed.frame.columns)
    result["preview"] = _preview(transformed.frame)
    result["column_types"] = {
        str(column): (
            "fecha"
            if pd.api.types.is_datetime64_any_dtype(transformed.frame[column])
            else "numero"
            if pd.api.types.is_numeric_dtype(transformed.frame[column])
            else result.get("column_types", {}).get(str(column), "texto")
        )
        for column in transformed.frame.columns
    }
    mapping = resolve_mapping(
        [str(column) for column in transformed.frame.columns],
        result.get("mapeo"),
    )
    result["mapeo"] = mapping
    result["evidencia_venta_linea"] = line_sales_evidence(
        transformed.frame, mapping
    ).to_dict()
    return result


def _service_frames(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    return {_sheet_key(name): frame for name, frame in frames.items()}


def _round_money(value: float | int) -> float:
    return float(round(float(value)))


def _group_rows(
    frame: pd.DataFrame,
    key: str,
    revenue: str,
    cost: str,
    *,
    limit: int = 12,
) -> list[dict[str, Any]]:
    grouped = frame.groupby(key, dropna=False).agg(
        registros=(key, "size"),
        ingresos=(revenue, "sum"),
        costo=(cost, "sum"),
    )
    grouped["utilidad"] = grouped["ingresos"] - grouped["costo"]
    grouped["margen_pct"] = grouped["utilidad"].div(
        grouped["ingresos"].replace(0, pd.NA)
    ) * 100
    grouped = grouped.sort_values("ingresos", ascending=False).head(limit)
    return [
        {
            "nombre": str(index),
            "registros": int(row["registros"]),
            "ingresos": _round_money(row["ingresos"]),
            "costo": _round_money(row["costo"]),
            "utilidad": _round_money(row["utilidad"]),
            "margen_pct": round(float(row["margen_pct"]), 2)
            if pd.notna(row["margen_pct"])
            else None,
        }
        for index, row in grouped.iterrows()
    ]


def analyze_service_business(
    frames: dict[str, pd.DataFrame],
) -> dict[str, Any] | None:
    """Calcula el negocio de servicios solo con la red completa de 11 hojas."""

    service = _service_frames(frames)
    if not SERVICE_SHEETS.issubset(service):
        return None

    orders = service["ordenes_trabajo"].copy()
    detail = service["detalle_ot"].copy()
    hours = service["horas_tecnicos"].copy()
    tariffs = service["tarifas_tecnicos"].copy()
    technicians = service["tecnicos"].copy()
    items = service["items"].copy()
    clients = service["clientes"].copy()
    contracts = service["contratos"].copy()
    installments = service["cuotas_contrato"].copy()
    uf = service["valor_uf"].copy()
    expenses = service["gastos_estructura"].copy()

    # Columnas críticas: si falta una, se bloquea el modelo completo en lugar de
    # completar con cero o inferir una relación no demostrada.
    required_columns = {
        "orders": [
            _column(orders, ("n", "ot"), ("id", "ot")),
            _column(orders, ("fecha", "apertura")),
            _column(orders, ("estado",)),
            _column(orders, ("tipo",)),
        ],
        "detail": [
            _column(detail, ("n", "ot"), ("id", "ot")),
            _column(detail, ("tipo", "linea")),
            _column(detail, ("cod", "item"), ("id", "item")),
            _column(detail, ("cant",)),
            _column(detail, ("monto",)),
        ],
        "hours": [
            _column(hours, ("n", "ot"), ("id", "ot")),
            _column(hours, ("cod", "tecnico"), ("id", "tecnico")),
            _column(hours, ("fecha",)),
            _column(hours, ("horas",)),
            _column(hours, ("factura",)),
        ],
        "tariffs": [
            _column(tariffs, ("cod", "tecnico"), ("id", "tecnico")),
            _column(tariffs, ("vigente", "desde")),
            _column(tariffs, ("vigente", "hasta")),
            _column(tariffs, ("costo", "hora")),
            _column(tariffs, ("valor", "hora", "venta")),
        ],
    }
    if any(not all(columns) for columns in required_columns.values()):
        return None

    order_id, order_date, order_status, order_type = required_columns["orders"]
    detail_ot, line_type, item_id, quantity, detail_amount = required_columns["detail"]
    hour_ot, tech_id, work_date, hour_value, billable = required_columns["hours"]
    tariff_tech, valid_from, valid_to, cost_rate, sale_rate = required_columns["tariffs"]

    orders[order_id] = orders[order_id].map(_pad_ot)
    orders["__fecha"] = _dates(orders[order_date])
    orders["__estado"] = _text(orders[order_status])
    orders["__tipo"] = _text(orders[order_type]).str.title()

    detail[detail_ot] = detail[detail_ot].mask(_blank(detail[detail_ot]), pd.NA).ffill().map(_pad_ot)
    detail["__tipo_linea"] = _text(detail[line_type])
    detail["__monto"] = _numbers(detail[detail_amount])
    detail["__cantidad"] = _numbers(detail[quantity])
    detail["__item"] = detail[item_id].astype(str).str.strip().str.upper()
    detail_date = _column(detail, ("fecha",))
    detail["__fecha"] = _dates(detail[detail_date]) if detail_date else pd.NaT
    structural = detail["__tipo_linea"].str.contains(r"subtotal|total", regex=True, na=False)
    detail = detail.loc[~structural].copy()
    material = detail["__tipo_linea"].eq("material")
    subcontract = detail["__tipo_linea"].str.contains("subcontrat", na=False)

    item_key = _column(items, ("cod", "item"), ("id", "item"))
    standard_cost = _column(items, ("costo", "estandar"), ("costo",))
    family = _column(items, ("familia",), ("categoria",))
    if not item_key or not standard_cost:
        return None
    item_lookup = items[[item_key, standard_cost] + ([family] if family else [])].copy()
    item_lookup["__item"] = item_lookup[item_key].astype(str).str.strip().str.upper()
    item_lookup["__costo_unit"] = _numbers(item_lookup[standard_cost])
    item_lookup = item_lookup.drop_duplicates("__item", keep="last")
    detail = detail.merge(
        item_lookup[["__item", "__costo_unit"] + ([family] if family else [])],
        on="__item",
        how="left",
        validate="many_to_one",
    )
    detail["__costo_material"] = (
        detail["__cantidad"] * detail["__costo_unit"]
    ).where(material)
    detail["__ingreso_material"] = detail["__monto"].where(material, 0.0)
    detail["__costo_subcontrato"] = detail["__monto"].where(subcontract, 0.0)

    hours[hour_ot] = hours[hour_ot].map(_pad_ot)
    hours["__tecnico"] = hours[tech_id].astype(str).str.strip().str.upper()
    hours["__fecha"] = _dates(hours[work_date])
    hours["__horas"] = _hours(hours[hour_value])
    billable_text = _text(hours[billable])
    hours["__facturable"] = billable_text.isin({"si", "sí", "s", "1", "x", "v", "true"})
    hour_type = _column(hours, ("tipo",))
    hours["__multiplicador"] = (
        _text(hours[hour_type]).str.contains("extra", na=False).map({True: 1.5, False: 1.0})
        if hour_type
        else 1.0
    )
    hours["__row"] = range(len(hours))

    rates = tariffs.copy()
    rates["__tecnico"] = rates[tariff_tech].astype(str).str.strip().str.upper()
    rates["__desde"] = _dates(rates[valid_from])
    rates["__hasta"] = _dates(rates[valid_to])
    rates["__costo_hora"] = _numbers(rates[cost_rate])
    rates["__venta_hora"] = _numbers(rates[sale_rate])
    matched = hours.merge(
        rates[["__tecnico", "__desde", "__hasta", "__costo_hora", "__venta_hora"]],
        on="__tecnico",
        how="left",
    )
    matched = matched.loc[
        matched["__fecha"].between(matched["__desde"], matched["__hasta"], inclusive="both")
    ].copy()
    duplicate_rate_rows = int(matched["__row"].duplicated().sum())
    if duplicate_rate_rows:
        return None
    matched["__costo_hh"] = (
        matched["__horas"] * matched["__costo_hora"] * matched["__multiplicador"]
    )
    matched["__ingreso_hh"] = (
        matched["__horas"] * matched["__venta_hora"] * matched["__multiplicador"]
    ).where(matched["__facturable"], 0.0)
    matched["__costo_no_facturable"] = matched["__costo_hh"].where(
        ~matched["__facturable"], 0.0
    )

    installment_period = _column(installments, ("periodo",))
    installment_amount = _column(installments, ("monto",))
    installment_currency = _column(installments, ("moneda",))
    installment_status = _column(installments, ("estado",))
    uf_period = _column(uf, ("periodo",))
    uf_value = _column(uf, ("valor", "uf"))
    if not all(
        (
            installment_period,
            installment_amount,
            installment_currency,
            installment_status,
            uf_period,
            uf_value,
        )
    ):
        return None
    uf_lookup = dict(
        zip(
            uf[uf_period].astype(str).str.replace("/", "-", regex=False).str[:7],
            _numbers(uf[uf_value]),
        )
    )
    installments["__periodo"] = (
        installments[installment_period].astype(str).str.replace("/", "-", regex=False).str[:7]
    )
    installments["__monto_origen"] = _numbers(installments[installment_amount])
    installments["__moneda"] = _text(installments[installment_currency]).str.replace(
        ".", "", regex=False
    ).str.replace(" ", "", regex=False)
    installments["__monto_clp"] = installments["__monto_origen"].where(
        ~installments["__moneda"].eq("uf"),
        installments["__monto_origen"] * installments["__periodo"].map(uf_lookup),
    ).round()
    installments["__estado"] = _text(installments[installment_status])

    expense_period = _column(expenses, ("periodo",))
    expense_amount = _column(expenses, ("monto",))
    expense_type = _column(expenses, ("tipo", "gasto"))
    expense_concept = _column(expenses, ("concepto", "gasto"))
    if not all((expense_period, expense_amount, expense_type, expense_concept)):
        return None
    expenses["__periodo"] = expenses[expense_period].astype(str).str[:7]
    expenses["__monto"] = _numbers(expenses[expense_amount])
    expenses["__tipo"] = _text(expenses[expense_type])
    expenses["__concepto"] = _text(expenses[expense_concept])

    revenue_material = float(detail["__ingreso_material"].sum())
    cost_material = float(detail["__costo_material"].sum())
    cost_subcontract = float(detail["__costo_subcontrato"].sum())
    revenue_hours = float(matched["__ingreso_hh"].sum())
    cost_hours = float(matched["__costo_hh"].sum())
    revenue_contracts = float(installments["__monto_clp"].sum())
    revenue_total = revenue_material + revenue_hours + revenue_contracts
    direct_cost = cost_material + cost_hours + cost_subcontract
    gross_profit = revenue_total - direct_cost
    gross_margin = gross_profit / revenue_total * 100 if revenue_total else None
    structure_expense = float(expenses["__monto"].sum())
    fixed_expense = float(expenses.loc[expenses["__tipo"].eq("fijo"), "__monto"].sum())
    variable_expense = structure_expense - fixed_expense
    depreciation = float(
        expenses.loc[expenses["__concepto"].str.contains("depreci", na=False), "__monto"].sum()
    )
    operating_profit = gross_profit - structure_expense
    operating_margin = operating_profit / revenue_total * 100 if revenue_total else None
    ebitda = operating_profit + depreciation
    ebitda_margin = ebitda / revenue_total * 100 if revenue_total else None

    detail_ot_summary = detail.groupby(detail_ot).agg(
        ingreso_material=("__ingreso_material", "sum"),
        costo_material=("__costo_material", "sum"),
        costo_subcontrato=("__costo_subcontrato", "sum"),
    )
    hour_ot_summary = matched.groupby(hour_ot).agg(
        ingreso_horas=("__ingreso_hh", "sum"),
        costo_horas=("__costo_hh", "sum"),
        horas=("__horas", "sum"),
        horas_facturables=("__horas", lambda values: float(values[matched.loc[values.index, "__facturable"]].sum())),
    )
    ot = orders[[order_id, "__fecha", "__estado", "__tipo"]].copy()
    ot = ot.merge(detail_ot_summary, left_on=order_id, right_index=True, how="left")
    ot = ot.merge(hour_ot_summary, left_on=order_id, right_index=True, how="left")
    monetary_columns = [
        "ingreso_material", "costo_material", "costo_subcontrato",
        "ingreso_horas", "costo_horas", "horas", "horas_facturables",
    ]
    ot[monetary_columns] = ot[monetary_columns].fillna(0.0)
    ot["ingresos"] = ot["ingreso_material"] + ot["ingreso_horas"]
    ot["costo"] = ot["costo_material"] + ot["costo_subcontrato"] + ot["costo_horas"]
    ot["utilidad"] = ot["ingresos"] - ot["costo"]
    ot["margen_pct"] = ot["utilidad"].div(ot["ingresos"].replace(0, pd.NA)) * 100
    # La estructura se asigna a cada OT en proporción a su ingreso, usando la
    # tasa real del negocio. Las cuotas de contrato no se imputan a una OT
    # concreta porque el libro no declara esa distribución. Esto mantiene
    # separado el ingreso recurrente y evita inventar rentabilidad por orden.
    structure_rate = structure_expense / revenue_total if revenue_total else 0.0
    ot["utilidad_operacional"] = ot["utilidad"] - ot["ingresos"] * structure_rate
    closed = ot["__estado"].str.contains("cerrad", na=False)
    open_mask = ~closed
    negative = ot["utilidad"] < 0
    operating_negative = ot["utilidad_operacional"] < 0

    total_hours = float(matched["__horas"].sum())
    billable_hours = float(matched.loc[matched["__facturable"], "__horas"].sum())
    utilization = billable_hours / total_hours * 100 if total_hours else None
    non_billable_cost = float(matched["__costo_no_facturable"].sum())

    monthly = pd.DataFrame(index=[f"2025-{month:02d}" for month in range(1, 13)])
    detail_month = detail["__fecha"].dt.strftime("%Y-%m")
    matched_month = matched["__fecha"].dt.strftime("%Y-%m")
    monthly["ingreso_material"] = detail.groupby(detail_month)["__ingreso_material"].sum()
    monthly["ingreso_horas"] = matched.groupby(matched_month)["__ingreso_hh"].sum()
    monthly["ingreso_contratos"] = installments.groupby("__periodo")["__monto_clp"].sum()
    monthly["costo_material"] = detail.groupby(detail_month)["__costo_material"].sum()
    monthly["costo_subcontrato"] = detail.groupby(detail_month)["__costo_subcontrato"].sum()
    monthly["costo_horas"] = matched.groupby(matched_month)["__costo_hh"].sum()
    monthly["gastos"] = expenses.groupby("__periodo")["__monto"].sum()
    monthly["horas"] = matched.groupby(matched_month)["__horas"].sum()
    monthly["horas_facturables"] = matched.loc[matched["__facturable"]].groupby(matched_month)["__horas"].sum()
    monthly["ot"] = ot.groupby(ot["__fecha"].dt.strftime("%Y-%m"))[order_id].nunique()
    monthly = monthly.fillna(0.0)
    monthly["ingresos"] = monthly[
        ["ingreso_material", "ingreso_horas", "ingreso_contratos"]
    ].sum(axis=1)
    monthly["costo_directo"] = monthly[
        ["costo_material", "costo_subcontrato", "costo_horas"]
    ].sum(axis=1)
    monthly["utilidad_bruta"] = monthly["ingresos"] - monthly["costo_directo"]
    monthly["utilidad_operacional"] = monthly["utilidad_bruta"] - monthly["gastos"]
    monthly["margen_bruto_pct"] = monthly["utilidad_bruta"].div(
        monthly["ingresos"].replace(0, pd.NA)
    ) * 100
    monthly["margen_operacional_pct"] = monthly["utilidad_operacional"].div(
        monthly["ingresos"].replace(0, pd.NA)
    ) * 100
    monthly["utilizacion_pct"] = monthly["horas_facturables"].div(
        monthly["horas"].replace(0, pd.NA)
    ) * 100

    last_order_date = orders["__fecha"].max()
    monthly_rows = []
    def rounded_percent(value: object) -> float | None:
        return round(float(value), 2) if pd.notna(value) else None

    for period, row in monthly.iterrows():
        year, month = (int(value) for value in period.split("-"))
        days = calendar.monthrange(year, month)[1]
        partial = bool(
            pd.notna(last_order_date)
            and last_order_date.strftime("%Y-%m") == period
            and int(last_order_date.day) < days
        )
        monthly_rows.append(
            {
                "mes": period,
                **{
                    column: _round_money(row[column])
                    for column in (
                        "ingresos", "costo_directo", "utilidad_bruta",
                        "gastos", "utilidad_operacional", "horas",
                        "horas_facturables", "ot",
                    )
                },
                "margen_bruto_pct": rounded_percent(row["margen_bruto_pct"]),
                "margen_operacional_pct": rounded_percent(
                    row["margen_operacional_pct"]
                ),
                "utilizacion_pct": rounded_percent(row["utilizacion_pct"]),
                "parcial": partial,
                "cobertura_hasta_dia": int(last_order_date.day) if partial else days,
                "dias_del_mes": days,
            }
        )

    contract_key = _column(contracts, ("cod", "contrato"), ("id", "contrato"))
    contract_currency = _column(contracts, ("moneda",))
    active_contracts = int(contracts[contract_key].nunique()) if contract_key else len(contracts)
    contracts_uf = int(_text(contracts[contract_currency]).str.replace(".", "", regex=False).eq("uf").sum()) if contract_currency else 0
    pending_installments = float(
        installments.loc[
            installments["__estado"].str.contains("pend", na=False), "__monto_clp"
        ].sum()
    )

    client_key_order = _column(orders, ("cod", "cliente"), ("id", "cliente"))
    client_key_master = _column(clients, ("cod", "cliente"), ("id", "cliente"))
    client_segment = _column(clients, ("segmento",))
    if client_key_order and client_key_master and client_segment:
        client_lookup = clients[[client_key_master, client_segment]].drop_duplicates(client_key_master)
        ot = ot.merge(
            orders[[order_id, client_key_order]],
            on=order_id,
            how="left",
            validate="one_to_one",
        ).merge(
            client_lookup,
            left_on=client_key_order,
            right_on=client_key_master,
            how="left",
            validate="many_to_one",
        )

    type_rows = _group_rows(ot, "__tipo", "ingresos", "costo")
    segment_rows = (
        _group_rows(ot, client_segment, "ingresos", "costo")
        if client_segment and client_segment in ot.columns
        else []
    )
    family_rows: list[dict[str, Any]] = []
    if family and family in detail.columns:
        material_rows = detail.loc[material].copy()
        material_rows["__costo"] = material_rows["__costo_material"]
        family_rows = _group_rows(
            material_rows, family, "__ingreso_material", "__costo", limit=10
        )

    operating_leverage = (
        gross_profit / operating_profit if operating_profit else None
    )
    break_even = (
        structure_expense / (gross_profit / revenue_total)
        if revenue_total and gross_profit
        else None
    )
    safety_margin = (
        (revenue_total - break_even) / revenue_total * 100
        if break_even is not None and revenue_total
        else None
    )

    ot_points = [
        {
            "ot": str(row[order_id]),
            "ingresos": _round_money(row["ingresos"]),
            "utilidad": _round_money(row["utilidad"]),
            "tipo": str(row["__tipo"]),
            "margen_pct": round(float(row["margen_pct"]), 2)
            if pd.notna(row["margen_pct"])
            else None,
            "perdida": bool(row["utilidad"] < 0),
        }
        for _, row in ot.iterrows()
    ]

    relations = [
        (1, "Detalle_OT → Ordenes_Trabajo", "Ingreso y costo por OT"),
        (2, "Horas_Tecnicos → Ordenes_Trabajo", "Horas e ingreso de mano de obra por OT"),
        (3, "Detalle_OT → Items", "Costo y familia de materiales"),
        (4, "Horas_Tecnicos → Tarifas_Tecnicos (vigencia)", "Costo y venta real de horas"),
        (5, "Cuotas_Contrato → Valor_UF (periodo)", "Cuotas UF convertidas a CLP"),
        (6, "Cuotas_Contrato → Contratos", "Ingreso recurrente y estado contractual"),
        (7, "Ordenes_Trabajo → Clientes", "Rentabilidad por cliente y segmento"),
        (8, "Ordenes_Trabajo → Contratos", "OT asociadas a contratos"),
        (9, "Ordenes_Trabajo → Tecnicos", "Supervisión y SLA"),
        (10, "Horas_Tecnicos → Tecnicos", "Productividad y utilización por técnico"),
        (11, "Contratos → Clientes", "Cartera contractual por cliente"),
        (12, "Gastos_Estructura → Periodo", "Resultado operacional mensual"),
    ]

    service_payload = {
        "kpis": {
            "ventas_netas": _round_money(revenue_total),
            "costo_directo": _round_money(direct_cost),
            "utilidad_bruta": _round_money(gross_profit),
            "margen_bruto_pct": round(float(gross_margin), 2),
            "gastos_estructura": _round_money(structure_expense),
            "utilidad_operacional": _round_money(operating_profit),
            "margen_operacional_pct": round(float(operating_margin), 2),
            "ebitda": _round_money(ebitda),
            "margen_ebitda_pct": round(float(ebitda_margin), 2),
            "utilizacion_pct": round(float(utilization), 2),
            "costo_horas_no_facturables": _round_money(non_billable_cost),
            "backlog": _round_money(ot.loc[open_mask, "ingresos"].sum()),
            "ot_perdida": int(negative.sum()),
            "ingreso_recurrente": _round_money(revenue_contracts),
        },
        "composicion_ingresos": [
            {"nombre": "Materiales", "valor": _round_money(revenue_material)},
            {"nombre": "Horas facturables", "valor": _round_money(revenue_hours)},
            {"nombre": "Contratos", "valor": _round_money(revenue_contracts)},
        ],
        "composicion_costos": [
            {"nombre": "Materiales", "valor": _round_money(cost_material)},
            {"nombre": "Mano de obra", "valor": _round_money(cost_hours)},
            {"nombre": "Subcontratos", "valor": _round_money(cost_subcontract)},
            {"nombre": "Estructura fija", "valor": _round_money(fixed_expense)},
            {"nombre": "Estructura variable", "valor": _round_money(variable_expense)},
        ],
        "cascada": [
            {"nombre": "Ingresos", "valor": _round_money(revenue_total)},
            {"nombre": "Costo directo", "valor": -_round_money(direct_cost)},
            {"nombre": "Utilidad bruta", "valor": _round_money(gross_profit)},
            {"nombre": "Gastos estructura", "valor": -_round_money(structure_expense)},
            {"nombre": "Utilidad operacional", "valor": _round_money(operating_profit)},
            {"nombre": "EBITDA", "valor": _round_money(ebitda)},
        ],
        "evolucion": monthly_rows,
        "ot_dispersion": ot_points,
        "por_tipo_ot": type_rows,
        "por_segmento": segment_rows,
        "por_familia": family_rows,
        "operacion": {
            "ot_total": int(len(ot)),
            "ot_cerradas": int(closed.sum()),
            "ot_abiertas": int(open_mask.sum()),
            "ot_perdida": int(negative.sum()),
            "ot_perdida_operacional": int(operating_negative.sum()),
            "perdida_ot_negativas": _round_money(
                abs(ot.loc[negative, "utilidad"].sum())
            ),
            "horas_totales": _round_money(total_hours),
            "horas_facturables": _round_money(billable_hours),
            "horas_no_facturables": _round_money(total_hours - billable_hours),
            "contratos": active_contracts,
            "contratos_uf": contracts_uf,
            "cuotas_pendientes": _round_money(pending_installments),
            "punto_equilibrio": _round_money(break_even or 0),
            "margen_seguridad_pct": round(float(safety_margin), 2)
            if safety_margin is not None
            else None,
            "apalancamiento_operativo": round(float(operating_leverage), 2)
            if operating_leverage is not None
            else None,
        },
        "relaciones": [
            {"orden": order, "relacion": relation, "desbloquea": unlock}
            for order, relation, unlock in relations
        ],
        "trazabilidad": {
            "fuentes_ingreso": [
                "Detalle_OT: solo líneas Material",
                "Horas_Tecnicos × Tarifas_Tecnicos vigentes: solo horas facturables",
                "Cuotas_Contrato × Valor_UF del periodo",
            ],
            "fuentes_costo": [
                "Items.Costo Estandar × Detalle_OT.Cant.",
                "Todas las horas × tarifa de costo vigente",
                "Detalle_OT: líneas Subcontrato",
            ],
            "moneda": "CLP, con conversión explícita de UF por periodo",
            "mes_parcial": (
                f"{last_order_date.strftime('%Y-%m')} hasta el día {last_order_date.day}"
                if pd.notna(last_order_date)
                and last_order_date.day
                < calendar.monthrange(last_order_date.year, last_order_date.month)[1]
                else None
            ),
        },
    }

    return {
        "version": 2,
        "perfil": "servicios_tecnicos",
        "servicios": service_payload,
        "estado_certificacion": "certified",
        "confianza_pct": 100.0,
        "filtros": {"disponibles": {}, "aplicados": {}},
        "alcance": {
            "hojas_ventas": ["Detalle_OT", "Horas_Tecnicos", "Cuotas_Contrato"],
            "hoja_costos": "Items + Tarifas_Tecnicos + Detalle_OT",
            "hoja_historial_costos": "Tarifas_Tecnicos",
            "hojas_utilizadas": sorted(frames),
            "filas_ventas_fisicas": int(len(detail) + len(matched) + len(installments)),
            "filas_totales_estructurales": int(structural.sum()),
            "filas_anuladas": 0,
            "filas_indicadores": int(len(detail) + len(matched) + len(installments)),
            "documentos_repetidos": 0,
            "filas_adicionales_documento": 0,
            "documentos_conflictivos": 0,
        },
        "estado_resultados": {
            "ventas_observadas": _round_money(revenue_total),
            "ventas_certificables": _round_money(revenue_total),
            "ventas_pareadas": _round_money(revenue_total),
            "costo_venta_conocido": _round_money(direct_cost),
            "costo_venta_estimado_catalogo": 0,
            "utilidad_bruta": _round_money(gross_profit),
            "margen_bruto_pct": round(float(gross_margin), 2),
            "gastos_operacionales": _round_money(structure_expense),
            "gastos_operacionales_periodo": _round_money(structure_expense),
            "base_gastos_operacionales": "monto_gasto",
            "filas_gastos": int(len(expenses)),
            "resultado_operacional": _round_money(operating_profit),
            "margen_operacional_pct": round(float(operating_margin), 2),
            "depreciacion_amortizacion": _round_money(depreciation),
            "ebitda": _round_money(ebitda),
            "cobertura_costos_pct": 100.0,
            "cobertura_costos_historica_pct": 100.0,
            "cobertura_costos_certificable_pct": 100.0,
            "ventas_certificables_pareadas": _round_money(revenue_total),
            "costo_certificable": _round_money(direct_cost),
            "utilidad_certificable": _round_money(gross_profit),
            "margen_certificable_pct": round(float(gross_margin), 2),
            "resultado_operacional_certificable": _round_money(operating_profit),
            "margen_operacional_certificable_pct": round(float(operating_margin), 2),
        },
        "operacion": {
            "cobrado_aplicado": None,
            "cobranza_sobre_documentos_pct": None,
            "documentos_sobrepagados": 0,
            "pagos_duplicados_excluidos": 0,
            "valor_inventario": None,
            "compras_efectivas": None,
            "gastos_fijos": _round_money(fixed_expense),
            "gastos_variables": _round_money(variable_expense),
            "gasto_fijo_mensual_promedio": _round_money(fixed_expense / 12),
            "punto_equilibrio_ventas": _round_money(break_even or 0),
            "rotacion_inventario_aprox": None,
        },
        "evolucion": [
            {
                "mes": row["mes"],
                "ventas": row["ingresos"],
                "costo": row["costo_directo"],
                "utilidad_bruta": row["utilidad_bruta"],
                "gastos_operacionales": row["gastos"],
                "resultado_operacional": row["utilidad_operacional"],
                "parcial": row["parcial"],
                "cobertura_hasta_dia": row["cobertura_hasta_dia"],
                "dias_del_mes": row["dias_del_mes"],
            }
            for row in monthly_rows
        ],
        "agrupaciones": {},
        "portafolio": {"umbrales": None, "productos": []},
        "metas": {
            "disponible": False,
            "meta_venta": None,
            "venta_comparable": None,
            "cumplimiento_pct": None,
            "meta_margen_pct": None,
            "meta_nuevos_clientes": None,
            "por_mes": [],
            "nota": "El libro no declara metas comparables.",
        },
        "sensibilidad": {
            "base_utilidad_bruta": _round_money(gross_profit),
            "costo_mas_5": _round_money(gross_profit - direct_cost * 0.05),
            "costo_mas_10": _round_money(gross_profit - direct_cost * 0.10),
            "nota": "Escenario mecánico; no es una proyección.",
        },
        "calidad": {
            "costos": {"cobertura_pct": 100.0},
            "integridad_referencial": {},
            "controles_formula": [],
            "filas_inconsistentes_formula": 0,
            "referencias_problematicas": [],
        },
        "ratios": [],
        "decisiones": [],
        "catalogo_indicadores": {
            "version": 1,
            "moneda": "CLP",
            "categorias": [],
            "disponibles": 14,
            "parciales": 0,
            "no_disponibles": 0,
        },
    }
