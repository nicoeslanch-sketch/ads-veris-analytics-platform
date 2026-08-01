"""Safe multi-sheet business analysis for small and medium businesses.

The module keeps every grain separate and only performs many-to-one lookups or
explicit pre-aggregations. It never joins raw collections, cost history or
inventory directly to sales, which prevents accidental row multiplication.
"""

from __future__ import annotations

from collections import defaultdict
import re
from typing import Any

import pandas as pd

from .mapping import strip_accents_lower
from .multi_sheet import append_compatible_frames
from .quality import (
    find_column,
    formula_mismatch,
    line_sales_evidence,
    normalized_header,
    numeric_series,
    structural_total_mask,
)
from .standardize import map_unique, parse_date, physical_missing_mask
from .service_model import analyze_service_business

BUSINESS_FILTER_KEYS = (
    "sucursal",
    "canal",
    "vendedor",
    "categoria",
    "producto",
    "moneda",
    "periodo_cotizado",
    "equipo",
    "subgrupo",
    "agencia_pago",
    "forma_pago",
)


def _text_key(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = " ".join(strip_accents_lower(str(value)).split())
    code = re.fullmatch(r"([a-z][a-z0-9 ._/-]*?[-_/ ]?)(0*\d+)", text)
    if code:
        text = f"{code.group(1)}{int(code.group(2))}"
    period = re.fullmatch(r"(\d{4})[-/](\d{1,2})", text)
    if period and 1 <= int(period.group(2)) <= 12:
        text = f"{period.group(1)}-{int(period.group(2)):02d}"
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


def _declared_sales_period(
    frames: dict[str, pd.DataFrame],
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """Read an explicit sales period from a parameter sheet when available."""

    for name, frame in frames.items():
        if "parametr" not in normalized_header(name) or frame.empty:
            continue
        label_column = find_column(frame.columns, "parametro") or str(frame.columns[0])
        value_column = find_column(frame.columns, "valor") or (
            str(frame.columns[1]) if len(frame.columns) > 1 else None
        )
        if not value_column:
            continue
        labels = frame[label_column].astype(str).map(strip_accents_lower)
        matches = frame.loc[labels.str.contains(r"periodo\s+ventas?", regex=True, na=False)]
        for raw_value in matches[value_column]:
            tokens = re.findall(r"\d{1,4}[-/]\d{1,2}[-/]\d{1,4}", str(raw_value))
            if len(tokens) < 2:
                continue
            parsed = [
                pd.to_datetime(parse_date(token), errors="coerce", dayfirst=True)
                for token in tokens[:2]
            ]
            if all(pd.notna(value) for value in parsed):
                start, end = sorted(parsed)
                return start.normalize(), end.normalize()
    return None, None


def _sheet_kind(name: str, frame: pd.DataFrame) -> str:
    sheet = normalized_header(name)
    sheet_tokens = set(sheet.split())
    headers = " | ".join(normalized_header(column) for column in frame.columns)
    # A line-level commercial formula is stronger evidence than the sheet
    # name. This allows Detalle_OT to be sales when MONTO reconciles with
    # quantity, selling price and discount, while tariffs/contracts/UF remain
    # operational because they cannot satisfy the same joint evidence.
    if line_sales_evidence(frame).confirmed:
        return "ventas"
    # Dominios operacionales de servicios. Deben resolverse antes de buscar
    # palabras monetarias: MONTO, tarifa o valor no convierten una OT en venta.
    if "detalle ot" in sheet or (
        ("n ot" in headers or "numero ot" in headers)
        and "tipo linea" in headers
    ):
        return "detalle_ot"
    if "horas tecnicos" in sheet or (
        ("n ot" in headers or "numero ot" in headers)
        and "cod tecnico" in headers
        and "horas" in headers
    ):
        return "horas_tecnicos"
    if "tarifas tecnicos" in sheet or (
        "cod tecnico" in headers
        and "valor hora venta" in headers
        and "costo hora" in headers
    ):
        return "tarifas_tecnicos"
    if "ordenes trabajo" in sheet or (
        ("n ot" in headers or "numero ot" in headers)
        and "estado" in headers
        and "cod cliente" in headers
    ):
        return "ordenes_trabajo"
    if "cuotas contrato" in sheet or (
        "cod contrato" in headers and "periodo" in headers and "moneda" in headers
    ):
        return "cuotas_contrato"
    if sheet == "contratos" or (
        "cod contrato" in headers and "monto mensual" in headers
    ):
        return "contratos"
    if "valor uf" in sheet or ("valor uf" in headers and "periodo" in headers):
        return "valor_uf"
    if sheet == "items" or (
        "cod item" in headers and ("descripcion" in headers or "unidad" in headers)
    ):
        return "items"
    if sheet == "tecnicos" or (
        "cod tecnico" in headers and "nombre tecnico" in headers
    ):
        return "tecnicos"
    if sheet_tokens & {"venta", "ventas"} or (
        "id documento" in headers and "monto venta" in headers
    ):
        return "ventas"
    if "historial" in sheet and "costo" in sheet:
        return "historial_costos"
    if "costo" in sheet and "producto" in sheet:
        return "costos"
    if "inventario" in sheet or "stock" in sheet_tokens or "stock sistema" in headers:
        return "inventario"
    if sheet_tokens & {"devolucion", "devoluciones", "retorno", "retornos"}:
        return "devoluciones"
    if "compra" in sheet or "id compra" in headers:
        return "compras"
    if "gasto" in sheet or "id gasto" in headers:
        return "gastos"
    if (
        "cobran" in sheet
        or "id pago" in headers
        or (
            "valor nominal" in headers
            and "lote" in headers
            and "fecha pago" in headers
        )
    ):
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
    if (
        "trabajador" in sheet
        or "empleado" in sheet
        or "id trabajador" in headers
        or ("cargo" in headers and ("comision" in headers or "sueldo" in headers))
    ):
        return "vendedores"
    if "campan" in sheet or (
        "impresiones" in headers and "clics" in headers and "inversion" in headers
    ):
        return "campanas"
    if "instruccion" in sheet or (
        len(frame.columns) <= 3 and "columna" in headers and "rut" in headers
    ):
        return "auxiliar"
    return "otra"


def _first_column(
    columns: Any,
    candidates: tuple[tuple[str, ...], ...],
    *,
    excluded: tuple[str, ...] = (),
) -> str | None:
    """Find the first semantically preferred header from a synonym list."""

    for required in candidates:
        match = find_column(columns, *required, excluded=excluded)
        if match:
            return match
    return None


def _net_amount_column(columns: Any, *, domain: str | None = None) -> str | None:
    candidates: list[tuple[str, ...]] = [
        ("monto", "neto"),
        ("venta", "neta"),
        ("importe", "neto"),
        ("total", "neto"),
        ("net", "amount"),
        ("net", "sales"),
    ]
    if domain:
        candidates.extend(
            [
                ("monto", domain),
                ("total", domain),
            ]
        )
    candidates.extend([("monto",), ("importe",), ("total",)])
    return _first_column(
        columns,
        tuple(candidates),
        excluded=("iva", "impuesto", "unitario", "ticket", "promedio"),
    )


def _event_date_column(columns: Any, domain: str | None = None) -> str | None:
    candidates: list[tuple[str, ...]] = []
    if domain:
        candidates.extend([("fecha", domain), (domain, "fecha")])
    candidates.extend([("fecha",), ("periodo",), ("mes",)])
    return _first_column(columns, tuple(candidates))


def _entity_key(columns: Any, entity: str) -> str | None:
    """Clave empresarial con los prefijos habituales, sin exigir solo `ID`."""

    if columns is None:
        return None
    if entity == "producto":
        sku = find_column(columns, "sku", entity)
        if sku:
            return sku
    return (
        find_column(columns, "id", entity)
        or find_column(columns, "cod", entity)
        or find_column(columns, "codigo", entity)
    )


def classify_business_sheets(frames: dict[str, pd.DataFrame]) -> dict[str, list[str]]:
    classified: dict[str, list[str]] = defaultdict(list)
    for name, frame in frames.items():
        classified[_sheet_kind(name, frame)].append(name)
    return dict(classified)


def _append_sales(
    frames: dict[str, pd.DataFrame],
    names: list[str],
    mappings: dict[str, dict[str, str]],
) -> tuple[pd.DataFrame, dict[str, str]]:
    if not names:
        return pd.DataFrame(), {}
    # Las ventas mensuales/semestrales pueden usar sinónimos de encabezado.
    # El mismo alineador que usa "Unir periodos" evita que Visión del negocio
    # sume únicamente la primera hoja y deje el resto lleno de NaN.
    combined, combined_mapping, _ = append_compatible_frames(
        {name: frames[name] for name in names},
        mappings,
        allow_single=True,
    )
    combined = combined.rename(columns={"hoja_origen": "_hoja_origen"})
    source_rows: list[int] = []
    for name in names:
        rows = list(frames[name].attrs.get("adsveris_source_rows", []))
        source_rows.extend(
            rows if len(rows) == len(frames[name]) else range(2, len(frames[name]) + 2)
        )
    combined["_fila_origen"] = source_rows
    return combined, combined_mapping


def _source_row_number(
    frame: pd.DataFrame,
    index: Any,
    row: pd.Series,
) -> int:
    raw_value = row.get("_fila_origen")
    if raw_value is not None and not pd.isna(raw_value):
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            pass
    try:
        position = frame.index.get_loc(index)
        if isinstance(position, int):
            return position + 2
    except (KeyError, TypeError):
        pass
    return 2


def _unique_reference(
    frame: pd.DataFrame | None,
    key_column: str | None,
    value_columns: list[str],
) -> tuple[pd.DataFrame, dict[str, int]]:
    if frame is None or not key_column or key_column not in frame.columns:
        return pd.DataFrame(), {"claves": 0, "duplicadas": 0, "conflictivas": 0}
    usable_values = [
        c for c in dict.fromkeys(value_columns)
        if c in frame.columns and c != key_column
    ]
    reference = frame[[key_column, *usable_values]].copy()
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
    reference_keys = set(_keys(reference[reference_column]).dropna())
    informed = source_keys.notna()
    orphan = informed & ~source_keys.isin(reference_keys)
    missing = ~informed
    valid = informed & ~orphan
    locations = []
    for index in source.index[orphan][:8]:
        row = source.loc[index]
        locations.append({
            "hoja": str(row.get("_hoja_origen", label.split(" → ")[0])),
            "fila": _source_row_number(source, index, row),
            "clave": str(row.get(source_column, "")),
        })
    return {
        "relacion": label,
        "filas": int(len(source)),
        "validas": int(valid.sum()),
        "huerfanas": int(orphan.sum()),
        "sin_clave": int(missing.sum()),
        "cobertura_pct": round(float(valid.sum()) / max(len(source), 1) * 100, 1),
        "ejemplos": sorted({str(value) for value in source.loc[orphan, source_column].head(8)}),
        "ubicaciones": locations,
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
    ref = ref[ref["_k"].notna()].drop_duplicates(subset=["_k"], keep="first")
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
        "filas": checked,
        "validas": checked - conflicts,
        "huerfanas": conflicts,
        "sin_clave": 0,
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


def _business_filter_dimensions(
    sales: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
    kinds: dict[str, list[str]],
    mapping: dict[str, str],
    results: dict[str, dict],
) -> dict[str, pd.Series]:
    """Valores legibles usados tanto por los filtros como por agrupaciones.

    Los nombres de producto, sucursal y vendedor se resuelven mediante
    lookups many-to-one seguros. Si un maestro tiene claves conflictivas,
    _reference_values rehúsa usar esas claves y conserva el identificador.
    """

    dimensions: dict[str, pd.Series] = {}
    products = frames.get((kinds.get("productos") or [None])[0]) if kinds.get("productos") else None
    branches = frames.get((kinds.get("sucursales") or [None])[0]) if kinds.get("sucursales") else None
    sellers = frames.get((kinds.get("vendedores") or [None])[0]) if kinds.get("vendedores") else None

    product_key = mapping.get("producto") or _entity_key(sales.columns, "producto")
    product_ref_key = (
        _entity_key(products.columns, "producto")
        if products is not None
        else None
    )
    product_name = (
        find_column(products.columns, "nombre", "producto")
        or find_column(products.columns, "descripcion", "producto")
        or find_column(
            products.columns,
            "producto",
            excluded=("id", "sku", "codigo", "código", "categoria"),
        )
        if products is not None
        else None
    )
    category = find_column(products.columns, "categoria") if products is not None else None
    if product_key and product_key in sales.columns:
        dimensions["producto"] = _reference_values(
            sales, product_key, products, product_ref_key, product_name
        ).fillna(sales[product_key])
        dimensions["categoria"] = _reference_values(
            sales, product_key, products, product_ref_key, category
        )
    else:
        direct_product = mapping.get("producto")
        direct_category = mapping.get("categoria") or find_column(sales.columns, "categoria")
        if direct_product and direct_product in sales.columns:
            dimensions["producto"] = sales[direct_product]
        if direct_category and direct_category in sales.columns:
            dimensions["categoria"] = sales[direct_category]

    channel = mapping.get("canal") or find_column(sales.columns, "canal")
    if channel and channel in sales.columns:
        dimensions["canal"] = sales[channel]

    branch_key = mapping.get("sucursal") or _entity_key(sales.columns, "sucursal")
    branch_ref_key = (
        _entity_key(branches.columns, "sucursal") if branches is not None else None
    )
    branch_name = (
        find_column(branches.columns, "nombre", "sucursal")
        or find_column(branches.columns, "sucursal", excluded=("id",))
        if branches is not None
        else None
    )
    if branch_key and branch_key in sales.columns:
        dimensions["sucursal"] = _reference_values(
            sales, branch_key, branches, branch_ref_key, branch_name
        ).fillna(sales[branch_key])

    seller_key = mapping.get("vendedor") or _entity_key(sales.columns, "vendedor")
    seller_ref_key = (
        _entity_key(sellers.columns, "vendedor") if sellers is not None else None
    )
    seller_name = (
        find_column(sellers.columns, "nombre", "vendedor")
        or find_column(sellers.columns, "nombre")
        or find_column(
            sellers.columns,
            "vendedor",
            excluded=("id", "cod", "codigo"),
        )
        if sellers is not None
        else None
    )
    if seller_key and seller_key in sales.columns:
        dimensions["vendedor"] = _reference_values(
            sales, seller_key, sellers, seller_ref_key, seller_name
        ).fillna(sales[seller_key])

    currency_column = mapping.get("moneda") or find_column(sales.columns, "moneda")
    if currency_column and currency_column in sales.columns:
        dimensions["moneda"] = sales[currency_column]
        return dimensions

    currency_by_sheet: dict[str, str] = {}
    for name in kinds.get("ventas", []):
        detection = results.get(name, {}).get("_moneda")
        dominant = getattr(detection, "dominante", None)
        if dominant and not getattr(detection, "mixta", False):
            currency_by_sheet[name] = str(dominant)
    if currency_by_sheet and "_hoja_origen" in sales.columns:
        dimensions["moneda"] = sales["_hoja_origen"].map(currency_by_sheet)
    return dimensions


def _filter_options(dimensions: dict[str, pd.Series]) -> dict[str, list[str]]:
    options: dict[str, list[str]] = {}
    for key in BUSINESS_FILTER_KEYS:
        series = dimensions.get(key)
        if series is None:
            continue
        values = {
            str(value).strip()
            for value in series.dropna()
            if str(value).strip()
        }
        if values:
            options[key] = sorted(values, key=lambda value: strip_accents_lower(value))
    return options


def _cost_outlier_limit(values: pd.Series) -> float | None:
    positive = values[values > 0].dropna()
    if len(positive) < 20:
        return None
    q1, q3 = positive.quantile(0.25), positive.quantile(0.75)
    spread = float(q3 - q1)
    return float(q3 + 5 * spread) if spread > 0 else None


def _applicable_unit_cost(
    sales: pd.DataFrame,
    product_key: str | None,
    sales_dates: pd.Series,
    current_costs: pd.DataFrame | None,
    cost_key: str | None,
    unit_cost_col: str | None,
    cost_history: pd.DataFrame | None,
) -> tuple[pd.Series, pd.Series, dict[str, Any]]:
    """Return one applicable cost per sale without multiplying rows.

    Historical costs use an as-of match (last effective date not after the
    sale). When history does not cover a row, a trustworthy current catalogue
    value is exposed as an estimate. Its provenance remains separate so it can
    improve the management view without turning a historical estimate into a
    certifiable accounting result.
    """

    empty_cost = pd.Series(float("nan"), index=sales.index, dtype=float)
    empty_source = pd.Series(None, index=sales.index, dtype=object)
    if not product_key or product_key not in sales.columns:
        return empty_cost, empty_source, {
            "metodo": "sin_clave_producto",
            "filas_historicas": 0,
            "filas_catalogo_actual": 0,
            "claves_historicas_conflictivas": 0,
        }

    history_key = (
        (
            find_column(cost_history.columns, "sku", "producto")
            or find_column(cost_history.columns, "id", "producto")
            or find_column(cost_history.columns, "producto")
        )
        if cost_history is not None
        else None
    )
    history_date = (
        _first_column(
            cost_history.columns,
            (
                ("fecha", "desde"),
                ("vigencia", "desde"),
                ("fecha", "inicio"),
                ("effective", "from"),
                ("vigencia",),
            ),
        )
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
        return cost, source, {
            "metodo": "historial_asof" if usable_history else "sin_costos_utilizables",
            "filas_historicas": historical_rows,
            "filas_catalogo_actual": 0,
            "claves_historicas_conflictivas": len(conflicting_pairs),
            **reference_quality,
        }
    current_values = numeric_series(safe_current, unit_cost_col)
    trustworthy = current_values.gt(0)
    # Un costo alto del catálogo maestro sigue siendo autoritativo. Marcarlo
    # como atípico sirve para calidad, pero excluirlo del costo de venta crea
    # utilidades artificiales en productos legítimamente caros.
    lookup = dict(
        zip(
            safe_current.loc[trustworthy, "_key"],
            current_values.loc[trustworthy],
            strict=False,
        )
    )
    current_cost = _keys(sales[product_key]).map(lookup).astype(float)
    if usable_history:
        fallback = cost.isna() & current_cost.notna()
        cost.loc[fallback] = current_cost.loc[fallback]
        source.loc[fallback] = "catalogo_actual_estimado"
        method = "historial_asof_con_respaldo_actual"
        current_rows = int(fallback.sum())
    else:
        cost = current_cost
        source.loc[cost.notna()] = "catalogo_actual"
        method = "catalogo_actual"
        current_rows = int(cost.notna().sum())
    return cost, source, {
        "metodo": method,
        "filas_historicas": historical_rows,
        "filas_catalogo_actual": current_rows,
        "claves_historicas_conflictivas": len(conflicting_pairs),
        **reference_quality,
    }


def _formula_controls(frames: dict[str, pd.DataFrame], kinds: dict[str, list[str]]) -> list[dict]:
    controls: list[dict] = []

    for name in kinds.get("ventas", []):
        frame = frames[name]
        amount_col = _net_amount_column(frame.columns, domain="venta")
        quantity_col = find_column(frame.columns, "cantidad")
        price_col = find_column(frame.columns, "precio", "unitario")
        discount_col = find_column(frame.columns, "descuento")
        tax_col = find_column(frame.columns, "iva")
        total_col = _first_column(
            frame.columns,
            (("total", "documento"), ("total",)),
            excluded=("subtotal", "neto"),
        )
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
                relative_tolerance=0.02,
                absolute_tolerance=50,
            ).to_dict()}
        )
        tax = numeric_series(frame, tax_col)
        comparable = amount.notna() & tax.notna() & (amount.abs() > 0)
        rate = float((tax[comparable] / amount[comparable]).abs().median()) if comparable.any() else 0.19
        if not 0.03 <= rate <= 0.35:
            rate = 0.19
        controls.append(
            {"hoja": name, **formula_mismatch(
                "iva_venta",
                tax,
                amount * rate,
                source_rows=source_rows,
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
        quantity = numeric_series(
            frame,
            _first_column(frame.columns, (("cantidad", "comprada"), ("cantidad",))),
        )
        unit_cost = numeric_series(frame, find_column(frame.columns, "costo", "unitario"))
        discount = numeric_series(frame, find_column(frame.columns, "descuento")).fillna(0)
        net = numeric_series(frame, _net_amount_column(frame.columns, domain="compra"))
        tax = numeric_series(frame, find_column(frame.columns, "iva"))
        total = numeric_series(
            frame,
            _first_column(frame.columns, (("total", "compra"), ("total",))),
        )
        source_rows = list(frame.attrs.get("adsveris_source_rows", []))
        controls.append({"hoja": name, **formula_mismatch(
            "neto_compra", net, quantity * unit_cost * (1 - discount),
            source_rows=source_rows, eligible=discount.between(0, 1),
        ).to_dict()})
        controls.append({"hoja": name, **formula_mismatch(
            "total_compra", total, net + tax, source_rows=source_rows,
            relative_tolerance=0.0,
        ).to_dict()})

    for name in kinds.get("gastos", []):
        frame = frames[name]
        net = numeric_series(frame, _net_amount_column(frame.columns, domain="gasto"))
        tax = numeric_series(frame, find_column(frame.columns, "iva"))
        total_column = _first_column(
            frame.columns,
            (("total", "gasto"), ("total",)),
        )
        if total_column is None or not tax.notna().any():
            continue
        total = numeric_series(frame, total_column)
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


def _indicator_contract(
    key: str,
    category: str,
    label: str,
    value: float | int | None,
    unit: str,
    *,
    period_from: str | None,
    period_to: str | None,
    formula: str,
    numerator: float | int | None = None,
    denominator: float | int | None = None,
    prior_value: float | int | None = None,
    variation_type: str = "porcentaje",
    coverage: float | None = None,
    status: str | None = None,
    warnings: list[str] | None = None,
    required: list[str] | None = None,
    sources: list[str] | None = None,
    polarity: str = "neutral",
    visualizations: list[str] | None = None,
) -> dict[str, Any]:
    """Stable, auditable contract used by every adaptive KPI.

    Missing inputs remain ``None`` and are never converted to zero.  The
    frontend can therefore distinguish an unavailable indicator from a real
    result equal to zero.
    """

    effective_status = status or (
        "available"
        if value is not None and (coverage is None or coverage >= 99.5)
        else "partial"
        if value is not None
        else "unavailable"
    )
    nominal_change = (
        float(value) - float(prior_value)
        if value is not None and prior_value is not None
        else None
    )
    if variation_type == "puntos_porcentuales":
        variation = nominal_change
    elif (
        nominal_change is not None
        and prior_value is not None
        and float(prior_value) != 0
    ):
        variation = nominal_change / abs(float(prior_value)) * 100
    else:
        variation = None
    return {
        "id": key,
        "categoria": category,
        "nombre": label,
        "valor": round(float(value), 2) if value is not None else None,
        "unidad": unit,
        "periodo_actual": {"desde": period_from, "hasta": period_to},
        "valor_anterior": round(float(prior_value), 2)
        if prior_value is not None
        else None,
        "diferencia_nominal": round(nominal_change, 2)
        if nominal_change is not None
        else None,
        "variacion": round(variation, 2) if variation is not None else None,
        "tipo_variacion": variation_type,
        "formula": formula,
        "numerador": round(float(numerator), 2)
        if numerator is not None
        else None,
        "denominador": round(float(denominator), 2)
        if denominator is not None
        else None,
        "cobertura_datos_pct": round(float(coverage), 1)
        if coverage is not None
        else None,
        "estado": effective_status,
        "advertencias": warnings or [],
        "requiere": required or [],
        "fuentes": sources or [],
        "polaridad": polarity,
        "visualizaciones": visualizations or [],
    }


def _collection_profile_columns(frame: pd.DataFrame) -> dict[str, str | None] | None:
    """Recognize the auditable nominal-value collection profile.

    The profile is intentionally strict: a generic payments sheet must not be
    reinterpreted as this dashboard unless the three defining fields exist.
    Optional dimensions only enable their corresponding filter or chart.
    """

    exact_lot = next(
        (
            str(column)
            for column in frame.columns
            if normalized_header(column) == "lote"
        ),
        None,
    )
    columns = {
        "valor": find_column(frame.columns, "valor", "nominal"),
        "lote": exact_lot,
        "fecha_pago": find_column(frame.columns, "fecha", "pago"),
        "periodo_cotizado": find_column(frame.columns, "periodo", "cotizado"),
        "subgrupo": find_column(frame.columns, "cobrador", "final", "grupo"),
        "agencia_pago": find_column(frame.columns, "agencia", "recepcion", "pago"),
        "forma_pago": find_column(frame.columns, "forma", "pago"),
        "descripcion_pago": find_column(frame.columns, "descripcion", "lote"),
    }
    if not all(columns[key] for key in ("valor", "lote", "fecha_pago")):
        return None
    return columns


def has_collection_dashboard_profile(frames: dict[str, pd.DataFrame]) -> bool:
    """Cheap public predicate used by the metrics route."""

    return any(_collection_profile_columns(frame) for frame in frames.values())


def _collection_team(value: object) -> str:
    normalized = normalized_header(value)
    if normalized in {
        "est juridico lexco",
        "est juridico proinnova",
        "est juridico gna",
        "judicial",
    }:
        return "JUDICIAL"
    if normalized == "ejecutivos nmv flujo":
        return "FLUJO"
    if normalized == "stock":
        return "STOCK"
    return "SIN ASIGNAR"


def _collection_label(value: object, fallback: str = "SIN ASIGNAR") -> str:
    if value is None or pd.isna(value):
        return fallback
    text = " ".join(str(value).strip().split())
    return text or fallback


def _collection_options(series: pd.Series | None) -> list[str]:
    if series is None:
        return []
    by_key: dict[str, str] = {}
    for value in series:
        label = _collection_label(value)
        by_key.setdefault(_text_key(label) or label.casefold(), label)
    return sorted(by_key.values(), key=lambda item: strip_accents_lower(item))


def _collection_group(
    frame: pd.DataFrame,
    column: str,
    *,
    collection_mask: pd.Series,
    top: int | None = None,
    other_label: str = "Otros",
) -> list[dict[str, Any]]:
    if column not in frame.columns:
        return []
    working = pd.DataFrame({
        "nombre": frame[column].map(_collection_label),
        "valor": frame["_valor_nominal"].where(collection_mask),
    }).dropna(subset=["valor"])
    grouped = (
        working.groupby("nombre", dropna=False)["valor"]
        .sum()
        .sort_values(ascending=False)
    )
    if top and len(grouped) > top:
        visible = grouped.iloc[:top].copy()
        visible.loc[other_label] = float(grouped.iloc[top:].sum())
        grouped = visible
    total = float(grouped.sum())
    return [
        {
            "nombre": str(name),
            "valor": round(float(value), 2),
            "participacion_pct": round(float(value) / total * 100, 2)
            if total
            else None,
        }
        for name, value in grouped.items()
    ]


def _empty_business_shell(
    *,
    profile: str,
    filters_available: dict[str, list[str]],
    filters_applied: dict[str, str],
    catalog: dict[str, Any],
    collection: dict[str, Any],
    sheet_name: str,
) -> dict[str, Any]:
    """Keep the established API contract while exposing a specialized view."""

    return {
        "version": 3,
        "perfil": profile,
        "filtros": {
            "disponibles": filters_available,
            "aplicados": filters_applied,
        },
        "estado_certificacion": "certified",
        "confianza_pct": 100.0,
        "alcance": {
            "hojas_ventas": [],
            "hoja_costos": None,
            "hoja_historial_costos": None,
            "hojas_utilizadas": [sheet_name],
            "filas_ventas_sin_filtros": 0,
            "filas_ventas_fisicas": 0,
            "filas_totales_estructurales": 0,
            "filas_anuladas": 0,
            "filas_indicadores": 0,
            "documentos_repetidos": 0,
            "filas_adicionales_documento": 0,
            "documentos_conflictivos": 0,
        },
        "estado_resultados": {
            "ventas_observadas": 0,
            "ventas_certificables": 0,
            "ventas_pareadas": 0,
            "costo_venta_conocido": 0,
            "costo_venta_estimado_catalogo": 0,
            "utilidad_bruta": None,
            "margen_bruto_pct": None,
            "gastos_operacionales": None,
            "gastos_operacionales_periodo": None,
            "filas_gastos": 0,
            "resultado_operacional": None,
            "margen_operacional_pct": None,
            "cobertura_costos_pct": 0,
            "cobertura_costos_historica_pct": 0,
            "cobertura_costos_certificable_pct": 0,
            "ventas_certificables_pareadas": 0,
            "costo_certificable": 0,
            "utilidad_certificable": None,
            "margen_certificable_pct": None,
            "resultado_operacional_certificable": None,
            "margen_operacional_certificable_pct": None,
        },
        "operacion": {
            "cobrado_aplicado": collection["kpis"]["recaudacion_cobranza"],
            "cobranza_sobre_documentos_pct": collection["kpis"]["participacion_cobranza_pct"],
            "documentos_sobrepagados": 0,
            "pagos_duplicados_excluidos": 0,
            "cobranzas_huerfanas": 0,
            "cuentas_por_cobrar": None,
            "cuentas_vencidas": None,
            "dso_dias": None,
            "mora_promedio_dias": None,
            "valor_inventario": None,
            "stock_inventario": None,
            "inventario_bajo_minimo": None,
            "fecha_corte_inventario": None,
            "compras_efectivas": None,
            "fletes_compra": None,
            "gastos_fijos": None,
            "gastos_variables": None,
            "gasto_fijo_mensual_promedio": None,
            "punto_equilibrio_ventas": None,
            "rotacion_inventario_aprox": None,
        },
        "evolucion": [],
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
            "nota": "Este perfil analiza recaudación; no infiere metas de venta.",
        },
        "sensibilidad": {
            "base_utilidad_bruta": None,
            "costo_mas_5": None,
            "costo_mas_10": None,
            "nota": "No corresponde al perfil de cobranza nominal.",
        },
        "calidad": {
            "costos": {},
            "integridad_referencial": [],
            "controles_formula": [],
            "filas_inconsistentes_formula": 0,
            "referencias_problematicas": 0,
        },
        "ratios": [],
        "decisiones": [],
        "catalogo_indicadores": catalog,
        "cobranza": collection,
    }


def _analyze_nominal_collection(
    frames: dict[str, pd.DataFrame],
    results: dict[str, dict],
    *,
    date_from: str | None,
    date_to: str | None,
    filters: dict[str, str] | None,
) -> dict[str, Any] | None:
    profile: tuple[str, pd.DataFrame, dict[str, str | None]] | None = None
    for name, frame in frames.items():
        columns = _collection_profile_columns(frame)
        if columns:
            profile = (name, frame.copy(), columns)
            break
    if profile is None:
        return None
    sheet_name, frame, columns = profile
    value_column = str(columns["valor"])
    lot_column = str(columns["lote"])
    date_column = str(columns["fecha_pago"])
    frame["_valor_nominal"] = numeric_series(frame, value_column)
    frame["_lote"] = numeric_series(frame, lot_column)
    frame["_fecha_pago"] = _dates(frame, date_column)
    frame["_equipo"] = (
        frame[str(columns["subgrupo"])].map(_collection_team)
        if columns["subgrupo"]
        else pd.Series("SIN ASIGNAR", index=frame.index)
    )
    dimensions: dict[str, pd.Series] = {
        "equipo": frame["_equipo"],
    }
    for key in ("periodo_cotizado", "subgrupo", "agencia_pago", "forma_pago"):
        column = columns[key]
        if column:
            dimensions[key] = frame[str(column)]
    available_filters = {
        key: _collection_options(series)
        for key, series in dimensions.items()
        if series is not None and series.notna().any()
    }
    applied_filters = {
        key: str(value).strip()
        for key, value in (filters or {}).items()
        if key in dimensions and str(value).strip()
    }

    dimension_mask = pd.Series(True, index=frame.index)
    for key, selected in applied_filters.items():
        dimension_mask &= _keys(dimensions[key]).eq(_text_key(selected))
    current_mask = dimension_mask & _date_filter(
        frame["_fecha_pago"], date_from, date_to
    )
    current = frame.loc[current_mask].copy()
    current_collection = current["_lote"].le(300) & current["_lote"].notna()
    amount = current["_valor_nominal"]
    total = float(amount.dropna().sum())
    collection_total = float(amount[current_collection].dropna().sum())
    difference = total - collection_total
    row_count = int(len(current))
    collection_rows = int(current_collection.sum())
    positive_rows = int(amount.gt(0).sum())
    difference_pct = difference / total * 100 if total else None
    collection_share = collection_total / total * 100 if total else None

    prior_total = None
    prior_collection = None
    prior_frame = pd.DataFrame()
    period_start = current["_fecha_pago"].dropna().min() if not current.empty else None
    period_end = current["_fecha_pago"].dropna().max() if not current.empty else None
    requested_start = pd.to_datetime(date_from) if date_from else period_start
    requested_end = (
        pd.Period(date_to, freq="M").end_time.normalize()
        if date_to and len(str(date_to)) == 7
        else pd.to_datetime(date_to)
        if date_to
        else period_end
    )
    if (
        requested_start is not None
        and requested_end is not None
        and pd.notna(requested_start)
        and pd.notna(requested_end)
    ):
        duration = (requested_end.normalize() - requested_start.normalize()).days + 1
        prior_end = requested_start.normalize() - pd.Timedelta(days=1)
        prior_start = prior_end - pd.Timedelta(days=max(duration - 1, 0))
        prior_mask = (
            dimension_mask
            & frame["_fecha_pago"].ge(prior_start)
            & frame["_fecha_pago"].le(prior_end)
        )
        prior_frame = frame.loc[prior_mask].copy()
        prior_collection_mask = (
            prior_frame["_lote"].le(300) & prior_frame["_lote"].notna()
        )
        prior_total = float(prior_frame["_valor_nominal"].dropna().sum())
        prior_collection = float(
            prior_frame.loc[prior_collection_mask, "_valor_nominal"].dropna().sum()
        )

    span_days = (
        (requested_end.normalize() - requested_start.normalize()).days + 1
        if requested_start is not None
        and requested_end is not None
        and pd.notna(requested_start)
        and pd.notna(requested_end)
        else 0
    )
    if span_days <= 31:
        period_key = current["_fecha_pago"].dt.strftime("%Y-%m-%d")
        grain = "día"
    elif span_days <= 180:
        period_key = current["_fecha_pago"].dt.to_period("W-MON").astype(str)
        grain = "semana"
    else:
        period_key = current["_fecha_pago"].dt.to_period("M").astype(str)
        grain = "mes"
    timeline_frame = pd.DataFrame({
        "periodo": period_key,
        "total": amount,
        "cobranza": amount.where(current_collection),
    }).dropna(subset=["periodo"])
    timeline = [
        {
            "periodo": str(period),
            "recaudacion_total": round(float(row["total"]), 2),
            "recaudacion_cobranza": round(float(row["cobranza"]), 2),
            "diferencia": round(float(row["total"] - row["cobranza"]), 2),
        }
        for period, row in (
            timeline_frame.groupby("periodo")[["total", "cobranza"]]
            .sum()
            .sort_index()
            .iterrows()
        )
    ]

    team_rows: list[dict[str, Any]] = []
    for team, rows in current.groupby("_equipo", dropna=False):
        team_collection = rows["_lote"].le(300) & rows["_lote"].notna()
        team_total = float(rows["_valor_nominal"].dropna().sum())
        team_collected = float(
            rows.loc[team_collection, "_valor_nominal"].dropna().sum()
        )
        team_rows.append({
            "equipo": str(team),
            "subgrupo": None,
            "recaudacion_cobranza": round(team_collected, 2),
            "recaudacion_total": round(team_total, 2),
            "diferencia": round(team_total - team_collected, 2),
            "participacion_pct": round(team_collected / collection_total * 100, 2)
            if collection_total
            else None,
        })
        if team == "JUDICIAL" and columns["subgrupo"]:
            for subgroup, subgroup_rows in rows.groupby(str(columns["subgrupo"])):
                subgroup_collection = (
                    subgroup_rows["_lote"].le(300)
                    & subgroup_rows["_lote"].notna()
                )
                subgroup_total = float(
                    subgroup_rows["_valor_nominal"].dropna().sum()
                )
                subgroup_collected = float(
                    subgroup_rows.loc[
                        subgroup_collection, "_valor_nominal"
                    ].dropna().sum()
                )
                team_rows.append({
                    "equipo": "JUDICIAL",
                    "subgrupo": _collection_label(subgroup),
                    "recaudacion_cobranza": round(subgroup_collected, 2),
                    "recaudacion_total": round(subgroup_total, 2),
                    "diferencia": round(subgroup_total - subgroup_collected, 2),
                    "participacion_pct": round(
                        subgroup_collected / collection_total * 100, 2
                    )
                    if collection_total
                    else None,
                    "participacion_equipo_pct": round(
                        subgroup_collected / team_collected * 100, 2
                    )
                    if team_collected
                    else None,
                })
    parent_rows = sorted(
        (row for row in team_rows if row["subgrupo"] is None),
        key=lambda row: -float(row["recaudacion_cobranza"]),
    )
    subgroup_rows = sorted(
        (row for row in team_rows if row["subgrupo"] is not None),
        key=lambda row: -float(row["recaudacion_cobranza"]),
    )
    team_rows = []
    for parent in parent_rows:
        team_rows.append(parent)
        if parent["equipo"] == "JUDICIAL":
            team_rows.extend(subgroup_rows)

    period_rows: list[dict[str, Any]] = []
    period_column = columns["periodo_cotizado"]
    if period_column:
        quoted_dates = _dates(current, str(period_column))
        period_working = pd.DataFrame({
            "periodo": quoted_dates.dt.to_period("M").astype(str),
            "valor": amount.where(current_collection),
        })
        period_working = period_working[
            quoted_dates.notna() & period_working["valor"].notna()
        ]
        period_rows = [
            {"periodo": str(period), "valor": round(float(value), 2)}
            for period, value in (
                period_working.groupby("periodo")["valor"]
                .sum()
                .sort_index()
                .tail(12)
                .items()
            )
        ]

    detection = results.get(sheet_name, {}).get("_moneda")
    currency = getattr(detection, "dominante", None) or "CLP"
    period_from = (
        requested_start.date().isoformat()
        if requested_start is not None and pd.notna(requested_start)
        else None
    )
    period_to = (
        requested_end.date().isoformat()
        if requested_end is not None and pd.notna(requested_end)
        else None
    )
    indicators = [
        _indicator_contract(
            "recaudacion_cobranza",
            "cobranza",
            "Recaudación de cobranza",
            collection_total,
            currency,
            period_from=period_from,
            period_to=period_to,
            prior_value=prior_collection,
            formula="Σ Valor Nominal donde Lote ≤ 300",
            numerator=collection_total,
            required=["Valor Nominal", "Lote"],
            sources=[sheet_name],
            polarity="higher_is_better",
            visualizations=["kpi", "linea_temporal", "donut"],
        ),
        _indicator_contract(
            "recaudacion_total",
            "cobranza",
            "Recaudación total",
            total,
            currency,
            period_from=period_from,
            period_to=period_to,
            prior_value=prior_total,
            formula="Σ Valor Nominal de todos los lotes",
            numerator=total,
            required=["Valor Nominal"],
            sources=[sheet_name],
            polarity="higher_is_better",
            visualizations=["kpi", "linea_temporal"],
        ),
        _indicator_contract(
            "diferencia_recaudacion",
            "cobranza",
            "Diferencia total − cobranza",
            difference,
            currency,
            period_from=period_from,
            period_to=period_to,
            formula="Recaudación total − recaudación de cobranza",
            numerator=total,
            denominator=collection_total,
            required=["Valor Nominal", "Lote"],
            sources=[sheet_name],
            polarity="neutral",
            visualizations=["kpi", "barras"],
        ),
        _indicator_contract(
            "porcentaje_diferencia",
            "cobranza",
            "% diferencia",
            difference_pct,
            "%",
            period_from=period_from,
            period_to=period_to,
            formula="Diferencia ÷ recaudación total × 100",
            numerator=difference,
            denominator=total,
            variation_type="puntos_porcentuales",
            required=["Valor Nominal", "Lote"],
            sources=[sheet_name],
            polarity="lower_is_better",
            visualizations=["kpi"],
        ),
        _indicator_contract(
            "pagos_registrados",
            "cobranza",
            "N.º de pagos registrados",
            row_count,
            "registros",
            period_from=period_from,
            period_to=period_to,
            formula="Conteo de filas filtradas; no existe ID único de pago",
            numerator=row_count,
            required=["una fila por registro"],
            sources=[sheet_name],
            polarity="higher_is_better",
            visualizations=["kpi"],
        ),
        _indicator_contract(
            "ticket_promedio_cobranza",
            "cobranza",
            "Ticket promedio de cobranza",
            collection_total / collection_rows if collection_rows else None,
            f"{currency}/registro",
            period_from=period_from,
            period_to=period_to,
            formula="Recaudación de cobranza ÷ registros con Lote ≤ 300",
            numerator=collection_total,
            denominator=collection_rows,
            required=["Valor Nominal", "Lote"],
            sources=[sheet_name],
            polarity="higher_is_better",
            visualizations=["kpi"],
        ),
    ]
    catalog = {
        "version": 2,
        "moneda": currency,
        "categorias": [{
            "id": "cobranza",
            "nombre": "Cobranza y recaudación",
            "descripcion": "Valor nominal, lotes, equipos, agencias y medios de pago.",
            "estado": "available",
            "disponibles": len(indicators),
            "total": len(indicators),
            "indicadores": indicators,
        }],
        "disponibles": len(indicators),
        "parciales": 0,
        "no_disponibles": 0,
    }
    collection = {
        "hoja": sheet_name,
        "moneda": currency,
        "grano_temporal": grain,
        "periodo": {"desde": period_from, "hasta": period_to},
        "kpis": {
            "recaudacion_cobranza": round(collection_total, 2),
            "recaudacion_total": round(total, 2),
            "diferencia": round(difference, 2),
            "diferencia_pct": round(difference_pct, 2)
            if difference_pct is not None
            else None,
            "participacion_cobranza_pct": round(collection_share, 2)
            if collection_share is not None
            else None,
            "registros": row_count,
            "registros_cobranza": collection_rows,
            "pagos_positivos": positive_rows,
            "ticket_promedio_total": round(total / row_count, 2)
            if row_count
            else None,
            "ticket_promedio_cobranza": round(
                collection_total / collection_rows, 2
            )
            if collection_rows
            else None,
        },
        "comparacion": {
            "recaudacion_actual": round(collection_total, 2),
            "recaudacion_anterior": round(prior_collection, 2)
            if prior_collection is not None
            else None,
            "diferencia": round(collection_total - prior_collection, 2)
            if prior_collection is not None
            else None,
            "variacion_pct": round(
                (collection_total - prior_collection)
                / abs(prior_collection)
                * 100,
                2,
            )
            if prior_collection
            else None,
            "base_comparable": bool(prior_collection),
        },
        "evolucion": timeline,
        "equipos": team_rows,
        "agencias": _collection_group(
            current,
            str(columns["agencia_pago"]),
            collection_mask=current_collection,
            top=10,
        )
        if columns["agencia_pago"]
        else [],
        "formas_pago": _collection_group(
            current,
            str(columns["forma_pago"]),
            collection_mask=current_collection,
            top=6,
        )
        if columns["forma_pago"]
        else [],
        "periodos_cotizados": period_rows,
        "descripciones_pago": _collection_group(
            current,
            str(columns["descripcion_pago"]),
            collection_mask=current_collection,
        )
        if columns["descripcion_pago"]
        else [],
        "notas": [
            "Todas las medidas monetarias parten exclusivamente de Valor Nominal.",
            "Cobranza agrega la condición Lote ≤ 300 después de aplicar los filtros.",
            "El conteo corresponde a filas porque el archivo no contiene un ID único de pago.",
        ],
    }
    return _empty_business_shell(
        profile="cobranza_nominal",
        filters_available=available_filters,
        filters_applied=applied_filters,
        catalog=catalog,
        collection=collection,
        sheet_name=sheet_name,
    )


def analyze_business_workbook(
    frames: dict[str, pd.DataFrame],
    mappings: dict[str, dict[str, str]],
    results: dict[str, dict],
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    filters: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Build an executive and diagnostic view without mixing table grains."""

    service_profile = analyze_service_business(frames)
    if service_profile is not None:
        return service_profile
    if any(
        normalized_header(name) == "detalle ot"
        or _sheet_kind(name, frame) == "detalle_ot"
        for name, frame in frames.items()
    ):
        # Detalle_OT permite explorar ventas de materiales por sí sola, pero
        # no representa el negocio completo: faltan horas, contratos, tarifas,
        # estructura e Items. Visión del negocio se habilita solo con la red.
        return None

    collection_profile = _analyze_nominal_collection(
        frames,
        results,
        date_from=date_from,
        date_to=date_to,
        filters=filters,
    )
    if collection_profile is not None:
        return collection_profile

    kinds = classify_business_sheets(frames)
    sales_names = kinds.get("ventas", [])
    if not sales_names:
        return None
    try:
        sales, mapping = _append_sales(frames, sales_names, mappings)
    except ValueError:
        # Varias tablas denominadas venta con granos incompatibles no se deben
        # sumar silenciosamente en una visión empresarial falsa.
        return None
    if sales.empty:
        return None
    declared_period_from, declared_period_to = _declared_sales_period(frames)

    def analysis_period_mask(dates: pd.Series) -> pd.Series:
        mask = _date_filter(dates, date_from, date_to)
        if declared_period_from is not None:
            mask &= dates.ge(declared_period_from)
        if declared_period_to is not None:
            mask &= dates.le(declared_period_to)
        if declared_period_from is not None or declared_period_to is not None:
            mask &= dates.notna()
        return mask

    dimensions = _business_filter_dimensions(sales, frames, kinds, mapping, results)
    available_filters = _filter_options(dimensions)
    applied_filters = {
        key: str(value).strip()
        for key, value in (filters or {}).items()
        if key in BUSINESS_FILTER_KEYS and str(value).strip()
    }
    dimensional_filter_applied = any(key != "moneda" for key in applied_filters)
    unfiltered_sales_rows = len(sales)
    if applied_filters:
        filter_mask = pd.Series(True, index=sales.index)
        for key, selected in applied_filters.items():
            dimension = dimensions.get(key)
            if dimension is None:
                filter_mask &= False
                continue
            filter_mask &= _keys(dimension).eq(_text_key(selected))
        sales = sales.loc[filter_mask].copy()

    date_col = mapping.get("fecha") or _event_date_column(sales.columns, "venta")
    amount_col = _net_amount_column(sales.columns, domain="venta") or mapping.get("monto")
    quantity_col = mapping.get("cantidad") or find_column(sales.columns, "cantidad")
    product_key = mapping.get("producto") or _entity_key(sales.columns, "producto")
    client_key = mapping.get("cliente") or find_column(sales.columns, "id", "cliente")
    document_key = _first_column(
        sales.columns,
        (
            ("id", "documento"),
            ("numero", "boleta"),
            ("nro", "boleta"),
            ("n", "boleta"),
            ("folio",),
        ),
    )
    record_key = _first_column(
        sales.columns,
        (
            ("id", "venta"),
            ("id", "transaccion"),
            ("id", "movimiento"),
            ("id", "linea"),
        ),
        excluded=("documento",),
    )
    status_col = find_column(sales.columns, "estado")
    sales_dates = _dates(sales, date_col)
    structural = structural_total_mask(sales, date_col)
    cancelled = _status_mask(sales, status_col, r"\b(?:anulad|cancelad|void)\w*")
    base_indicator_mask = ~structural & ~cancelled
    period_mask = analysis_period_mask(sales_dates)
    if date_from or date_to:
        indicator_mask = base_indicator_mask & period_mask
    else:
        # Sin un filtro solicitado, una venta sin fecha sigue perteneciendo al
        # total global. Solo se excluye de series temporales y cruces as-of.
        indicator_mask = base_indicator_mask.copy()
        if declared_period_from is not None:
            indicator_mask &= sales_dates.isna() | sales_dates.ge(declared_period_from)
        if declared_period_to is not None:
            indicator_mask &= sales_dates.isna() | sales_dates.le(declared_period_to)
    timeline_mask = base_indicator_mask & sales_dates.notna() & period_mask
    outside_declared_period = pd.Series(False, index=sales.index)
    if declared_period_from is not None:
        outside_declared_period |= sales_dates.lt(declared_period_from)
    if declared_period_to is not None:
        outside_declared_period |= sales_dates.gt(declared_period_to)
    outside_declared_period &= ~structural & ~cancelled & sales_dates.notna()
    invalid_sales_date = ~structural & ~cancelled & sales_dates.isna()

    amount = numeric_series(sales, amount_col)
    quantity = numeric_series(sales, quantity_col)
    document_keys = (
        _keys(sales[document_key])
        if document_key
        else pd.Series(None, index=sales.index, dtype=object)
    )
    # Un documento puede contener muchas líneas. Por eso ID_Documento jamás se
    # trata por sí solo como duplicado: se revisa el ID único de transacción o,
    # cuando no existe/repite, la identidad documento + producto.
    record_keys = (
        _keys(sales[record_key])
        if record_key
        else pd.Series(None, index=sales.index, dtype=object)
    )
    repeated_record = record_keys.notna() & record_keys.duplicated(keep=False)
    product_keys = (
        _keys(sales[product_key])
        if product_key
        else pd.Series(None, index=sales.index, dtype=object)
    )
    line_keys = (
        document_keys.fillna("") + "\u241f" + product_keys.fillna("")
        if product_key
        else document_keys
    )
    repeated_line = document_keys.notna() & line_keys.duplicated(keep=False)
    duplicated_document = repeated_record | repeated_line
    duplicate_identity = record_keys.where(repeated_record, line_keys)
    duplicate_groups = int(duplicate_identity[duplicated_document].nunique())
    duplicate_extra_rows = int(duplicated_document.sum() - duplicate_groups)
    # Una línea repetida cae en conflicto material, copia idéntica o diferencia
    # limitada a observaciones. El ID técnico de la venta no forma parte de la
    # comparación porque dos cargas de la misma línea pueden generar IDs nuevos.
    conflicting_document_keys: set[str] = set()
    identical_document_keys: set[str] = set()
    observation_only_document_keys: set[str] = set()
    if duplicate_groups:
        compare_columns = [
            column for column in sales.columns
            if column not in {record_key, "_hoja_origen", "_fila_origen"}
            and "observa" not in normalized_header(column)
        ]
        all_columns = [
            column for column in sales.columns
            if column not in {record_key, "_hoja_origen", "_fila_origen"}
        ]

        def normalized_duplicate_frame(
            group: pd.DataFrame, columns: list[str]
        ) -> pd.DataFrame:
            comparable = pd.DataFrame(index=group.index)
            for column in columns:
                header = normalized_header(column)
                if "fecha" in header or "periodo" in header:
                    comparable[column] = _dates(group, column).astype(str)
                else:
                    comparable[column] = group[column].map(
                        lambda value: None if pd.isna(value) else str(value).strip()
                    )
            return comparable

        for key, group in sales.loc[duplicated_document].groupby(
            duplicate_identity[duplicated_document]
        ):
            key_str = str(key)
            if len(normalized_duplicate_frame(group, compare_columns).drop_duplicates()) > 1:
                conflicting_document_keys.add(key_str)
            elif len(normalized_duplicate_frame(group, all_columns).drop_duplicates()) > 1:
                observation_only_document_keys.add(key_str)
            else:
                identical_document_keys.add(key_str)
    conflict_groups = len(conflicting_document_keys)
    identical_groups = len(identical_document_keys)
    observation_only_groups = len(observation_only_document_keys)
    document_issue_examples = []
    for key, group in sales.loc[duplicated_document].groupby(
        duplicate_identity[duplicated_document], sort=False
    ):
        key_str = str(key)
        issue_type = (
            "conflicto"
            if key_str in conflicting_document_keys
            else "idéntico"
            if key_str in identical_document_keys
            else "solo_observación"
        )
        document_issue_examples.append({
            "id": str(group.iloc[0][document_key]) if document_key else key_str,
            "tipo": issue_type,
            "ubicaciones": [
                {
                    "hoja": str(row.get("_hoja_origen", "Ventas")),
                    "fila": _source_row_number(sales, index, row),
                }
                for index, row in group.head(8).iterrows()
            ],
        })
        if len(document_issue_examples) >= 12:
            break
    # Los hallazgos no alteran cifras silenciosamente. Las filas se conservan
    # hasta que el usuario confirme una acción de limpieza.
    certified_mask = indicator_mask.copy()

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
    cost_key = _entity_key(current_costs.columns, "producto") if current_costs is not None else None
    unit_cost_col = (
        find_column(current_costs.columns, "costo", "unitario", excluded=("ultima",))
        if current_costs is not None
        else None
    )
    product_minimum_col = (
        find_column(current_costs.columns, "stock", "minimo")
        if current_costs is not None
        else None
    )
    safe_costs, cost_reference_quality = _unique_reference(
        current_costs,
        cost_key,
        [column for column in (unit_cost_col, product_minimum_col) if column],
    )
    unit_cost, cost_source, cost_method = _applicable_unit_cost(
        sales,
        product_key,
        sales_dates,
        current_costs,
        cost_key,
        unit_cost_col,
        cost_history,
    )
    all_cost_of_sales = (quantity * unit_cost).where(
        quantity.notna() & unit_cost.notna()
    )
    historical_cost = cost_source.eq("historial_asof")
    estimated_current_cost = cost_source.eq("catalogo_actual_estimado")
    current_catalogue_only = cost_method.get("metodo") == "catalogo_actual"
    official_cost_source = historical_cost | (
        current_catalogue_only & cost_source.eq("catalogo_actual")
    )
    # If a history sheet exists, current catalogue fallbacks remain an explicit
    # estimate. They improve scenario analysis but never replace the historical
    # cost in the official gross profit.
    cost_of_sales = all_cost_of_sales.where(official_cost_source)
    estimated_cost_of_sales = all_cost_of_sales.where(
        official_cost_source | estimated_current_cost
    )
    gross_amount = amount.copy()
    accepted_return_amount = pd.Series(0.0, index=sales.index, dtype=float)
    accepted_return_cost = pd.Series(0.0, index=sales.index, dtype=float)
    accepted_returns_total = 0.0
    accepted_returns_rows = 0
    returns_name = (kinds.get("devoluciones") or [None])[0]
    returns_frame = frames.get(returns_name) if returns_name else None
    return_sale_key = None
    if returns_frame is not None and record_key:
        return_sale_key = (
            find_column(returns_frame.columns, "id", "venta")
            or find_column(returns_frame.columns, "cod", "venta")
            or find_column(returns_frame.columns, "codigo", "venta")
        )
        return_amount_col = _first_column(
            returns_frame.columns,
            (
                ("monto", "devuelto"),
                ("importe", "devuelto"),
                ("total", "devolucion"),
            ),
        )
        return_quantity_col = _first_column(
            returns_frame.columns,
            (
                ("cantidad", "devuelta"),
                ("cant", "devuelta"),
                ("unidades", "devueltas"),
            ),
        )
        return_status_col = find_column(returns_frame.columns, "estado")
        if return_sale_key and return_amount_col and return_status_col:
            return_dates = _dates(
                returns_frame,
                _event_date_column(returns_frame.columns, "devolucion"),
            )
            accepted = _status_mask(
                returns_frame,
                return_status_col,
                r"\b(?:aceptad|aprobad|procesad|confirmad)\w*",
            )
            accepted &= analysis_period_mask(return_dates)
            returned_amount = numeric_series(returns_frame, return_amount_col)
            accepted &= returned_amount.gt(0)
            return_keys = _keys(returns_frame[return_sale_key])
            accepted_returns_rows = int(accepted.sum())
            amount_by_sale = (
                pd.DataFrame({"_key": return_keys, "_amount": returned_amount})
                .loc[accepted & return_keys.notna()]
                .groupby("_key", sort=False)["_amount"]
                .sum()
            )
            accepted_returns_total = float(amount_by_sale.sum())
            accepted_return_amount = record_keys.map(amount_by_sale).fillna(0.0)

            if return_quantity_col:
                # El costo devuelto usa el costo aplicable de la venta original,
                # no un precio ni un promedio inventado en Devoluciones.
                sale_cost_reference = pd.DataFrame(
                    {"_key": record_keys, "_unit_cost": unit_cost}
                ).dropna()
                conflicts = sale_cost_reference.groupby("_key")["_unit_cost"].nunique()
                safe_sale_keys = set(conflicts[conflicts == 1].index)
                sale_cost_lookup = (
                    sale_cost_reference[
                        sale_cost_reference["_key"].isin(safe_sale_keys)
                    ]
                    .drop_duplicates("_key")
                    .set_index("_key")["_unit_cost"]
                )
                returned_quantity = numeric_series(
                    returns_frame, return_quantity_col
                )
                return_unit_cost = return_keys.map(sale_cost_lookup)
                return_cost_values = returned_quantity * return_unit_cost
                cost_by_sale = (
                    pd.DataFrame({"_key": return_keys, "_cost": return_cost_values})
                    .loc[accepted & return_keys.notna() & return_cost_values.notna()]
                    .groupby("_key", sort=False)["_cost"]
                    .sum()
                )
                accepted_return_cost = record_keys.map(cost_by_sale).fillna(0.0)

            amount = gross_amount - accepted_return_amount
            cost_of_sales = (cost_of_sales - accepted_return_cost).where(
                cost_of_sales.notna()
            )
            estimated_cost_of_sales = (
                estimated_cost_of_sales - accepted_return_cost
            ).where(estimated_cost_of_sales.notna())
    paired = indicator_mask & amount.notna() & cost_of_sales.notna()
    estimated_paired = (
        indicator_mask & amount.notna() & estimated_cost_of_sales.notna()
    )
    certified_paired = (
        certified_mask & amount.notna() & cost_of_sales.notna()
    )

    observed_sales = float(amount[indicator_mask].dropna().sum())
    certified_sales = float(amount[certified_mask].dropna().sum())
    paired_sales = float(amount[paired].sum())
    paired_cost = float(cost_of_sales[paired].sum())
    gross_profit = paired_sales - paired_cost if paired.any() else None
    gross_margin = gross_profit / paired_sales * 100 if gross_profit is not None and paired_sales else None
    estimated_paired_sales = float(amount[estimated_paired].sum())
    estimated_total_cost = float(estimated_cost_of_sales[estimated_paired].sum())
    estimated_gross_profit = (
        estimated_paired_sales - estimated_total_cost
        if estimated_paired.any()
        else None
    )
    estimated_gross_margin = (
        estimated_gross_profit / estimated_paired_sales * 100
        if estimated_gross_profit is not None and estimated_paired_sales
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
    estimated_cost_coverage = round(
        int(estimated_paired.sum())
        / max(int((indicator_mask & amount.notna()).sum()), 1)
        * 100,
        1,
    )
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
    # ``astype(str)`` turns NaT into the literal "NaT". If it remains in this
    # set, an expense with an invalid date can be matched to a sale with an
    # invalid date and enter the operating result as if both belonged to a real
    # accounting period.
    paired_months = set(
        sales_dates.loc[paired & sales_dates.notna()].dt.to_period("M").astype(str)
    )

    expenses_total = None
    expenses_period_total = None
    expenses_rows = 0
    fixed_expenses = None
    variable_expenses = None
    expense_value_basis = None
    expense_tax_excluded = None
    depreciation_expense = None
    expense_mask = pd.Series(dtype=bool)
    expense_values = pd.Series(dtype=float)
    expense_frame = frames.get((kinds.get("gastos") or [None])[0]) if kinds.get("gastos") else None
    if expense_frame is not None and not dimensional_filter_applied:
        expense_date_col = _event_date_column(expense_frame.columns, "gasto")
        expense_status = find_column(expense_frame.columns, "estado")
        expense_mask = ~_status_mask(expense_frame, expense_status, r"\b(?:anulad|cancelad)\w*")
        expense_dates = _dates(expense_frame, expense_date_col)
        # A row without a valid date cannot be assigned to an operating period.
        # It stays visible in quality controls, but not in period P&L metrics.
        expense_mask &= expense_dates.notna()
        expense_mask &= analysis_period_mask(expense_dates)
        expense_net_col = _first_column(
            expense_frame.columns,
            (("monto", "neto"), ("importe", "neto")),
        )
        expense_value_col = expense_net_col or _net_amount_column(
            expense_frame.columns, domain="gasto"
        )
        expense_value_basis = (
            "monto_neto"
            if expense_net_col
            else "monto_gasto"
            if expense_value_col and "monto" in normalized_header(expense_value_col)
            else "total_gasto"
        )
        expense_values = numeric_series(
            expense_frame,
            expense_value_col,
        )
        expenses_period_total = float(expense_values[expense_mask].dropna().sum())
        comparable_expense_mask = expense_mask & expense_dates.dt.to_period("M").astype(
            str
        ).isin(paired_months)
        expenses_total = float(expense_values[comparable_expense_mask].dropna().sum())
        expense_tax_col = find_column(expense_frame.columns, "iva")
        if expense_value_basis == "monto_neto" and expense_tax_col:
            expense_tax = numeric_series(expense_frame, expense_tax_col)
            expense_tax_excluded = float(
                expense_tax[comparable_expense_mask].dropna().sum()
            )
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
        depreciation_mask = pd.Series(False, index=expense_frame.index)
        for expense_label_col in expense_frame.columns:
            header = normalized_header(expense_label_col)
            if any(token in header for token in ("categoria", "subcategoria", "descripcion", "glosa")):
                depreciation_mask |= (
                    expense_frame[expense_label_col]
                    .astype(str)
                    .map(strip_accents_lower)
                    .str.contains(r"depreci|amortiz", regex=True, na=False)
                )
        depreciation_expense = float(
            expense_values[comparable_expense_mask & depreciation_mask]
            .dropna()
            .sum()
        )
    operating_result = (
        gross_profit - expenses_total
        if gross_profit is not None and expenses_total is not None
        else None
    )
    operating_margin = (
        operating_result / observed_sales * 100
        if operating_result is not None and observed_sales
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
        certified_operating_result / certified_sales * 100
        if certified_operating_result is not None and certified_sales
        else None
    )

    inventory_frame = frames.get((kinds.get("inventario") or [None])[0]) if kinds.get("inventario") else None
    inventory_value = None
    inventory_stock = None
    inventory_below_minimum = None
    inventory_snapshot_date = None
    inventory_cut = None
    if inventory_frame is not None and not dimensional_filter_applied:
        inventory_dates = _dates(
            inventory_frame, _event_date_column(inventory_frame.columns, "snapshot")
        )
        latest_date = inventory_dates.dropna().max() if inventory_dates.notna().any() else None
        inventory_product_key = _entity_key(inventory_frame.columns, "producto")
        # Inventario es una foto del negocio: se usa el último corte global
        # disponible. Mezclar para cada SKU su última fecha individual produciría
        # una fotografía sintética que nunca existió y sobrevaloraría el stock.
        inventory_cut = (
            inventory_frame.loc[inventory_dates.eq(latest_date)].copy()
            if latest_date is not None and pd.notna(latest_date)
            else inventory_frame.copy()
        )
        inventory_cut.attrs.update(inventory_frame.attrs)
        inventory_snapshot_date = (
            latest_date.date().isoformat()
            if latest_date is not None and pd.notna(latest_date)
            else None
        )
        inventory_values = numeric_series(
            inventory_cut, find_column(inventory_cut.columns, "valor", "inventario")
        )
        stock_col = _first_column(
            inventory_cut.columns,
            (
                ("stock", "unidades"),
                ("stock", "disponible"),
                ("stock", "fisico"),
                ("stock", "sistema"),
                ("stock",),
            ),
            excluded=("minimo", "id", "cod", "codigo"),
        )
        stock_values = numeric_series(inventory_cut, stock_col)
        minimum_values = numeric_series(
            inventory_cut,
            find_column(inventory_cut.columns, "stock", "minimo")
            or find_column(inventory_cut.columns, "minimo"),
        )
        if (
            not minimum_values.notna().any()
            and inventory_product_key
            and product_minimum_col
            and not safe_costs.empty
        ):
            minimum_lookup = dict(
                zip(
                    safe_costs["_key"],
                    numeric_series(safe_costs, product_minimum_col),
                    strict=False,
                )
            )
            minimum_values = _keys(inventory_cut[inventory_product_key]).map(
                minimum_lookup
            )
        inventory_stock = (
            float(stock_values.dropna().sum()) if stock_values.notna().any() else None
        )
        comparable_stock = stock_values.notna() & minimum_values.notna()
        inventory_below_minimum = int(
            (comparable_stock & (stock_values < minimum_values)).sum()
        )
        if inventory_values.notna().any():
            inventory_value = float(inventory_values.dropna().sum())
        elif stock_values.notna().any() and cost_key and unit_cost_col:
            if inventory_product_key and not safe_costs.empty:
                cost_lookup = dict(
                    zip(
                        safe_costs["_key"],
                        numeric_series(safe_costs, unit_cost_col),
                        strict=False,
                    )
                )
                inventory_unit_cost = _keys(
                    inventory_cut[inventory_product_key]
                ).map(cost_lookup)
                valued = stock_values.notna() & inventory_unit_cost.notna()
                if valued.any():
                    inventory_value = float(
                        (stock_values[valued] * inventory_unit_cost[valued]).sum()
                    )

    purchase_frame = frames.get((kinds.get("compras") or [None])[0]) if kinds.get("compras") else None
    purchases_total = None
    purchase_freight = None
    if purchase_frame is not None and not dimensional_filter_applied:
        purchase_mask = ~_status_mask(
            purchase_frame,
            find_column(purchase_frame.columns, "estado"),
            r"\b(?:anulad|cancelad)\w*",
        )
        purchase_mask &= analysis_period_mask(
            _dates(purchase_frame, _event_date_column(purchase_frame.columns, "compra")),
        )
        purchases = numeric_series(
            purchase_frame, _net_amount_column(purchase_frame.columns, domain="compra")
        )
        purchases_total = float(purchases[purchase_mask].dropna().sum())
        freight_col = find_column(purchase_frame.columns, "flete")
        if freight_col:
            freight_frame = pd.DataFrame(
                {
                    "flete": numeric_series(purchase_frame, freight_col).where(purchase_mask),
                    "documento": (
                        _keys(
                            purchase_frame[
                                _first_column(
                                    purchase_frame.columns,
                                    (("id", "documento", "compra"), ("id", "compra")),
                                )
                            ]
                        )
                        if _first_column(
                            purchase_frame.columns,
                            (("id", "documento", "compra"), ("id", "compra")),
                        )
                        else pd.Series(None, index=purchase_frame.index)
                    ),
                }
            ).dropna(subset=["flete"])
            if freight_frame["documento"].notna().any():
                freight_frame = freight_frame.drop_duplicates("documento")
            purchase_freight = float(freight_frame["flete"].sum())

    collections_frame = frames.get((kinds.get("cobranzas") or [None])[0]) if kinds.get("cobranzas") else None
    collected_total = None
    overpaid_documents = 0
    collection_coverage = None
    collection_duplicates_excluded = 0
    accounts_receivable = None
    overdue_receivable = None
    dso_days = None
    overdue_days = None
    orphan_collection_rows = 0
    if collections_frame is not None and not dimensional_filter_applied:
        # Exact duplicate payment rows are preserved in the source but cannot
        # be summed twice in a certifiable collection diagnostic.
        collection_rows = collections_frame.drop_duplicates().reset_index(drop=True)
        collection_duplicates_excluded = len(collections_frame) - len(collection_rows)
        collection_rows.attrs.update(collections_frame.attrs)
        payment_status = _first_column(
            collection_rows.columns,
            (("estado", "pago"), ("estado", "cobranza"), ("estado",)),
        )
        payment_date = _event_date_column(collection_rows.columns, "pago")
        payment_amount = numeric_series(
            collection_rows,
            _first_column(
                collection_rows.columns,
                (("monto", "pagado"), ("monto", "pago"), ("importe", "pagado")),
            ),
        )
        paid_status = _status_mask(
            collection_rows, payment_status, r"\b(?:pagad|aplicad|cobrad)\w*"
        )
        applied = (paid_status | payment_amount.gt(0)) & analysis_period_mask(
            _dates(collection_rows, payment_date)
        )
        collected_total = float(payment_amount[applied].dropna().sum())
        payment_document = find_column(collection_rows.columns, "id", "documento")
        document_amount = numeric_series(
            collection_rows,
            _first_column(
                collection_rows.columns,
                (("monto", "documento"), ("total", "documento"), ("monto",)),
            ),
        )
        collection_keys = (
            _keys(collection_rows[payment_document])
            if payment_document
            else pd.Series(None, index=collection_rows.index)
        )
        valid_sales_documents = set(
            document_keys[indicator_mask & document_keys.notna()]
        )
        matched_document = (
            collection_keys.isin(valid_sales_documents)
            if valid_sales_documents
            else collection_keys.notna()
        )
        orphan_collection_rows = int(
            (collection_keys.notna() & ~matched_document).sum()
        )
        positive_documents = matched_document & document_amount.gt(0)
        overpaid_documents = int(
            (
                positive_documents
                & payment_amount.gt(document_amount * 1.005 + 2)
            ).sum()
        )
        document_total = float(document_amount[positive_documents].sum())
        collection_coverage = (
            min(float(payment_amount[positive_documents].fillna(0).sum()) / document_total * 100, 999.9)
            if document_total
            else None
        )
        status_values = (
            collection_rows[payment_status].astype(str).map(strip_accents_lower)
            if payment_status
            else pd.Series("", index=collection_rows.index)
        )
        open_mask = positive_documents & ~status_values.str.contains(
            r"\b(?:pagad|aplicad|cobrad)\w*", regex=True, na=False
        )
        overdue_mask = positive_documents & status_values.str.contains(
            r"\b(?:vencid|moros|atrasad)\w*", regex=True, na=False
        )
        accounts_receivable = float(document_amount[open_mask].sum())
        overdue_receivable = float(document_amount[overdue_mask].sum())
        issue_date = _dates(
            collection_rows,
            _event_date_column(collection_rows.columns, "emision"),
        )
        paid_dates = _dates(collection_rows, payment_date)
        collection_days = (paid_dates - issue_date).dt.days
        realized = positive_documents & paid_status & collection_days.ge(0)
        dso_days = (
            float(collection_days[realized].mean()) if realized.any() else None
        )
        arrears = numeric_series(
            collection_rows, find_column(collection_rows.columns, "dias", "mora")
        )
        overdue_days = (
            float(arrears[overdue_mask].mean()) if overdue_mask.any() else None
        )

    campaign_frame = frames.get((kinds.get("campanas") or [None])[0]) if kinds.get("campanas") else None
    marketing_investment = None
    marketing_ctr = None
    marketing_conversion_rate = None
    marketing_cost_per_conversion = None
    if campaign_frame is not None:
        investment = numeric_series(
            campaign_frame, find_column(campaign_frame.columns, "inversion")
        )
        impressions = numeric_series(
            campaign_frame, find_column(campaign_frame.columns, "impresion")
        )
        clicks = numeric_series(
            campaign_frame, find_column(campaign_frame.columns, "clic")
        )
        conversions = numeric_series(
            campaign_frame, find_column(campaign_frame.columns, "conversion")
        )
        investment_total = float(investment.dropna().sum())
        impression_total = float(impressions.dropna().sum())
        clicks_total = float(clicks.dropna().sum())
        conversions_total = float(conversions.dropna().sum())
        marketing_investment = investment_total
        marketing_ctr = (
            clicks_total / impression_total * 100 if impression_total else None
        )
        marketing_conversion_rate = (
            conversions_total / clicks_total * 100 if clicks_total else None
        )
        marketing_cost_per_conversion = (
            investment_total / conversions_total if conversions_total else None
        )

    month_frame = pd.DataFrame(
        {
            "mes": sales_dates.dt.to_period("M").astype(str).where(timeline_mask),
            "ingresos": amount.where(timeline_mask),
            "costo": cost_of_sales.where(timeline_mask),
        }
    )
    ebitda = (
        operating_result + depreciation_expense
        if operating_result is not None and depreciation_expense is not None
        else None
    )
    month_frame.loc[sales_dates.isna(), "mes"] = None
    month_frame["ingresos_pareados"] = amount.where(paired)
    monthly = month_frame.dropna(subset=["mes"]).groupby("mes").sum(numeric_only=True)
    expense_monthly: dict[str, float] = {}
    if expense_frame is not None and not dimensional_filter_applied:
        expense_dates = _dates(expense_frame, find_column(expense_frame.columns, "fecha", "gasto"))
        exp = pd.DataFrame(
            {
                "mes": expense_dates.dt.to_period("M").astype(str),
                "valor": expense_values.where(expense_mask),
            }
        )
        exp.loc[expense_dates.isna(), "mes"] = None
        expense_monthly = exp.dropna(subset=["mes"]).groupby("mes")["valor"].sum().to_dict()
    valid_timeline_dates = sales_dates.where(timeline_mask).dropna()
    coverage_by_month: dict[str, int] = {}
    if not valid_timeline_dates.empty:
        coverage_frame = pd.DataFrame({
            "mes": valid_timeline_dates.dt.to_period("M").astype(str),
            "dia": valid_timeline_dates.dt.day,
        })
        coverage_by_month = {
            str(month): int(day)
            for month, day in coverage_frame.groupby("mes")["dia"].max().items()
        }

    monthly_rows: list[dict[str, Any]] = []
    for month, row in monthly.sort_index().iterrows():
        month_sales = float(row["ingresos"])
        month_cost = float(row["costo"])
        month_paired_sales = float(row["ingresos_pareados"])
        month_profit = month_paired_sales - month_cost if month_paired_sales or month_cost else None
        month_expense = float(expense_monthly.get(str(month), 0.0)) if expense_frame is not None else None
        period = pd.Period(str(month), freq="M")
        coverage_day = int(coverage_by_month.get(str(month), period.days_in_month))
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
                "parcial": False,
                "cobertura_hasta_dia": coverage_day,
                "dias_del_mes": int(period.days_in_month),
            }
        )
    if monthly_rows:
        latest_month = monthly_rows[-1]
        latest_month["parcial"] = bool(
            latest_month["cobertura_hasta_dia"] < latest_month["dias_del_mes"]
        )
        if latest_month["parcial"] and len(monthly_rows) >= 2:
            previous_month = monthly_rows[-2]
            current_days = max(int(latest_month["cobertura_hasta_dia"]), 1)
            previous_days = max(int(previous_month["dias_del_mes"]), 1)
            current_daily = float(latest_month["ventas"]) / current_days
            previous_daily = float(previous_month["ventas"]) / previous_days
            latest_month["ritmo_diario_ventas"] = round(current_daily, 2)
            latest_month["ritmo_diario_mes_anterior"] = round(previous_daily, 2)
            latest_month["variacion_ritmo_pct"] = (
                round((current_daily - previous_daily) / abs(previous_daily) * 100, 2)
                if previous_daily
                else None
            )
            latest_month["proyeccion_ritmo_mes_completo"] = round(
                current_daily * int(latest_month["dias_del_mes"]), 2
            )

    products_frame = frames.get((kinds.get("productos") or [None])[0]) if kinds.get("productos") else None
    clients_frame = frames.get((kinds.get("clientes") or [None])[0]) if kinds.get("clientes") else None
    branches_frame = frames.get((kinds.get("sucursales") or [None])[0]) if kinds.get("sucursales") else None
    sellers_frame = frames.get((kinds.get("vendedores") or [None])[0]) if kinds.get("vendedores") else None
    suppliers_frame = frames.get((kinds.get("proveedores") or [None])[0]) if kinds.get("proveedores") else None

    product_ref_key = _entity_key(products_frame.columns, "producto") if products_frame is not None else None
    client_ref_key = _entity_key(clients_frame.columns, "cliente") if clients_frame is not None else None
    branch_ref_key = _entity_key(branches_frame.columns, "sucursal") if branches_frame is not None else None
    seller_ref_key = (
        _entity_key(sellers_frame.columns, "vendedor")
        or _entity_key(sellers_frame.columns, "trabajador")
        if sellers_frame is not None
        else None
    )

    product_col = mapping.get("producto") or find_column(
        sales.columns, "producto", excluded=("sku", "id")
    )
    channel_col = mapping.get("canal") or find_column(sales.columns, "canal")
    branch_col = mapping.get("sucursal") or _entity_key(sales.columns, "sucursal")
    client_col = mapping.get("cliente") or _entity_key(sales.columns, "cliente")
    seller_col = mapping.get("vendedor") or _entity_key(sales.columns, "vendedor")

    product_name_ref = (
        find_column(products_frame.columns, "nombre", "producto")
        or find_column(products_frame.columns, "descripcion", "producto")
        or find_column(
            products_frame.columns,
            "producto",
            excluded=("id", "sku", "codigo", "código", "categoria"),
        )
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
        or find_column(sellers_frame.columns, "nombre", "trabajador")
        or find_column(sellers_frame.columns, "nombre")
        or find_column(
            sellers_frame.columns,
            "vendedor",
            excluded=("id", "cod", "codigo"),
        )
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
        "vendedores": _group_profit(
            analytic_sales, seller_group_col, analytic_amount, analytic_cost, 60
        ),
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

    historical_integrity = None
    if cost_history is not None:
        historical_informed = indicator_mask & product_keys.notna()
        historical_valid = historical_informed & historical_cost
        historical_missing = historical_informed & ~historical_cost
        historical_integrity = {
            "relacion": "Ventas → Historial de costos (vigencia)",
            "filas": int(historical_informed.sum()),
            "validas": int(historical_valid.sum()),
            "huerfanas": int(historical_missing.sum()),
            "sin_clave": int((indicator_mask & product_keys.isna()).sum()),
            "cobertura_pct": round(
                int(historical_valid.sum())
                / max(int(historical_informed.sum()), 1)
                * 100,
                1,
            ),
            "ejemplos": sorted(
                {
                    str(value)
                    for value in sales.loc[historical_missing, product_key].head(8)
                }
            )
            if product_key
            else [],
            "metodo": "vigencia_por_fecha",
        }
    goals_frame_for_relation = (
        frames.get((kinds.get("metas") or [None])[0])
        if kinds.get("metas")
        else None
    )
    campaign_frame_for_relation = (
        frames.get((kinds.get("campanas") or [None])[0])
        if kinds.get("campanas")
        else None
    )
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
        historical_integrity,
        _relation_quality(products_frame, _entity_key(products_frame.columns, "proveedor") if products_frame is not None else None, suppliers_frame, _entity_key(suppliers_frame.columns, "proveedor") if suppliers_frame is not None else None, "Productos → Proveedores"),
        _relation_quality(purchase_frame, find_column(purchase_frame.columns, "sku", "producto") if purchase_frame is not None else None, products_frame, product_ref_key, "Compras → Productos"),
        _relation_quality(purchase_frame, _entity_key(purchase_frame.columns, "proveedor") if purchase_frame is not None else None, suppliers_frame, _entity_key(suppliers_frame.columns, "proveedor") if suppliers_frame is not None else None, "Compras → Proveedores"),
        _relation_quality(collections_frame, find_column(collections_frame.columns, "id", "documento") if collections_frame is not None else None, sales.loc[~structural], document_key, "Cobranzas → Ventas"),
        _relation_quality(returns_frame, return_sale_key, sales.loc[~structural], record_key, "Devoluciones → Ventas"),
        _relation_quality(inventory_cut, _entity_key(inventory_cut.columns, "producto") if inventory_cut is not None else None, products_frame, product_ref_key, "Inventario → Productos"),
        _relation_quality(clients_frame, _entity_key(clients_frame.columns, "vendedor") if clients_frame is not None else None, sellers_frame, seller_ref_key, "Clientes → Vendedores"),
        _relation_quality(sellers_frame, _entity_key(sellers_frame.columns, "sucursal") if sellers_frame is not None else None, branches_frame, branch_ref_key, "Vendedores → Sucursales"),
        _relation_quality(expense_frame, _entity_key(expense_frame.columns, "sucursal") if expense_frame is not None else None, branches_frame, branch_ref_key, "Gastos → Sucursales"),
        _relation_quality(goals_frame_for_relation, _entity_key(goals_frame_for_relation.columns, "vendedor") if goals_frame_for_relation is not None else None, sellers_frame, seller_ref_key, "Metas → Vendedores"),
        _relation_quality(goals_frame_for_relation, _entity_key(goals_frame_for_relation.columns, "sucursal") if goals_frame_for_relation is not None else None, branches_frame, branch_ref_key, "Metas → Sucursales"),
        _relation_quality(campaign_frame_for_relation, find_column(campaign_frame_for_relation.columns, "id", "sucursal") if campaign_frame_for_relation is not None else None, branches_frame, branch_ref_key, "Campañas → Sucursales"),
    ]
    integrity = [item for item in integrity if item is not None]

    formula_controls = _formula_controls(frames, kinds)
    formula_issues = sum(item["filas_inconsistentes"] for item in formula_controls)
    orphan_rows = sum(item["huerfanas"] + item["sin_clave"] for item in integrity)

    cost_values = numeric_series(current_costs, unit_cost_col) if current_costs is not None else pd.Series(dtype=float)
    upper = _cost_outlier_limit(cost_values)
    negative_cost_locations = []
    if current_costs is not None:
        source_rows = list(current_costs.attrs.get("adsveris_source_rows", []))
        for index in cost_values.index[cost_values < 0][:12]:
            position = current_costs.index.get_loc(index)
            negative_cost_locations.append({
                "hoja": current_cost_name,
                "fila": int(source_rows[position]) if len(source_rows) == len(current_costs) else int(position) + 2,
                "valor": round(float(cost_values.loc[index]), 2),
                "clave": str(current_costs.loc[index, cost_key]) if cost_key else None,
            })
    cost_quality = {
        **cost_reference_quality,
        **cost_method,
        "faltantes": int(cost_values.isna().sum()),
        "negativos": int((cost_values < 0).sum()),
        "ceros": int((cost_values == 0).sum()),
        "extremos": int((cost_values > upper).sum()) if upper is not None else 0,
        "limite_extremo": round(upper, 2) if upper is not None else None,
        "ventas_con_costo_pct": cost_coverage,
        "ventas_certificables_con_costo_pct": certified_cost_coverage,
        "filas_costo_historico": int((cost_source == "historial_asof").sum()),
        "filas_costo_actual": int((cost_source == "catalogo_actual").sum()),
        "filas_costo_actual_estimado": int(
            (cost_source == "catalogo_actual_estimado").sum()
        ),
    }

    goals_frame = frames.get((kinds.get("metas") or [None])[0]) if kinds.get("metas") else None
    goals = {
        "disponible": False,
        "meta_venta": None,
        "venta_comparable": None,
        "cumplimiento_pct": None,
        "meta_margen_pct": None,
        "meta_nuevos_clientes": None,
        "metas_cumplidas": None,
        "metas_evaluadas": None,
        "por_mes": [],
        "nota": "No hay una hoja de metas comparable.",
    }
    if goals_frame is not None and not dimensional_filter_applied:
        goal_date_col = _event_date_column(goals_frame.columns)
        goal_amount_col = find_column(goals_frame.columns, "meta", "venta")
        goal_margin_col = find_column(goals_frame.columns, "meta", "margen")
        goal_clients_col = find_column(goals_frame.columns, "meta", "nuevo", "cliente")
        goal_branch_col = find_column(goals_frame.columns, "id", "sucursal")
        goal_seller_col = (
            find_column(goals_frame.columns, "id", "vendedor")
            or find_column(goals_frame.columns, "cod", "vendedor")
            or find_column(goals_frame.columns, "codigo", "vendedor")
        )
        goal_dates = _dates(goals_frame, goal_date_col)
        goal_period = analysis_period_mask(goal_dates)
        goal_amount = numeric_series(goals_frame, goal_amount_col)
        goal_margin = numeric_series(goals_frame, goal_margin_col)
        goal_clients = numeric_series(goals_frame, goal_clients_col)
        comparable_goals = goal_period & goal_dates.notna() & goal_amount.notna()
        if comparable_goals.any():
            goal_month = goal_dates.dt.to_period("M").astype(str)
            goal_dimension = (
                (goal_seller_col, seller_col)
                if goal_seller_col
                and seller_col
                and goal_seller_col in goals_frame.columns
                and seller_col in sales.columns
                else (goal_branch_col, branch_col)
                if goal_branch_col
                and branch_col
                and goal_branch_col in goals_frame.columns
                and branch_col in sales.columns
                else (None, None)
            )
            goal_dimension_col, sales_dimension_col = goal_dimension
            target_detail = pd.DataFrame(
                {
                    "mes": goal_month.where(comparable_goals),
                    "dimension": (
                        _keys(goals_frame[goal_dimension_col])
                        if goal_dimension_col
                        else "todas"
                    ),
                    "meta": goal_amount,
                }
            ).dropna(subset=["mes", "meta"])
            actual_detail = pd.DataFrame(
                {
                    "mes": sales_dates.dt.to_period("M").astype(str).where(timeline_mask),
                    "dimension": (
                        _keys(sales[sales_dimension_col])
                        if sales_dimension_col
                        else "todas"
                    ),
                    "venta": amount.where(timeline_mask),
                }
            ).dropna(subset=["mes", "venta"])
            target_by_key = target_detail.groupby(["mes", "dimension"], dropna=False)[
                "meta"
            ].sum()
            actual_by_key = actual_detail.groupby(["mes", "dimension"], dropna=False)[
                "venta"
            ].sum()
            goal_comparison = target_by_key.rename("meta").to_frame()
            goal_comparison["venta"] = actual_by_key.reindex(
                goal_comparison.index
            ).fillna(0)
            goal_comparison["cumplida"] = (
                goal_comparison["venta"] >= goal_comparison["meta"]
            )
            target_by_month = goal_comparison.groupby(level="mes")["meta"].sum()
            actual_by_month = goal_comparison.groupby(level="mes")["venta"].sum()
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
                "metas_cumplidas": int(goal_comparison["cumplida"].sum()),
                "metas_evaluadas": int(len(goal_comparison)),
                "por_mes": monthly_goals,
                "nota": "Las ventas se comparan solo en los meses que tienen una meta informada.",
            }
            goal_index = {row["mes"]: row for row in monthly_goals}
            for row in monthly_rows:
                match = goal_index.get(row["mes"])
                if match:
                    row["meta_venta"] = match["meta_venta"]
                    row["cumplimiento_meta_pct"] = match["cumplimiento_pct"]

    monthly_fixed_expenses = (
        fixed_expenses / len(paired_months)
        if fixed_expenses is not None and paired_months
        else None
    )
    break_even_sales = (
        expenses_total / (gross_margin / 100)
        if expenses_total is not None
        and gross_margin is not None
        and gross_margin > 0
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
            "Punto de equilibrio del periodo",
            break_even_sales,
            "partial" if break_even_sales is not None else "unavailable",
            "Gastos operacionales / margen bruto",
            "Aproximación sobre la base de ventas con costo histórico relacionado.",
            ["ventas", "costos históricos", "gastos operacionales"],
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
        _ratio(
            "ebitda",
            "EBITDA",
            ebitda,
            "partial" if ebitda is not None else "unavailable",
            "Resultado operacional + depreciación + amortización",
            (
                "Se calcula con las categorías de gasto que declaran depreciación o amortización."
                if ebitda is not None
                else "Falta clasificación contable de depreciación y amortización."
            ),
            ["resultado operacional", "depreciación", "amortización"],
        ),
    ]

    decisions: list[dict[str, Any]] = []
    if duplicate_extra_rows:
        decisions.append({
            "severidad": "alta",
            "titulo": f"Revisar {duplicate_groups} líneas de negocio repetidas",
            "evidencia": f"Hay {duplicate_extra_rows} filas adicionales y {conflict_groups} grupos con contenido distinto.",
            "accion": "Revisa los casos en Limpieza; se conservaron en los totales hasta que confirmes una acción.",
            "confianza": 1.0,
        })
    date_issue_rows = int(outside_declared_period.sum() + invalid_sales_date.sum())
    if date_issue_rows:
        decisions.append({
            "severidad": "media",
            "titulo": "Corregir ventas sin un periodo contable válido",
            "evidencia": (
                f"{int(invalid_sales_date.sum())} filas no tienen fecha válida y "
                f"{int(outside_declared_period.sum())} están fuera del periodo declarado."
            ),
            "accion": (
                "Corrige esas fechas en Limpieza; las fechas inválidas se conservan "
                "en el total global, pero no entran a meses ni costos por vigencia."
            ),
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
        decisions.append({
            "severidad": "alta",
            "titulo": "Validar costos que distorsionan el margen",
            "evidencia": f"{cost_quality['negativos']} negativos, {cost_quality['ceros']} en cero y {cost_quality['extremos']} extremos.",
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

    quality_penalty = min(
        45.0,
        duplicate_groups * 0.15
        + formula_issues * 0.015
        + orphan_rows * 0.01
        + date_issue_rows * 0.05,
    )
    confidence = max(0.0, min(100.0, certified_cost_coverage - quality_penalty))
    certification = (
        "blocked"
        if duplicate_groups or conflict_groups or certified_cost_coverage < 95 or cost_quality["negativos"]
        else "partial"
        if formula_issues or orphan_rows or date_issue_rows or certified_cost_coverage < 99.5
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
                (kinds.get("campanas") or [None])[0],
            )
            if name
        ],
    }
    period_dates = sales_dates[indicator_mask & sales_dates.notna()]
    period_start = (
        date_from
        or (
            declared_period_from.date().isoformat()
            if declared_period_from is not None
            else period_dates.min().date().isoformat()
            if not period_dates.empty
            else None
        )
    )
    period_end = (
        date_to
        or (
            declared_period_to.date().isoformat()
            if declared_period_to is not None
            else period_dates.max().date().isoformat()
            if not period_dates.empty
            else None
        )
    )
    complete_months = [row for row in monthly_rows if not row.get("parcial")]
    latest_complete = complete_months[-1] if complete_months else None
    previous_complete = complete_months[-2] if len(complete_months) >= 2 else None
    indicator_rows = int((indicator_mask & amount.notna()).sum())
    indicator_documents = (
        int(document_keys[indicator_mask & document_keys.notna()].nunique())
        if document_key
        else indicator_rows
    )
    indicator_units = (
        float(quantity[indicator_mask & quantity.notna()].sum())
        if quantity_col and quantity.notna().any()
        else None
    )
    indicator_clients = (
        int(_keys(sales.loc[indicator_mask, client_key]).dropna().nunique())
        if client_key
        else None
    )
    ticket_average = (
        observed_sales / indicator_documents if indicator_documents else None
    )
    currency_options = available_filters.get("moneda", [])
    selected_currency = applied_filters.get("moneda")
    currency_label = (
        selected_currency
        or (currency_options[0] if len(currency_options) == 1 else None)
        or "CLP"
    )
    mixed_unfiltered_currency = len(currency_options) > 1 and not selected_currency
    currency_unit = currency_label
    ticket_currency_unit = (
        f"{currency_label}/documento"
        if document_key
        else f"{currency_label}/línea"
    )
    available_source_names = sorted(used_sheets)
    cost_warning = (
        []
        if certified_cost_coverage >= 99.5
        else [
            "Se calcula solo sobre ventas con costo válido; las ventas sin costo "
            "no se tratan como costo cero."
        ]
    )
    partial_period_warning = (
        [
            "El último mes es parcial; las comparaciones usan los dos últimos "
            "meses completos."
        ]
        if monthly_rows and monthly_rows[-1].get("parcial")
        else []
    )

    indicator_catalog_rows = [
        _indicator_contract(
            "ventas_netas",
            "ventas",
            "Ventas netas",
            observed_sales,
            currency_unit,
            period_from=period_start,
            period_to=period_end,
            formula="Σ monto neto de documentos no anulados y no estructurales",
            numerator=observed_sales,
            coverage=100.0 if amount_col else None,
            warnings=partial_period_warning,
            required=["fecha", "monto neto", "estado"],
            sources=sales_names,
            polarity="higher_is_better",
            visualizations=["kpi", "linea_temporal", "barras_comparativas"],
        ),
        _indicator_contract(
            "ventas_ultimo_mes_completo",
            "ventas",
            "Ventas del último mes completo",
            latest_complete.get("ventas") if latest_complete else None,
            currency_unit,
            period_from=latest_complete.get("mes") if latest_complete else None,
            period_to=latest_complete.get("mes") if latest_complete else None,
            prior_value=previous_complete.get("ventas")
            if previous_complete
            else None,
            formula="Σ ventas del último mes con cobertura completa",
            warnings=partial_period_warning,
            required=["fecha", "monto neto"],
            sources=sales_names,
            polarity="higher_is_better",
            visualizations=["kpi_tendencia", "linea_temporal"],
        ),
        _indicator_contract(
            "ticket_promedio_documento",
            "ventas",
            (
                "Ticket promedio por documento"
                if document_key
                else "Venta promedio por línea"
            ),
            ticket_average,
            ticket_currency_unit,
            period_from=period_start,
            period_to=period_end,
            formula=(
                "Ventas netas ÷ documentos únicos"
                if document_key
                else "Ventas netas ÷ líneas con monto"
            ),
            numerator=observed_sales,
            denominator=indicator_documents,
            status="available" if ticket_average is not None else "unavailable",
            warnings=(
                []
                if document_key
                else [
                    "No existe un documento único: este promedio es por línea "
                    "vendida y no se presenta como ticket."
                ]
            ),
            required=(
                ["monto neto", "ID documento"]
                if document_key
                else ["monto neto"]
            ),
            sources=sales_names,
            polarity="neutral",
            visualizations=["kpi"],
        ),
        _indicator_contract(
            "unidades_vendidas",
            "ventas",
            "Unidades vendidas",
            indicator_units,
            "unidades",
            period_from=period_start,
            period_to=period_end,
            formula="Σ cantidad; las devoluciones conservan su signo",
            numerator=indicator_units,
            required=["cantidad", "estado"],
            sources=sales_names,
            polarity="higher_is_better",
            visualizations=["kpi", "linea_temporal", "barras_comparativas"],
        ),
        _indicator_contract(
            "costo_venta",
            "rentabilidad",
            "Costo de ventas conocido",
            paired_cost if paired.any() else None,
            currency_unit,
            period_from=period_start,
            period_to=period_end,
            formula="Σ (cantidad × costo unitario vigente a la fecha)",
            numerator=paired_cost if paired.any() else None,
            coverage=certified_cost_coverage,
            warnings=cost_warning,
            required=["cantidad", "fecha", "clave producto", "costo unitario vigente"],
            sources=[
                name
                for name in (cost_history_name, current_cost_name, *sales_names)
                if name
            ],
            polarity="lower_is_better",
            visualizations=["kpi", "barras_apiladas", "linea_temporal"],
        ),
        _indicator_contract(
            "utilidad_bruta",
            "rentabilidad",
            "Utilidad bruta",
            gross_profit,
            currency_unit,
            period_from=period_start,
            period_to=period_end,
            formula="Ventas pareadas − costo de ventas conocido",
            numerator=gross_profit,
            denominator=paired_sales,
            coverage=certified_cost_coverage,
            warnings=cost_warning,
            required=["ventas", "costo de ventas"],
            sources=available_source_names,
            polarity="higher_is_better",
            visualizations=["kpi", "linea_temporal", "ranking"],
        ),
        _indicator_contract(
            "margen_bruto_pct",
            "rentabilidad",
            "Margen bruto",
            gross_margin,
            "%",
            period_from=period_start,
            period_to=period_end,
            formula="Utilidad bruta ÷ ventas pareadas × 100",
            numerator=gross_profit,
            denominator=paired_sales,
            variation_type="puntos_porcentuales",
            coverage=certified_cost_coverage,
            warnings=cost_warning,
            required=["ventas pareadas", "utilidad bruta"],
            sources=available_source_names,
            polarity="higher_is_better",
            visualizations=["kpi", "linea_porcentual", "matriz_volumen_margen"],
        ),
        _indicator_contract(
            "cobertura_costos_pct",
            "rentabilidad",
            "Cobertura de costos",
            certified_cost_coverage,
            "%",
            period_from=period_start,
            period_to=period_end,
            formula="Filas de venta con costo válido ÷ filas de venta con monto × 100",
            numerator=int(certified_paired.sum()),
            denominator=int((certified_mask & amount.notna()).sum()),
            variation_type="puntos_porcentuales",
            coverage=100.0,
            status="available" if certified_cost_coverage >= 99.5 else "partial",
            warnings=cost_warning,
            required=["ventas", "costos"],
            sources=available_source_names,
            polarity="higher_is_better",
            visualizations=["kpi", "barra_progreso"],
        ),
        _indicator_contract(
            "ebitda",
            "rentabilidad",
            "EBITDA",
            ebitda,
            currency_unit,
            period_from=period_start,
            period_to=period_end,
            formula="Resultado operacional + depreciación y amortización",
            numerator=ebitda,
            coverage=certified_cost_coverage if ebitda is not None else None,
            warnings=cost_warning,
            required=["resultado operacional", "depreciación y amortización"],
            sources=available_source_names,
            polarity="higher_is_better",
            visualizations=["kpi", "linea_temporal"],
        ),
        _indicator_contract(
            "punto_equilibrio",
            "rentabilidad",
            "Punto de equilibrio",
            break_even_sales,
            currency_unit,
            period_from=period_start,
            period_to=period_end,
            formula="Gastos operacionales ÷ margen bruto",
            numerator=expenses_total,
            denominator=(gross_margin / 100) if gross_margin is not None else None,
            coverage=certified_cost_coverage if break_even_sales is not None else None,
            warnings=cost_warning,
            required=["gastos operacionales", "margen bruto"],
            sources=available_source_names,
            polarity="lower_is_better",
            visualizations=["kpi", "referencia_en_ventas"],
        ),
        _indicator_contract(
            "flujo_neto_caja",
            "caja",
            "Flujo neto de caja",
            None,
            currency_unit,
            period_from=period_start,
            period_to=period_end,
            formula="Ingresos de caja − egresos de caja",
            status="unavailable",
            warnings=[
                "Cobranzas no equivale por sí sola al flujo de caja: faltan todos "
                "los egresos y sus fechas de pago."
            ],
            required=["ingresos de caja", "egresos de caja", "fecha de pago"],
            sources=[],
            polarity="higher_is_better",
            visualizations=["linea_temporal", "saldo_acumulado"],
        ),
        _indicator_contract(
            "cuentas_por_cobrar",
            "cobranza",
            "Cuentas por cobrar",
            accounts_receivable,
            currency_unit,
            period_from=period_start,
            period_to=period_end,
            formula="Σ saldo abierto de documentos válidos",
            numerator=accounts_receivable,
            required=["ID documento", "monto documento", "estado de pago"],
            sources=[name for name in ((kinds.get("cobranzas") or [None])[0], *sales_names) if name],
            polarity="lower_is_better",
            visualizations=["kpi", "barras_antiguedad"],
        ),
        _indicator_contract(
            "cobranza_vencida",
            "cobranza",
            "Cobranza vencida",
            overdue_receivable,
            currency_unit,
            period_from=period_start,
            period_to=period_end,
            formula="Σ saldo de documentos vencidos",
            numerator=overdue_receivable,
            denominator=accounts_receivable,
            required=["saldo", "fecha de vencimiento o estado vencido"],
            sources=[(kinds.get("cobranzas") or [None])[0]]
            if kinds.get("cobranzas")
            else [],
            polarity="lower_is_better",
            visualizations=["kpi", "donut", "barras_antiguedad"],
        ),
        _indicator_contract(
            "dso_dias",
            "cobranza",
            "Días promedio de cobro",
            dso_days,
            "días",
            period_from=period_start,
            period_to=period_end,
            formula="Promedio(fecha de pago − fecha de emisión) en documentos cobrados",
            numerator=dso_days,
            required=["fecha emisión", "fecha pago", "ID documento"],
            sources=[(kinds.get("cobranzas") or [None])[0]]
            if kinds.get("cobranzas")
            else [],
            polarity="lower_is_better",
            visualizations=["kpi", "linea_temporal"],
        ),
        _indicator_contract(
            "mora_promedio_dias",
            "cobranza",
            "Mora promedio vencida",
            overdue_days,
            "días",
            period_from=period_start,
            period_to=period_end,
            formula="Promedio de días de mora en documentos vencidos",
            numerator=overdue_days,
            required=["días de mora", "estado vencido"],
            sources=[(kinds.get("cobranzas") or [None])[0]]
            if kinds.get("cobranzas")
            else [],
            polarity="lower_is_better",
            visualizations=["kpi", "barras_antiguedad"],
        ),
        _indicator_contract(
            "porcentaje_cartera_vencida",
            "cobranza",
            "Cartera vencida",
            (
                overdue_receivable / accounts_receivable * 100
                if overdue_receivable is not None
                and accounts_receivable is not None
                and accounts_receivable > 0
                else None
            ),
            "%",
            period_from=period_start,
            period_to=period_end,
            formula="Saldo vencido ÷ cuentas por cobrar × 100",
            numerator=overdue_receivable,
            denominator=accounts_receivable,
            variation_type="puntos_porcentuales",
            required=["saldo abierto", "saldo vencido"],
            sources=[(kinds.get("cobranzas") or [None])[0]]
            if kinds.get("cobranzas")
            else [],
            polarity="lower_is_better",
            visualizations=["kpi", "donut"],
        ),
        _indicator_contract(
            "stock_valorizado",
            "inventario",
            "Inventario valorizado",
            inventory_value,
            currency_unit,
            period_from=inventory_snapshot_date,
            period_to=inventory_snapshot_date,
            formula="Σ stock disponible × costo unitario ponderado, último corte",
            numerator=inventory_value,
            warnings=[]
            if inventory_snapshot_date
            else ["No se identificó una fecha de corte; se usa el conjunto disponible."],
            required=["stock", "costo unitario", "fecha de snapshot"],
            sources=[(kinds.get("inventario") or [None])[0]]
            if kinds.get("inventario")
            else [],
            polarity="neutral",
            visualizations=["kpi", "ranking", "barras"],
        ),
        _indicator_contract(
            "rotacion_inventario",
            "inventario",
            "Rotación de inventario",
            inventory_turnover,
            "veces",
            period_from=period_start,
            period_to=period_end,
            formula="Costo de ventas conocido ÷ inventario del último corte",
            numerator=paired_cost if paired.any() else None,
            denominator=inventory_value,
            coverage=certified_cost_coverage if inventory_turnover is not None else None,
            status="partial" if inventory_turnover is not None else "unavailable",
            warnings=[
                "Es una aproximación con inventario de cierre; el promedio de "
                "inventario requiere al menos dos cortes comparables."
            ] if inventory_turnover is not None else [],
            required=["costo de ventas", "inventario promedio"],
            sources=available_source_names,
            polarity="neutral",
            visualizations=["kpi", "linea_temporal"],
        ),
        _indicator_contract(
            "stock_disponible",
            "inventario",
            "Stock disponible",
            inventory_stock,
            "unidades",
            period_from=inventory_snapshot_date,
            period_to=inventory_snapshot_date,
            formula="Σ stock disponible del último corte",
            numerator=inventory_stock,
            required=["stock", "fecha de snapshot"],
            sources=[(kinds.get("inventario") or [None])[0]]
            if kinds.get("inventario")
            else [],
            polarity="neutral",
            visualizations=["kpi", "ranking"],
        ),
        _indicator_contract(
            "registros_bajo_minimo",
            "inventario",
            "Registros bajo stock mínimo",
            inventory_below_minimum,
            "registros",
            period_from=inventory_snapshot_date,
            period_to=inventory_snapshot_date,
            formula="Conteo de registros donde stock disponible < stock mínimo",
            numerator=inventory_below_minimum,
            required=["stock disponible", "stock mínimo"],
            sources=[(kinds.get("inventario") or [None])[0]]
            if kinds.get("inventario")
            else [],
            polarity="lower_is_better",
            visualizations=["kpi", "ranking_alertas"],
        ),
        _indicator_contract(
            "dias_inventario_aprox",
            "inventario",
            "Días de inventario aproximados",
            365 / inventory_turnover
            if inventory_turnover is not None and inventory_turnover > 0
            else None,
            "días",
            period_from=period_start,
            period_to=period_end,
            formula="365 ÷ rotación aproximada",
            denominator=inventory_turnover,
            coverage=certified_cost_coverage if inventory_turnover is not None else None,
            status="partial" if inventory_turnover is not None else "unavailable",
            warnings=[
                "Usa inventario de cierre; para un resultado certificado se "
                "requiere inventario promedio."
            ] if inventory_turnover is not None else [],
            required=["rotación", "inventario promedio"],
            sources=available_source_names,
            polarity="neutral",
            visualizations=["kpi"],
        ),
        _indicator_contract(
            "compras_netas",
            "compras",
            "Compras netas",
            purchases_total,
            currency_unit,
            period_from=period_start,
            period_to=period_end,
            formula="Σ monto neto de compras no anuladas",
            numerator=purchases_total,
            required=["fecha compra", "monto neto", "estado"],
            sources=[(kinds.get("compras") or [None])[0]]
            if kinds.get("compras")
            else [],
            polarity="neutral",
            visualizations=["kpi", "linea_temporal", "ranking_proveedores"],
        ),
        _indicator_contract(
            "fletes_compra",
            "compras",
            "Fletes de compra",
            purchase_freight,
            currency_unit,
            period_from=period_start,
            period_to=period_end,
            formula="Σ flete por documento de compra sin duplicarlo por línea",
            numerator=purchase_freight,
            required=["ID documento compra", "flete"],
            sources=[(kinds.get("compras") or [None])[0]]
            if kinds.get("compras")
            else [],
            polarity="lower_is_better",
            visualizations=["kpi", "linea_temporal"],
        ),
        _indicator_contract(
            "gastos_operacionales",
            "gastos",
            "Gastos operacionales",
            expenses_period_total,
            currency_unit,
            period_from=period_start,
            period_to=period_end,
            formula="Σ gasto neto no anulado con fecha válida",
            numerator=expenses_period_total,
            required=["fecha gasto", "monto neto", "estado"],
            sources=[(kinds.get("gastos") or [None])[0]]
            if kinds.get("gastos")
            else [],
            polarity="lower_is_better",
            visualizations=["kpi", "donut", "linea_temporal", "barras_centro_costo"],
        ),
        _indicator_contract(
            "resultado_operacional",
            "gastos",
            "Resultado operacional",
            operating_result,
            currency_unit,
            period_from=period_start,
            period_to=period_end,
            formula="Utilidad bruta conocida − gastos operacionales comparables",
            numerator=operating_result,
            denominator=observed_sales,
            coverage=certified_cost_coverage if operating_result is not None else None,
            warnings=cost_warning,
            required=["utilidad bruta", "gastos operacionales"],
            sources=available_source_names,
            polarity="higher_is_better",
            visualizations=["kpi", "linea_temporal"],
        ),
        _indicator_contract(
            "gastos_fijos",
            "gastos",
            "Gastos fijos",
            fixed_expenses,
            currency_unit,
            period_from=period_start,
            period_to=period_end,
            formula="Σ gastos declarados como fijos",
            numerator=fixed_expenses,
            required=["tipo de gasto", "monto"],
            sources=[(kinds.get("gastos") or [None])[0]]
            if kinds.get("gastos")
            else [],
            polarity="lower_is_better",
            visualizations=["kpi", "donut"],
        ),
        _indicator_contract(
            "gastos_variables",
            "gastos",
            "Gastos variables",
            variable_expenses,
            currency_unit,
            period_from=period_start,
            period_to=period_end,
            formula="Σ gastos declarados como variables",
            numerator=variable_expenses,
            required=["tipo de gasto", "monto"],
            sources=[(kinds.get("gastos") or [None])[0]]
            if kinds.get("gastos")
            else [],
            polarity="lower_is_better",
            visualizations=["kpi", "donut"],
        ),
        _indicator_contract(
            "clientes_con_compra",
            "clientes",
            "Clientes con compra",
            indicator_clients,
            "clientes",
            period_from=period_start,
            period_to=period_end,
            formula="Clientes únicos en ventas no anuladas",
            numerator=indicator_clients,
            required=["ID cliente", "ventas"],
            sources=sales_names,
            polarity="higher_is_better",
            visualizations=["kpi", "linea_temporal", "segmentos"],
        ),
        _indicator_contract(
            "concentracion_cliente_principal",
            "clientes",
            "Concentración del principal cliente",
            top_clients[0].get("participacion_pct") if top_clients else None,
            "%",
            period_from=period_start,
            period_to=period_end,
            formula="Ventas positivas del principal cliente ÷ ventas positivas × 100",
            numerator=top_clients[0].get("ingresos") if top_clients else None,
            denominator=observed_sales if top_clients else None,
            variation_type="puntos_porcentuales",
            required=["ID cliente", "monto neto"],
            sources=available_source_names,
            polarity="lower_is_better",
            visualizations=["kpi", "ranking", "pareto"],
        ),
        _indicator_contract(
            "cumplimiento_meta_ventas",
            "comercial",
            "Cumplimiento de meta de ventas",
            target_compliance,
            "%",
            period_from=period_start,
            period_to=period_end,
            formula="Ventas comparables ÷ meta de ventas × 100",
            numerator=goals.get("venta_comparable"),
            denominator=goals.get("meta_venta"),
            variation_type="puntos_porcentuales",
            required=["periodo", "meta de ventas", "ventas"],
            sources=available_source_names,
            polarity="higher_is_better",
            visualizations=["kpi", "barra_progreso", "barras_sucursal"],
        ),
        _indicator_contract(
            "conversion_marketing",
            "comercial",
            "Conversión de campañas",
            marketing_conversion_rate,
            "%",
            period_from=period_start,
            period_to=period_end,
            formula="Conversiones ÷ clics × 100",
            numerator=None,
            denominator=None,
            variation_type="puntos_porcentuales",
            required=["clics", "conversiones"],
            sources=[(kinds.get("campanas") or [None])[0]]
            if kinds.get("campanas")
            else [],
            polarity="higher_is_better",
            visualizations=["kpi", "linea_temporal", "embudo"],
        ),
        _indicator_contract(
            "ctr_marketing",
            "comercial",
            "CTR de campañas",
            marketing_ctr,
            "%",
            period_from=period_start,
            period_to=period_end,
            formula="Clics ÷ impresiones × 100",
            variation_type="puntos_porcentuales",
            required=["clics", "impresiones"],
            sources=[(kinds.get("campanas") or [None])[0]]
            if kinds.get("campanas")
            else [],
            polarity="higher_is_better",
            visualizations=["kpi", "linea_temporal"],
        ),
        _indicator_contract(
            "costo_por_conversion",
            "comercial",
            "Costo por conversión",
            marketing_cost_per_conversion,
            currency_unit,
            period_from=period_start,
            period_to=period_end,
            formula="Inversión de campañas ÷ conversiones",
            numerator=marketing_investment,
            required=["inversión", "conversiones"],
            sources=[(kinds.get("campanas") or [None])[0]]
            if kinds.get("campanas")
            else [],
            polarity="lower_is_better",
            visualizations=["kpi", "ranking_campañas"],
        ),
        _indicator_contract(
            "liquidez_corriente",
            "balance",
            "Liquidez corriente",
            None,
            "veces",
            period_from=period_start,
            period_to=period_end,
            formula="Activo corriente ÷ pasivo corriente",
            status="unavailable",
            required=["activo corriente", "pasivo corriente"],
            warnings=["No se infieren partidas de balance desde ventas o cobranza."],
            sources=[],
            polarity="higher_is_better",
            visualizations=["kpi"],
        ),
        _indicator_contract(
            "roe",
            "balance",
            "ROE",
            None,
            "%",
            period_from=period_start,
            period_to=period_end,
            formula="Utilidad neta ÷ patrimonio promedio × 100",
            variation_type="puntos_porcentuales",
            status="unavailable",
            required=["utilidad neta", "patrimonio inicial y final"],
            warnings=["La utilidad operacional no se presenta como utilidad neta."],
            sources=[],
            polarity="higher_is_better",
            visualizations=["kpi", "linea_porcentual"],
        ),
    ]
    if mixed_unfiltered_currency:
        for indicator in indicator_catalog_rows:
            if indicator["unidad"] in {currency_unit, ticket_currency_unit}:
                indicator["valor"] = None
                indicator["valor_anterior"] = None
                indicator["diferencia_nominal"] = None
                indicator["variacion"] = None
                indicator["estado"] = "blocked"
                indicator["advertencias"] = [
                    "Hay monedas incompatibles. Elige una moneda antes de usar "
                    "este indicador monetario.",
                    *indicator["advertencias"],
                ]
    category_definitions = [
        ("ventas", "Ventas y crecimiento", "Ingresos, tendencia, ticket y unidades."),
        ("rentabilidad", "Rentabilidad", "Costo, utilidad, margen y cobertura."),
        ("caja", "Caja y liquidez", "Flujo, saldo y capacidad de pago."),
        ("cobranza", "Cobranza", "Cartera, mora y velocidad de cobro."),
        ("inventario", "Inventario", "Stock, valorización, rotación y quiebres."),
        ("clientes", "Clientes", "Concentración, recurrencia y segmentos."),
        ("compras", "Compras y proveedores", "Abastecimiento, costo y dependencia."),
        ("gastos", "Gastos y resultado", "Gasto operacional y resultado del negocio."),
        ("comercial", "Desempeño comercial", "Metas, campañas, vendedor y sucursal."),
        ("balance", "Indicadores financieros", "Liquidez, deuda, ROA y ROE."),
    ]
    indicator_categories = []
    for category_id, category_label, category_description in category_definitions:
        category_indicators = [
            row for row in indicator_catalog_rows if row["categoria"] == category_id
        ]
        available_count = sum(
            row["estado"] in {"available", "partial"}
            for row in category_indicators
        )
        fully_available = bool(category_indicators) and all(
            row["estado"] == "available" for row in category_indicators
        )
        indicator_categories.append({
            "id": category_id,
            "nombre": category_label,
            "descripcion": category_description,
            "estado": "available"
            if fully_available
            else "partial"
            if available_count
            else "unavailable",
            "disponibles": available_count,
            "total": len(category_indicators),
            "indicadores": category_indicators,
        })
    catalog_available = sum(
        row["estado"] == "available" for row in indicator_catalog_rows
    )
    catalog_partial = sum(
        row["estado"] == "partial" for row in indicator_catalog_rows
    )

    return {
        "version": 2,
        "filtros": {
            "disponibles": available_filters,
            "aplicados": applied_filters,
        },
        "estado_certificacion": certification,
        "confianza_pct": round(confidence, 1),
        "alcance": {
            "hojas_ventas": sales_names,
            "hoja_costos": current_cost_name,
            "hoja_historial_costos": cost_history_name,
            "hojas_utilizadas": sorted(used_sheets),
            "filas_ventas_sin_filtros": int(unfiltered_sales_rows),
            "filas_ventas_fisicas": int(len(sales)),
            "filas_totales_estructurales": int(structural.sum()),
            "filas_anuladas": int(cancelled.sum()),
            "filas_indicadores": int(indicator_mask.sum()),
            "periodo_declarado": {
                "desde": declared_period_from.date().isoformat()
                if declared_period_from is not None
                else None,
                "hasta": declared_period_to.date().isoformat()
                if declared_period_to is not None
                else None,
            }
            if declared_period_from is not None or declared_period_to is not None
            else None,
            "filas_fecha_invalida": int(invalid_sales_date.sum()),
            "filas_fuera_periodo_declarado": int(outside_declared_period.sum()),
            "documentos_repetidos": duplicate_groups,
            "filas_adicionales_documento": duplicate_extra_rows,
            "documentos_conflictivos": conflict_groups,
            "documentos_identicos": identical_groups,
            "documentos_solo_observacion_distinta": observation_only_groups,
        },
        "estado_resultados": {
            "ventas_brutas": round(float(gross_amount[indicator_mask].dropna().sum()), 2),
            "devoluciones_aceptadas": round(accepted_returns_total, 2),
            "filas_devoluciones_aceptadas": accepted_returns_rows,
            "ventas_observadas": round(observed_sales, 2),
            "ventas_certificables": round(certified_sales, 2),
            "ventas_pareadas": round(paired_sales, 2),
            "costo_venta_conocido": round(paired_cost, 2),
            "costo_venta_estimado_catalogo": round(
                float(all_cost_of_sales[indicator_mask & estimated_current_cost].sum()), 2
            ),
            "costo_venta_con_relleno_estimado": round(estimated_total_cost, 2),
            "ventas_pareadas_estimadas": round(estimated_paired_sales, 2),
            "utilidad_bruta_estimada": round(estimated_gross_profit, 2)
            if estimated_gross_profit is not None
            else None,
            "margen_bruto_estimado_pct": round(estimated_gross_margin, 2)
            if estimated_gross_margin is not None
            else None,
            "utilidad_bruta": round(gross_profit, 2) if gross_profit is not None else None,
            "margen_bruto_pct": round(gross_margin, 2) if gross_margin is not None else None,
            "gastos_operacionales": round(expenses_total, 2) if expenses_total is not None else None,
            "gastos_operacionales_periodo": round(expenses_period_total, 2)
            if expenses_period_total is not None
            else None,
            "base_gastos_operacionales": expense_value_basis,
            "iva_gastos_excluido": round(expense_tax_excluded, 2)
            if expense_tax_excluded is not None
            else None,
            "filas_gastos": expenses_rows,
            "resultado_operacional": round(operating_result, 2) if operating_result is not None else None,
            "margen_operacional_pct": round(operating_margin, 2) if operating_margin is not None else None,
            "depreciacion_amortizacion": round(depreciation_expense, 2)
            if depreciation_expense is not None
            else None,
            "ebitda": round(ebitda, 2) if ebitda is not None else None,
            "cobertura_costos_pct": cost_coverage,
            "cobertura_costos_estimada_pct": estimated_cost_coverage,
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
            "cobranzas_huerfanas": orphan_collection_rows,
            "cuentas_por_cobrar": round(accounts_receivable, 2)
            if accounts_receivable is not None
            else None,
            "cuentas_vencidas": round(overdue_receivable, 2)
            if overdue_receivable is not None
            else None,
            "dso_dias": round(dso_days, 2) if dso_days is not None else None,
            "mora_promedio_dias": round(overdue_days, 2)
            if overdue_days is not None
            else None,
            "valor_inventario": round(inventory_value, 2) if inventory_value is not None else None,
            "stock_inventario": round(inventory_stock, 2)
            if inventory_stock is not None
            else None,
            "inventario_bajo_minimo": inventory_below_minimum,
            "fecha_corte_inventario": inventory_snapshot_date,
            "compras_efectivas": round(purchases_total, 2) if purchases_total is not None else None,
            "fletes_compra": round(purchase_freight, 2)
            if purchase_freight is not None
            else None,
            "gastos_fijos": round(fixed_expenses, 2) if fixed_expenses is not None else None,
            "gastos_variables": round(variable_expenses, 2) if variable_expenses is not None else None,
            "gasto_fijo_mensual_promedio": round(monthly_fixed_expenses, 2)
            if monthly_fixed_expenses is not None
            else None,
            "punto_equilibrio_ventas": round(break_even_sales, 2) if break_even_sales is not None else None,
            "rotacion_inventario_aprox": round(inventory_turnover, 2) if inventory_turnover is not None else None,
            "inversion_marketing": round(marketing_investment, 2)
            if marketing_investment is not None
            else None,
            "ctr_marketing_pct": round(marketing_ctr, 2)
            if marketing_ctr is not None
            else None,
            "conversion_marketing_pct": round(marketing_conversion_rate, 2)
            if marketing_conversion_rate is not None
            else None,
            "costo_por_conversion": round(marketing_cost_per_conversion, 2)
            if marketing_cost_per_conversion is not None
            else None,
        },
        "evolucion": monthly_rows,
        "agrupaciones": groupings,
        "portafolio": {"umbrales": thresholds, "productos": portfolio},
        "metas": goals,
        "sensibilidad": sensitivity,
        "calidad": {
            "costos": cost_quality,
            "costos_detalle": {
                "hoja": current_cost_name,
                "negativos": negative_cost_locations,
            },
            "documentos": document_issue_examples,
            "integridad_referencial": integrity,
            "controles_formula": formula_controls,
            "filas_inconsistentes_formula": formula_issues,
            "referencias_problematicas": orphan_rows,
        },
        "ratios": ratios,
        "decisiones": decisions,
        "catalogo_indicadores": {
            "version": 1,
            "moneda": currency_label if not mixed_unfiltered_currency else "mixta",
            "categorias": indicator_categories,
            "disponibles": catalog_available,
            "parciales": catalog_partial,
            "no_disponibles": len(indicator_catalog_rows)
            - catalog_available
            - catalog_partial,
        },
    }
