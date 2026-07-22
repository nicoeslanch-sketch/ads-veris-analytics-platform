"""Indicadores del dashboard a partir del dataset limpio (SPEC §7, POST /metrics).

Fase 2: KPIs con variación vs periodo anterior, evolución mensual de ingresos/
gastos/utilidad, análisis por categoría, ventas por canal, top productos y
proyección a 3 meses. Todo filtrable por rango de fechas.

Gastos y utilidad se calculan solo si el archivo trae una columna de costo.
Los ratios financieros que requieren balance (ROA, ROE, liquidez, prueba ácida,
rotación de inventario, días de cobro/pago) quedan declarados pero sin valor:
se habilitan cuando el usuario conecte sus datos financieros.
"""

import math
import re
from dataclasses import dataclass, field
from typing import Any, Iterator

import pandas as pd

from .mapping import (
    detect_column_roles,
    resolve_mapping,
    strip_accents_lower,
)
from .standardize import (
    NUMERIC_CANONICAL_ATTR,
    is_missing,
    map_unique,
    parse_date,
    parse_number,
    physical_missing_mask,
    semantic_missing_mask,
    structural_total_mask,
)

FINANCIAL_RATIOS = [
    "roa",
    "roe",
    "liquidez_corriente",
    "prueba_acida",
    "rotacion_inventario",
    "dias_cobro",
    "dias_pago",
]


def _json_safe_metrics(value: Any) -> Any:
    """Convierte ausentes numéricos en null antes de responder o persistir.

    Pandas conserva ``NaN`` en columnas float aunque se intente reemplazar por
    ``None``. Python puede imprimirlo, pero JSON estricto, PostgreSQL y httpx
    lo rechazan. Un dato no disponible debe representarse como ``null``.
    """
    if isinstance(value, dict):
        return {key: _json_safe_metrics(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_metrics(item) for item in value]
    if value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _numeric_series(df: pd.DataFrame, column: str | None) -> pd.Series:
    if column is None or column not in df.columns:
        return pd.Series([None] * len(df), index=df.index, dtype=float)
    canonical = bool(df.attrs.get(NUMERIC_CANONICAL_ATTR))
    return map_unique(
        df[column],
        lambda value: (
            parse_number(
                value,
                dot3_convention="decimal" if canonical else "miles",
                comma3_convention="decimal",
            )
            if not is_missing(value)
            else None
        ),
    ).astype(float)


# ── Moneda (Fase 10 §4.4): detección por tokens en la columna de montos ─────
# El parser acepta "$ 1.200", "US$1.500", "€200"… pero el dashboard debe saber
# QUÉ moneda está mostrando, y jamás sumar monedas distintas en silencio.
# Fase 13 (P0.5): TODAS las monedas cuyo token elimina el estandarizador —
# antes UF/ARS/PEN/COP/MXN perdían su token y el dashboard las mostraba
# como pesos chilenos sin aviso.
_CURRENCY_SIGNALS = {
    "USD": re.compile(r"(?i)(us\$|usd)"),
    "EUR": re.compile(r"(?i)(€|eur)"),
    "CLP": re.compile(r"(?i)\bclp\b"),
    "UF": re.compile(r"(?i)\buf\b"),
    "ARS": re.compile(r"(?i)\bars\b"),
    "PEN": re.compile(r"(?i)(\bpen\b|s/\.?\s?\d)"),
    "COP": re.compile(r"(?i)\bcop\b"),
    "MXN": re.compile(r"(?i)\bmxn\b"),
    "GBP": re.compile(r"(?i)(£|gbp)"),
}


@dataclass(frozen=True)
class CurrencyDetection:
    """Resultado tipado de la inspección monetaria completa.

    ``conteos_por_columna`` permite auditar si la incompatibilidad proviene de
    ventas, costos o de ambas. ``__iter__`` mantiene la compatibilidad con el
    antiguo desempaquetado ``moneda, aviso = detect_currency(...)``.
    """

    dominante: str
    detectadas: tuple[str, ...]
    conteos: dict[str, int]
    mixta: bool
    advertencia: str | None = None
    conteos_por_columna: dict[str, dict[str, int]] = field(default_factory=dict)

    def __iter__(self) -> Iterator[str | None]:
        yield self.dominante
        yield self.advertencia

    def to_dict(self) -> dict:
        return {
            "dominante": self.dominante,
            "detectadas": list(self.detectadas),
            "conteos": dict(self.conteos),
            "mixta": self.mixta,
            "advertencia": self.advertencia,
            "conteos_por_columna": {
                name: dict(counts) for name, counts in self.conteos_por_columna.items()
            },
        }


def _currency_counts(raw: pd.Series | None) -> dict[str, int]:
    counts = {code: 0 for code in _CURRENCY_SIGNALS}
    if raw is None:
        return counts

    # Recorre TODA la columna, pero evalúa cada valor único una sola vez.
    # Es lineal para construir value_counts y evita el sesgo de las primeras
    # 1.000 filas sin multiplicar el costo por datos muy repetidos.
    values = raw.loc[~physical_missing_mask(raw)].astype(str).str.strip()
    for value, occurrences in values.value_counts(dropna=False).items():
        text = str(value)
        found = {
            code for code, pattern in _CURRENCY_SIGNALS.items() if pattern.search(text)
        }
        # '$' aislado es CLP por convención es-CL, pero no cuando el mismo
        # valor ya declara otra moneda (US$, ARS $, etc.).
        if not found and "$" in text:
            found.add("CLP")
        for code in found:
            counts[code] += int(occurrences)
    return counts


def detect_currency(
    montos: pd.Series | None,
    costos: pd.Series | None = None,
) -> CurrencyDetection:
    """Inspecciona montos y costos completos y devuelve un contrato tipado."""

    by_column = {
        "monto": _currency_counts(montos),
        "costo": _currency_counts(costos),
    }
    counts = {
        code: by_column["monto"][code] + by_column["costo"][code]
        for code in _CURRENCY_SIGNALS
    }
    explicit = {code: count for code, count in counts.items() if count > 0}
    if not explicit:
        return CurrencyDetection("CLP", (), counts, False, None, by_column)

    dominant = max(explicit, key=lambda code: (explicit[code], code == "CLP", code))
    detected = tuple(sorted(explicit))
    mixed = len(detected) > 1
    warning: str | None = None
    if mixed:
        detail = ", ".join(detected)
        warning = (
            f"Se detectaron montos o costos en más de una moneda ({detail}). "
            "Los indicadores monetarios están bloqueados porque no existe una "
            "conversión declarada y verificable."
        )
    elif dominant != "CLP":
        warning = (
            f"Los montos y costos parecen estar en {dominant}: los indicadores se "
            "muestran en esa moneda, sin conversión a pesos chilenos."
        )
    return CurrencyDetection(dominant, detected, counts, mixed, warning, by_column)


def _coerce_currency_detection(
    hint: CurrencyDetection | tuple[str, str | None] | None,
    montos: pd.Series | None,
    costos: pd.Series | None,
) -> CurrencyDetection:
    if isinstance(hint, CurrencyDetection):
        return hint
    if isinstance(hint, tuple):
        # Compatibilidad transitoria con integraciones Fase 15. El pipeline
        # propio nunca usa este camino: siempre entrega CurrencyDetection.
        dominant, warning = hint
        mixed = bool(warning and "más de una moneda" in warning.lower())
        detected = (dominant,) if not mixed else (dominant, "INCOMPATIBLE")
        return CurrencyDetection(
            dominant,
            detected,
            {dominant: 1},
            mixed,
            warning,
            {},
        )
    return detect_currency(montos, costos)


def _block_monetary_outputs(result: dict, detection: CurrencyDetection) -> None:
    """Elimina del contrato público cualquier suma monetaria incompatible.

    El bloqueo vive en backend para proteger también análisis guardados, IA,
    reportes y consumidores futuros que no implementen una pantalla especial.
    Se conservan solo conteos no monetarios y metadatos de cobertura.
    """

    kpis = result.get("kpis", {})
    for key in (
        "ingresos_totales",
        "ticket_promedio",
        "gastos_totales",
        "ganancia_neta",
        "margen_utilidad_pct",
        "flujo_caja",
        "devoluciones",
        "base_costos",
    ):
        if key in kpis:
            kpis[key] = None

    # El monto de filas sin fecha también es una suma monetaria. Quedaba fuera
    # de los KPI principales y podía ser consumido por reportes aun cuando la
    # mezcla de monedas ya había bloqueado el dashboard.
    period_without_date = result.get("periodo", {}).get("sin_fecha")
    if isinstance(period_without_date, dict) and "monto" in period_without_date:
        period_without_date["monto"] = None

    # Estas estructuras se derivan de sumas monetarias. Entregar listas vacías
    # evita que un consumidor use accidentalmente valores calculados antes del
    # bloqueo y mantiene operativas las dimensiones no monetarias.
    result["evolucion_mensual"] = []
    for key in (
        "por_categoria",
        "ventas_por_canal",
        "top_productos",
        "por_dia_semana",
        "agrupaciones_flexibles",
    ):
        if key in result:
            result[key] = []
    if "lideres_productos" in result:
        result["lideres_productos"] = None
    # Fase 19: la clasificación de rentabilidad también es una suma monetaria.
    if "analisis_rentabilidad" in result:
        result["analisis_rentabilidad"] = None
    if isinstance(result.get("clientes"), dict):
        result["clientes"] = {
            **result["clientes"],
            "top": [],
            "concentracion_top_pct": None,
            "cobertura_identificacion_pct": None,
        }

    # Los catálogos no publican ingresos genéricos, pero sí estadísticas de
    # costo/precio y margen potencial. También son indicadores monetarios y
    # deben quedar inutilizables si el archivo mezcla monedas. Se conservan
    # exclusivamente conteos, cobertura, categorías, marcas y estados.
    product_analysis = result.get("analisis_productos")
    if isinstance(product_analysis, dict):
        empty_stats = {
            "promedio": None,
            "mediana": None,
            "minimo": None,
            "maximo": None,
        }
        for key in ("costos", "precios_lista", "margen_potencial"):
            if key in product_analysis:
                product_analysis[key] = dict(empty_stats)
        if "totales_catalogo_unitario" in product_analysis:
            product_analysis["totales_catalogo_unitario"] = None
        if "ranking_costos" in product_analysis:
            product_analysis["ranking_costos"] = []

    # En campañas, inversión y CPC son monetarios; impresiones, clics, CTR y
    # sus desgloses siguen siendo seguros y útiles.
    campaign_analysis = result.get("analisis_campanas")
    if isinstance(campaign_analysis, dict):
        for key in ("inversion", "cpc"):
            if key in campaign_analysis:
                campaign_analysis[key] = None
    generic_analysis = result.get("analisis_generico")
    if isinstance(generic_analysis, dict):
        for numeric in generic_analysis.get("numericas", []):
            if numeric.get("formato") == "moneda":
                for key in ("total", "promedio", "mediana", "minimo", "maximo"):
                    numeric[key] = None
        evolution = generic_analysis.get("evolucion")
        if isinstance(evolution, dict) and evolution.get("formato") == "moneda":
            generic_analysis["evolucion"] = None
    inventory_analysis = result.get("analisis_inventario")
    if isinstance(inventory_analysis, dict):
        for key in ("valor_inventario", "costo_referencia_promedio"):
            if key in inventory_analysis:
                inventory_analysis[key] = None
    result["proyeccion"] = None
    result["datos_monetarios_disponibles"] = False
    result["bloqueo_monetario"] = {
        "codigo": "MONEDAS_INCOMPATIBLES",
        "mensaje": detection.advertencia,
    }


def is_product_catalog_profile(
    columns: list[str] | pd.Index,
    roles: dict[str, str],
) -> bool:
    """Distingue una maestra de productos de una tabla transaccional.

    ``Stock`` puede ocupar el rol cantidad en una maestra y ``Precio_Lista``
    puede ocupar el rol monto por compatibilidad legacy. Eso no convierte la
    maestra en ventas. En el sentido inverso, la presencia de una columna
    transaccional distinta (por ejemplo ``Monto``) impide ocultar ingresos
    solo porque la misma tabla también incluya precio de lista y costos.

    Esta función es compartida por métricas y relaciones multihoja para que
    ambas rutas clasifiquen la misma estructura de la misma manera.
    """

    normalized_columns = {
        str(column): strip_accents_lower(str(column)).replace("_", " ")
        for column in columns
    }
    price_list_columns = {
        column
        for column, normalized in normalized_columns.items()
        if "precio" in normalized and "lista" in normalized
    }
    total_unit_cost_columns = {
        column
        for column, normalized in normalized_columns.items()
        if "costo" in normalized
        and "total" in normalized
        and any(token in normalized for token in ("unitario", "por unidad", "unit"))
    }
    unit_cost_columns = {
        column
        for column, normalized in normalized_columns.items()
        if "costo" in normalized
        and any(token in normalized for token in ("unitario", "por unidad", "unit"))
    }
    catalog_reference_columns = (
        price_list_columns | total_unit_cost_columns | unit_cost_columns
    )
    if not catalog_reference_columns:
        return False

    transaction_id_tokens = (
        "id venta",
        "id transaccion",
        "numero venta",
        "numero boleta",
        "numero factura",
        "id compra",
        "numero compra",
    )
    has_transaction_id = any(
        any(token in normalized for token in transaction_id_tokens)
        for normalized in normalized_columns.values()
    ) or any(
        any(
            marker in re.sub(r"[^a-z0-9]", "", normalized)
            for marker in (
                "idventa", "idtransaccion", "numeroventa", "numeroboleta",
                "numerofactura", "idcompra", "numerocompra",
            )
        )
        for normalized in normalized_columns.values()
    )
    operational_date_tokens = (
        "venta",
        "operacion",
        "transaccion",
        "factura",
        "boleta",
        "pedido",
        "orden",
        "emision",
        "sale",
        "transaction",
        "operation",
        "invoice",
        "order",
        "compra",
        "purchase",
    )
    metadata_date_tokens = (
        "actualizacion",
        "creacion",
        "modificacion",
        "vigencia",
        "carga",
        "update",
        "created",
        "creation",
        "modified",
        "effective",
        "alta",
        "registro",
    )
    mapped_date = roles.get("fecha")
    mapped_date_normalized = normalized_columns.get(str(mapped_date), "")
    # Una fecha explícitamente comercial domina cualquier marca de metadata
    # (por ejemplo Fecha_Venta_Modificada sigue siendo una fecha de venta).
    has_operational_date = any(
        (
            column == str(mapped_date)
            or any(marker in normalized for marker in ("fecha", "date", "periodo"))
        )
        and any(token in normalized for token in operational_date_tokens)
        for column, normalized in normalized_columns.items()
    )
    mapped_date_is_metadata = bool(
        mapped_date
        and any(token in mapped_date_normalized for token in metadata_date_tokens)
        and not any(
            token in mapped_date_normalized for token in operational_date_tokens
        )
    )
    has_transaction_date = bool(
        has_operational_date or (mapped_date and not mapped_date_is_metadata)
    )
    mapped_amount = roles.get("monto")
    amount_is_catalog_reference = (
        mapped_amount is None or mapped_amount in catalog_reference_columns
    )

    # Protege incluso ante un override manual que asigne Precio_Lista a monto
    # aunque el archivo conserve una columna comercial inequívoca.
    transaction_amount_tokens = {
        "monto",
        "venta",
        "ventas",
        "ingreso",
        "ingresos",
        "importe",
        "facturacion",
        "revenue",
        "sales",
    }
    distinct_transaction_amount = any(
        column not in catalog_reference_columns
        and column != roles.get("costo")
        and not any(
            marker in normalized for marker in ("unidad venta", "unidad compra")
        )
        and bool(
            set(re.split(r"[^a-z0-9]+", normalized.strip()))
            & transaction_amount_tokens
        )
        for column, normalized in normalized_columns.items()
    )
    return bool(
        roles.get("producto")
        and not has_transaction_date
        and not has_transaction_id
        and amount_is_catalog_reference
        and not distinct_transaction_amount
    )


def is_transaction_profile(
    columns: list[str] | pd.Index,
    roles: dict[str, str],
) -> bool:
    """Reconoce hechos comerciales aunque no traigan fecha ni cantidad.

    Muchos extractos válidos solo incluyen folio, producto y monto. El perfil
    anterior los trataba como una tabla genérica, lo que impedía relacionarlos
    con Productos. Un catálogo explícito siempre tiene prioridad para que
    Precio_Lista/Stock no se conviertan en ventas ficticias.
    """

    if not roles.get("monto") or is_product_catalog_profile(columns, roles):
        return False
    normalized_columns = {
        str(column): strip_accents_lower(str(column)).replace("_", " ")
        for column in columns
    }
    compact_names = {
        re.sub(r"[^a-z0-9]", "", normalized)
        for normalized in normalized_columns.values()
    }
    has_transaction_id = any(
        any(
            marker in compact
            for marker in (
                "idventa",
                "idtransaccion",
                "numeroventa",
                "numeroboleta",
                "numerofactura",
            )
        )
        for compact in compact_names
    )
    amount_name = normalized_columns.get(str(roles.get("monto")), "")
    amount_words = set(re.split(r"[^a-z0-9]+", amount_name.strip()))
    clear_transaction_amount = bool(
        amount_words
        & {
            "monto",
            "venta",
            "ventas",
            "ingreso",
            "ingresos",
            "importe",
            "facturacion",
            "revenue",
            "sales",
        }
    )
    return bool(
        roles.get("fecha")
        or (roles.get("cantidad") and roles.get("producto"))
        or has_transaction_id
        or clear_transaction_amount
    )


def detect_non_sales_profile(
    columns: list[str] | pd.Index,
    roles: dict[str, str],
) -> str | None:
    """Reconoce tablas operacionales que tienen fecha y monto, pero no ventas.

    Fecha + monto no basta para afirmar que una fila es una venta. Compras,
    gastos, cobranzas, metas e inventario cumplen esa estructura y antes se
    presentaban como ingresos, ticket y utilidad. La clasificación usa varias
    señales explícitas del encabezado y es conservadora: si no hay evidencia
    suficiente, el perfil comercial existente conserva la prioridad.
    """

    normalized = [
        strip_accents_lower(str(column)).replace("_", " ") for column in columns
    ]
    compact = {re.sub(r"[^a-z0-9]", "", value) for value in normalized}
    words = " ".join(normalized)

    def has_compact(*markers: str) -> bool:
        return any(any(marker in name for marker in markers) for name in compact)

    # Orden deliberado: una compra y un gasto también traen proveedor; una
    # cobranza también trae cliente. Primero se detecta el hecho operacional.
    if (
        has_compact("idcompra", "fechacompra", "totalcompra", "montonetocompra")
        and has_compact("proveedor", "costounitariocompra", "estadorecepcion")
    ):
        return "compras"
    if (
        has_compact("idgasto", "fechagasto", "totalgasto", "categoriagasto")
        and has_compact("tipogasto", "estadogasto", "proveedor")
    ):
        return "gastos"
    if (
        has_compact("idpago", "fechapago", "montopago")
        and has_compact("estadopago", "mediopago", "documento")
    ):
        return "cobranzas"
    if has_compact("metaventa", "metamargen", "metanuevosclientes") or (
        "meta" in words and bool(roles.get("sucursal"))
    ):
        return "metas"
    if (
        has_compact("valorinventario")
        or (
            has_compact("stockminimo")
            and has_compact("stocksistema", "stockfisico", "stockdisponible")
        )
    ):
        return "inventario"
    if has_compact("mesvigencia") and roles.get("costo") and roles.get("producto"):
        return "historial_costos"
    if (
        has_compact("idproveedor")
        and not roles.get("producto")
        and not has_compact("idcompra", "idgasto")
    ):
        return "proveedores"
    if has_compact("idvendedor") and has_compact("cargo", "comision"):
        return "trabajadores"
    if has_compact("idcliente") and not has_compact(
        "idventa", "idpago", "fechaventa", "montoventa", "tipomovimiento"
    ):
        return "clientes"
    if has_compact("idsucursal") and not has_compact(
        "idventa", "idcompra", "idgasto", "idpago", "sku"
    ):
        return "sucursales"
    if roles.get("producto") and not roles.get("monto") and not has_compact(
        "idventa", "idcompra", "cantidadvendida", "montoventa"
    ):
        return "productos"
    return None


def _pct_change(current: float, previous: float | None) -> float | None:
    if previous is None or previous == 0:
        return None
    return round((current - previous) / abs(previous) * 100, 1)


def _kpi(value: float, previous: float | None) -> dict:
    return {"valor": round(value, 2), "variacion_pct": _pct_change(value, previous)}


def _group_sum(
    groups: pd.Series, amounts: pd.Series, costs: pd.Series | None
) -> list[dict]:
    """Ingresos por grupo; con costos, utilidad y margen SOLO sobre filas
    pareadas (ingreso Y costo) — misma regla que el KPI global (Fase 12: antes
    el margen por grupo dividía por los ingresos totales del grupo, y con
    cobertura parcial de costos quedaba subestimado)."""
    # Fase 18: una clave AUSENTE (NaN tras una relación sin correspondencia o
    # una celda vacía) se agrupaba con la etiqueta "nan" — ilegible y fácil de
    # confundir con una categoría real. Solo lo físicamente ausente cae en
    # "Sin clasificar": un literal textual "null"/"NaT" es un dato conservado
    # (Fase 16) y sigue siendo su propio grupo.
    def _etiqueta_grupo(value) -> str:
        if pd.isna(value):
            return "Sin clasificar"
        text = str(value).strip()
        return text if text else "Sin clasificar"

    frame = pd.DataFrame({"grupo": groups.map(_etiqueta_grupo), "monto": amounts})
    has_costs = costs is not None
    if has_costs:
        frame["costo"] = costs
    frame = frame.dropna(subset=["monto"])
    if frame.empty:
        return []
    # Fase 13 (P0.3): la participación se calcula sobre las ventas BRUTAS
    # positivas — con devoluciones, dividir por el neto disparaba porcentajes
    # absurdos (100.000 sobre un neto de 10.000 = "1.000%").
    positivos = float(frame.loc[frame["monto"] > 0, "monto"].sum())
    total = positivos if positivos > 0 else (abs(float(frame["monto"].sum())) or 1.0)
    total_neto = float(frame["monto"].sum())
    rows: list[dict] = []
    for name, g in frame.groupby("grupo", dropna=False):
        ingresos = float(g["monto"].sum())
        # Fase 14b: participación BRUTA por grupo — una distribución real que
        # suma ≈100%. `porcentaje` (neto del grupo / brutas totales) se
        # conserva para mostrar el efecto de las devoluciones, pero las
        # afirmaciones de CONCENTRACIÓN ("X concentra el N% de tus ventas")
        # usan participacion_bruta_pct: con devoluciones, el neto no es una
        # distribución (A:+100.000 y B:-90.000 daban 100% y -90%).
        brutas = float(g.loc[g["monto"] > 0, "monto"].sum())
        devoluciones_grupo = float(g.loc[g["monto"] < 0, "monto"].sum())
        item = {
            "nombre": str(name),
            "ingresos": round(ingresos, 2),
            "porcentaje": round(ingresos / total * 100, 1),
            "ventas_brutas": round(brutas, 2),
            "devoluciones": round(devoluciones_grupo, 2),
            "ventas_netas": round(ingresos, 2),
            "participacion_bruta_pct": (
                round(brutas / positivos * 100, 1) if positivos > 0 else None
            ),
            "participacion_neta_pct": (
                round(ingresos / total_neto * 100, 1) if total_neto else None
            ),
        }
        # Fase 12b §22: cada grupo expone su base de cálculo — sin esto, una
        # categoría con UNA fila con costo competía en "rentabilidad" contra
        # otra con mil, y nadie podía notarlo.
        item["filas"] = int(len(g))
        if has_costs:
            paired = g.dropna(subset=["costo"])
            item["filas_pareadas"] = int(len(paired))
            item["cobertura_costos_pct"] = round(len(paired) / len(g) * 100, 1)
            if len(paired):
                ing_par = float(paired["monto"].sum())
                costo_pareado = float(paired["costo"].sum())
                utilidad = ing_par - costo_pareado
                item["costo"] = round(costo_pareado, 2)
                item["utilidad"] = round(utilidad, 2)
                item["margen_pct"] = (
                    round(utilidad / ing_par * 100, 1) if ing_par else None
                )
            # Grupo sin ninguna fila pareada: sin utilidad/margen (la UI
            # muestra "—" en vez de un 0 falso).
        rows.append(item)
    rows.sort(key=lambda r: r["ingresos"], reverse=True)
    return rows


def _is_percentage_column(column: str) -> bool:
    normalized = strip_accents_lower(column).replace("_", " ")
    return "%" in normalized or normalized.strip() == "pct" or any(
        token in normalized for token in ("descuento", "porcentaje", "percent", " pct")
    )


def _percentage_buckets(df: pd.DataFrame, column: str) -> tuple[pd.Series, pd.Series]:
    """Groups canonical proportions without mixing invalid business values."""
    values = _numeric_series(df, column)
    labels = pd.Series("Sin dato", index=df.index, dtype="object")
    labels.loc[values == 0] = "Sin descuento"
    for lower, upper, label in (
        (0, 0.05, "1–5%"),
        (0.05, 0.10, "6–10%"),
        (0.10, 0.20, "11–20%"),
        (0.20, 0.50, "21–50%"),
        (0.50, 1.00, "51–100%"),
    ):
        labels.loc[(values > lower) & (values <= upper)] = label
    out_of_range = values.notna() & ((values < 0) | (values > 1))
    labels.loc[out_of_range] = "Fuera de rango"
    return labels, out_of_range


def _sort_by_gross_share(rows: list[dict]) -> list[dict]:
    """Ordena solo los rankings de concentración por participación bruta.

    Las tablas generales conservan su orden por ingresos netos; mezclar ambos
    criterios haría que barras y montos dejaran de ser monotónicos.
    """
    return sorted(
        rows,
        key=lambda row: (
            row.get("participacion_bruta_pct")
            if row.get("participacion_bruta_pct") is not None
            else float("-inf")
        ),
        reverse=True,
    )


def _projection(monthly: pd.DataFrame, first_month: pd.Period | None = None) -> dict | None:
    """Proyección simple a 3 meses por crecimiento promedio mensual.

    Fase 14: cuando el último mes de la serie real está PARCIAL, se pasa aquí
    la serie SIN ese mes (la tasa y la base usan solo meses completos — el mes
    a medio llenar deprimía el crecimiento con una caída ficticia) y
    `first_month` fija el primer mes proyectado DESPUÉS del final real, para
    que la proyección jamás se superponga con un mes que sí tiene datos.
    """
    series = monthly["ingresos"].astype(float)
    if len(series) < 2 or series.iloc[:-1].le(0).any():
        return None
    growth_rates = series.pct_change().dropna()
    # Acotar tasas extremas para que un mes atípico no dispare la proyección.
    growth = float(growth_rates.clip(-0.5, 0.5).mean())
    last_month = pd.Period(monthly.index[-1], freq="M")
    start = first_month if first_month is not None else last_month + 1
    projected = []
    value = float(series.iloc[-1])
    month = last_month
    # Puente silencioso hasta el mes previo al primero proyectado (cubre el
    # mes parcial excluido de la serie).
    while month + 1 < start:
        month += 1
        value = value * (1 + growth)
    for _ in range(3):
        month += 1
        value = value * (1 + growth)
        projected.append({"mes": str(month), "ingresos": round(max(value, 0.0), 2)})
    base = float(series.tail(3).sum())
    total_projected = sum(item["ingresos"] for item in projected)
    return {
        "crecimiento_pct": round(growth * 100, 1),
        "crecimiento_trimestre_pct": _pct_change(total_projected, base if base else None),
        "meses": projected,
    }


def compute_metrics(
    df: pd.DataFrame,
    mapping: dict[str, str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    currency_hint: CurrencyDetection | tuple[str, str | None] | None = None,
) -> dict:
    """`currency_hint` viene del pipeline (detección sobre los valores CRUDOS,
    antes de que la estandarización quite los símbolos de moneda)."""
    # Fase 11 §9.2: el mapeo manual se FUSIONA con el automático. Antes un
    # override parcial (ej: solo "monto") reemplazaba el mapeo completo y
    # hacía desaparecer fecha/categoría/canal detectados → dashboard vacío.
    roles = resolve_mapping(list(df.columns), mapping)
    roles = {role: col for role, col in roles.items() if col in df.columns}
    warnings: list[str] = []
    normalized_columns = {
        strip_accents_lower(str(column)).replace("_", " "): str(column)
        for column in df.columns
    }
    price_list_column = next(
        (
            column
            for normalized, column in normalized_columns.items()
            if "precio" in normalized and "lista" in normalized
        ),
        None,
    )
    total_unit_cost_column = next(
        (
            column
            for normalized, column in normalized_columns.items()
            if "costo" in normalized
            and "total" in normalized
            and any(token in normalized for token in ("unitario", "por unidad", "unit"))
            and column != roles.get("costo")
        ),
        None,
    )
    product_catalog = is_product_catalog_profile(df.columns, roles)
    normalized_keys = {norm_key: column for norm_key, column in normalized_columns.items()}
    campaign_profile = all(
        any(token in name for name in normalized_keys)
        for token in ("inversion", "impresiones", "clic")
    )
    inventory_profile = (
        any(
            "stock" in name
            and "minimo" not in name
            and "ubicacion" not in name
            for name in normalized_keys
        )
        and any("stock minimo" in name for name in normalized_keys)
        and bool(roles.get("producto"))
    )
    non_sales_profile = detect_non_sales_profile(df.columns, roles)
    # Un historial de costos tiene muchas observaciones por SKU. Resumirlo
    # como un catálogo estático mezclaría vigencias y falsearía el ranking.
    if non_sales_profile == "historial_costos":
        product_catalog = False
    transactional_profile = bool(
        is_transaction_profile(df.columns, roles)
        and non_sales_profile is None
        and not inventory_profile
    )

    status_column = next(
        (
            column
            for normalized, column in normalized_columns.items()
            if normalized == "estado"
            or normalized.startswith("estado ")
            or normalized.endswith(" estado")
        ),
        None,
    )
    cancelled_mask = pd.Series(False, index=df.index)
    if transactional_profile and status_column:
        status_missing = physical_missing_mask(df[status_column])
        normalized_status = df[status_column].astype(str).map(strip_accents_lower).str.strip()
        normalized_status = normalized_status.mask(status_missing, "")
        cancelled_mask = normalized_status.str.contains(
            r"\b(?:anulad|cancelad|void)\w*", regex=True, na=False
        )
    # Fase 19: filas "TOTAL 2025"/"Subtotal…" exportadas al pie de la tabla.
    # Traen el monto del periodo completo sin fecha ni estado: sumarlas junto a
    # las transacciones DUPLICA los ingresos. Se conservan en la base pero
    # jamás entran a los indicadores.
    total_rows_mask = (
        structural_total_mask(df, roles.get("fecha"))
        if transactional_profile
        else pd.Series(False, index=df.index)
    )
    indicator_row_mask = ~cancelled_mask & ~total_rows_mask
    total_rows = int(total_rows_mask.sum())
    if total_rows:
        warnings.append(
            f"Se detectaron {total_rows} fila(s) de totales estructurales "
            "(por ejemplo 'TOTAL 2025'): se conservan en la base pero se "
            "excluyen de todos los indicadores — sumarlas duplicaría el periodo."
        )
    cancelled_rows = int(cancelled_mask.sum())
    if cancelled_rows:
        warnings.append(
            f"Se conservaron {cancelled_rows} fila(s) anulada(s) en la base, "
            "pero se excluyeron de ventas, costos, utilidad y tendencias."
        )

    currency = _coerce_currency_detection(
        currency_hint,
        df[roles["monto"]] if roles.get("monto") else None,
        df[roles["costo"]] if roles.get("costo") else None,
    )

    amounts_all = _numeric_series(df, roles.get("monto")).where(indicator_row_mask)
    costs_all = _numeric_series(df, roles.get("costo")).where(indicator_row_mask)
    cost_column_normalized = (
        strip_accents_lower(str(roles["costo"])).replace("_", " ")
        if roles.get("costo")
        else ""
    )
    unit_cost_role = any(
        marker in cost_column_normalized
        for marker in ("costo unitario", "cost unit", "unit cost", "costo por unidad")
    )
    derived_unit_cost = bool(
        unit_cost_role
        and roles.get("cantidad")
        and transactional_profile
        and not product_catalog
    )
    if derived_unit_cost:
        quantities_all = _numeric_series(df, roles.get("cantidad"))
        costs_all = (costs_all * quantities_all).where(
            costs_all.notna() & quantities_all.notna()
        )
        warnings.append(
            f"El costo de venta se calculó como {roles['cantidad']} × "
            f"{roles['costo']}; el costo unitario no se sumó directamente."
        )
    has_costs = roles.get("costo") is not None and costs_all.notna().any()
    profits_all = (amounts_all - costs_all) if has_costs else None

    if roles.get("monto") is None:
        warnings.append(
            "No se detectó una columna de monto/ventas; los indicadores monetarios quedan en 0."
        )
    if not has_costs:
        warnings.append(
            "No se detectó una columna de costos; gastos, utilidad y margen requieren esa columna."
        )

    dates_all = (
        map_unique(df[roles["fecha"]], parse_date)
        if roles.get("fecha")
        else pd.Series([None] * len(df))
    )
    dates_all = dates_all.where(indicator_row_mask)
    has_dates = roles.get("fecha") is not None and dates_all.notna().any()
    sin_fecha = 0
    monto_sin_fecha = 0.0
    if not has_dates:
        warnings.append("No se detectó una columna de fecha; sin evolución mensual ni proyección.")
    else:
        # Fase 12: transparencia — ninguna fila se pierde en silencio. Las
        # ventas sin fecha legible SÍ suman al total del periodo completo,
        # pero no pueden ubicarse en la evolución mensual ni en filtros por mes.
        undated_mask = amounts_all.notna() & dates_all.isna()
        sin_fecha = int(undated_mask.sum())
        monto_sin_fecha = float(amounts_all[undated_mask].sum())
        if sin_fecha:
            amount_label = f"{monto_sin_fecha:,.0f}".replace(",", ".")
            if date_from or date_to:
                warnings.append(
                    f"El filtro excluye {sin_fecha} venta(s) sin fecha válida por un "
                    f"monto de {amount_label}; no es posible ubicarlas dentro del rango."
                )
            else:
                warnings.append(
                    f"{sin_fecha} venta(s) no tienen fecha válida; por un monto de {amount_label}, "
                    "se incluyen en el total global pero no en la evolución mensual."
                )

    # ── Evolución mensual (siempre sobre el periodo completo) ──
    monthly = pd.DataFrame()
    if has_dates:
        frame = pd.DataFrame(
            {
                "mes": dates_all.map(lambda d: d.strftime("%Y-%m") if pd.notna(d) else None),
                "ingresos": amounts_all,
            }
        )
        if has_costs:
            paired_all = amounts_all.notna() & costs_all.notna()
            frame["gastos"] = costs_all
            frame["utilidad"] = profits_all
            # Fase 12b §13: el margen MENSUAL debe usar el mismo denominador
            # pareado que el KPI global — el frontend calculaba utilidad/
            # ingresos del mes (con ventas sin costo en el denominador) y el
            # sparkline quedaba subestimado con cobertura parcial.
            frame["ingresos_pareados"] = amounts_all.where(paired_all)
            frame["_filas_con_ingreso"] = amounts_all.notna().astype(int)
            frame["_filas_pareadas"] = paired_all.astype(int)
        # Fase 12: solo se exige la fecha — una fila con costo legible pero
        # monto ilegible aportaba su gasto al KPI total y DESAPARECÍA del
        # gráfico mensual (el gráfico y el KPI no cuadraban).
        monthly = (
            frame.dropna(subset=["mes"]).groupby("mes").sum(numeric_only=True).sort_index()
        )

    # ── Parcialidad por mes (Fase 14) ──
    # Cada mes de la evolución declara hasta qué día tiene datos. El flag
    # `parcial` solo marca el ÚLTIMO mes de la serie (un hueco al final es
    # cobertura incompleta; un hueco al medio son días sin ventas reales).
    # Consumidores: la proyección lo excluye, Alertas no compara parcial vs
    # completo, la IA recibe la marca y el gráfico lo identifica.
    cobertura_dias: dict[str, int] = {}
    if has_dates and len(monthly):
        dias_frame = pd.DataFrame(
            {
                "mes": dates_all.map(lambda d: d.strftime("%Y-%m") if pd.notna(d) else None),
                "dia": dates_all.map(lambda d: int(d.day) if pd.notna(d) else None),
            }
        ).dropna(subset=["mes", "dia"])
        cobertura_dias = dias_frame.groupby("mes")["dia"].max().astype(int).to_dict()
    ultimo_mes = str(monthly.index[-1]) if len(monthly) else None

    def _mes_meta(mes: str) -> dict:
        dias_del_mes = int(pd.Period(mes).days_in_month)
        hasta = int(cobertura_dias.get(mes, dias_del_mes))
        return {
            "parcial": bool(mes == ultimo_mes and hasta < dias_del_mes),
            "cobertura_hasta_dia": hasta,
            "dias_del_mes": dias_del_mes,
        }

    def _month_extra(row) -> dict:
        if not has_costs:
            return {}
        ing_par = float(row.get("ingresos_pareados", 0.0) or 0.0)
        con_ingreso = int(row.get("_filas_con_ingreso", 0) or 0)
        pareadas = int(row.get("_filas_pareadas", 0) or 0)
        # Fase 13: un mes SIN filas pareadas no tiene utilidad conocida — la
        # suma de puros NaN daba 0.0 y "sin costos" se veía como "utilidad $0".
        if not pareadas:
            return {
                "gastos": round(float(row["gastos"]), 2),
                "utilidad": None,
                "margen_pareado_pct": None,
                "cobertura_costos_pct": 0.0 if con_ingreso else None,
            }
        utilidad_mes = float(row["utilidad"])
        return {
            "gastos": round(float(row["gastos"]), 2),
            "utilidad": round(utilidad_mes, 2),
            "margen_pareado_pct": (
                round(utilidad_mes / ing_par * 100, 1) if ing_par else None
            ),
            "cobertura_costos_pct": (
                round(pareadas / con_ingreso * 100, 1) if con_ingreso else None
            ),
        }

    evolucion = [
        {
            "mes": str(month),
            "ingresos": round(float(row["ingresos"]), 2),
            **_mes_meta(str(month)),
            **_month_extra(row),
        }
        for month, row in monthly.iterrows()
    ]

    if evolucion and evolucion[-1]["parcial"]:
        ult = evolucion[-1]
        # Fase 14b: el copy NO afirma una causa — el archivo no permite saber
        # si faltan datos, no hubo ventas o el periodo terminó a propósito.
        # Solo se declara el hecho (último registro) y la regla conservadora.
        warnings.append(
            f"El último registro disponible de {ult['mes']} corresponde al día "
            f"{ult['cobertura_hasta_dia']} de {ult['dias_del_mes']}. Para no "
            "comparar periodos con distinta cantidad de días registrados, este "
            "mes no se usa como mes completo: la proyección lo excluye y las "
            "alertas comparan meses completos."
        )

    # ── Selección por rango de fechas ──
    # Fase 18: un límite superior con granularidad de MES ("2025-12") cubre el
    # mes completo. pd.to_datetime lo convertía en el día 1 y los KPI perdían
    # los días 2–31 mientras la evolución mensual sí los mostraba.
    start = pd.to_datetime(date_from) if date_from else None
    if date_to and re.fullmatch(r"\d{4}-\d{2}", str(date_to).strip()):
        end = pd.Period(str(date_to).strip(), freq="M").end_time.normalize()
    else:
        end = pd.to_datetime(date_to) if date_to else None
    if has_dates and (start is not None or end is not None):
        mask = dates_all.map(
            lambda d: bool(
                pd.notna(d)
                and (start is None or d >= start)
                and (end is None or d <= end)
            )
        )
    else:
        mask = pd.Series([True] * len(df), index=df.index)
    mask &= indicator_row_mask

    selection = df[mask]
    amounts = amounts_all[mask]
    costs = costs_all[mask]
    profits = profits_all[mask] if profits_all is not None else None

    cost_quality: dict[str, Any] | None = None
    valid_costs_selection = costs.dropna().astype(float) if has_costs else pd.Series(dtype=float)
    if len(valid_costs_selection) >= 4:
        positive_costs = valid_costs_selection[valid_costs_selection > 0]
        if len(positive_costs) >= 4:
            q1 = float(positive_costs.quantile(0.25))
            q3 = float(positive_costs.quantile(0.75))
            upper = q3 + 1.5 * (q3 - q1)
            cost_outlier_mask = costs.notna() & ((costs <= 0) | (costs > upper))
            atypical_total = float(costs.loc[cost_outlier_mask].abs().sum())
            known_total = float(costs.dropna().abs().sum())
            cost_quality = {
                "registros_atipicos": int(cost_outlier_mask.sum()),
                "no_positivos": int((costs.notna() & (costs <= 0)).sum()),
                "limite_superior_iqr": round(upper, 2),
                "costo_absoluto_atipico": round(atypical_total, 2),
                "participacion_costo_absoluto_pct": (
                    round(atypical_total / known_total * 100, 1)
                    if known_total
                    else 0.0
                ),
            }
            if cost_quality["registros_atipicos"]:
                warnings.insert(
                    0,
                    f"{cost_quality['registros_atipicos']} costo(s) son no positivos o atípicos según IQR y concentran {cost_quality['participacion_costo_absoluto_pct']}% del costo absoluto. Los indicadores los conservan, pero deben revisarse antes de interpretar utilidad y margen.",
                )

    # ── Periodo anterior para las variaciones (Fase 10 §4.5) ──
    # Si la selección es un mes calendario completo, el periodo anterior es el
    # MES CALENDARIO anterior (mayo se compara con abril, no con una ventana de
    # 31 días que arrastra el 31 de marzo). Para rangos arbitrarios se mantiene
    # la ventana equivalente de días.
    prev_amounts = prev_costs = None
    prev_mask = None
    if has_dates and start is not None and end is not None:
        month_end = start + pd.offsets.MonthEnd(0)
        is_full_month = start.day == 1 and end.normalize() == month_end.normalize()
        if is_full_month:
            # Fase 13 (P0.4): si el mes seleccionado está INCOMPLETO (el último
            # dato del archivo cae dentro de este mes antes de fin de mes), se
            # compara contra los DÍAS EQUIVALENTES del mes anterior — comparar
            # 15 días contra 30 mostraba caídas falsas.
            max_data = dates_all.max()
            prev_end_full = start - pd.Timedelta(days=1)
            prev_start = prev_end_full.replace(day=1)
            mes_parcial_sel = bool(
                pd.notna(max_data)
                and start <= max_data < month_end.normalize()
                and max_data.strftime("%Y-%m") == start.strftime("%Y-%m")
            )
            if mes_parcial_sel:
                eq_day = min(int(max_data.day), int(prev_end_full.day))
                prev_end = prev_start + pd.Timedelta(days=eq_day - 1)
                warnings.append(
                    f"El mes seleccionado está incompleto (datos hasta el "
                    f"{max_data.strftime('%d/%m/%Y')}): la variación se compara "
                    f"con los primeros {eq_day} días del mes anterior, no con el "
                    "mes completo."
                )
            else:
                prev_end = prev_end_full
            prev_mask = dates_all.map(
                lambda d: bool(pd.notna(d) and prev_start <= d <= prev_end)
            )
        else:
            window = end - start
            prev_mask = dates_all.map(
                lambda d: bool(pd.notna(d) and (start - window - pd.Timedelta(days=1)) <= d < start)
            )
        if not prev_mask.any():
            prev_mask = None
    # Sin rango seleccionado ("todo el periodo") no hay periodo anterior
    # comparable: las variaciones quedan en null y la UI muestra "—".

    ingresos = float(amounts.dropna().sum())

    # ── Devoluciones/ajustes (Fase 12b §16) ──
    # Los montos negativos (reversas, notas de crédito) restan del total: los
    # "ingresos" son NETOS y el usuario debe verlo, no descubrirlo.
    negativos = amounts[amounts.notna() & (amounts < 0)]
    devoluciones = (
        {"monto": round(float(negativos.sum()), 2), "filas": int(len(negativos))}
        if len(negativos)
        else None
    )
    if devoluciones:
        warnings.append(
            f"Los ingresos mostrados son NETOS: incluyen {devoluciones['filas']} "
            f"monto(s) negativo(s) que restan {abs(devoluciones['monto']):,.0f} "
            "(devoluciones, reversas o ajustes).".replace(",", ".")
        )

    # ── Cobertura de costos (Fase 10 §4.1) ──
    # Utilidad y margen se calculan SOLO sobre las filas que tienen ingreso Y
    # costo. Antes se restaban los costos conocidos del total de ingresos, lo
    # que trataba los costos faltantes como $0 e inflaba la utilidad.
    filas_con_ingreso = int(amounts.notna().sum())
    paired_mask = amounts.notna() & costs.notna() if has_costs else None
    filas_pareadas = int(paired_mask.sum()) if paired_mask is not None else 0
    cobertura_pct = (
        round(filas_pareadas / filas_con_ingreso * 100, 1) if filas_con_ingreso else 0.0
    )

    gastos = float(costs.dropna().sum()) if has_costs else None
    if has_costs and filas_pareadas:
        ingresos_pareados = float(amounts[paired_mask].sum())
        utilidad = ingresos_pareados - float(costs[paired_mask].sum())
        margen = round(utilidad / ingresos_pareados * 100, 1) if ingresos_pareados else None
    else:
        ingresos_pareados = 0.0
        utilidad = None
        margen = None

    prev_utilidad = prev_margen = None
    if prev_mask is not None:
        prev_amounts = float(amounts_all[prev_mask].dropna().sum())
        prev_costs = float(costs_all[prev_mask].dropna().sum())
        if has_costs:
            prev_paired = amounts_all.notna() & costs_all.notna() & prev_mask
            if prev_paired.any():
                prev_ing_par = float(amounts_all[prev_paired].sum())
                prev_utilidad = prev_ing_par - float(costs_all[prev_paired].sum())
                prev_margen = (
                    round(prev_utilidad / prev_ing_par * 100, 1) if prev_ing_par else None
                )

    if has_costs and filas_con_ingreso and cobertura_pct < 99.5:
        warnings.append(
            f"{filas_con_ingreso - filas_pareadas} de {filas_con_ingreso} ventas no "
            f"tienen costo asociado (cobertura {cobertura_pct}%): la utilidad y el "
            "margen se calculan solo sobre las ventas con costo — son resultados "
            "PARCIALES, no el total del negocio."
        )

    kpis: dict = {
        "ingresos_totales": _kpi(ingresos, prev_amounts),
        # Semántica honesta (Fase 12b §11): esto cuenta FILAS del archivo, no
        # ventas confirmadas — la UI lo rotula "Registros". Sin una clave de
        # transacción declarada no se puede afirmar más.
        "transacciones": int(len(selection)),
        "ticket_promedio": round(float(amounts.dropna().mean()), 2) if amounts.notna().any() else 0.0,
        # §12: el ticket se calcula sobre las filas CON monto — si difiere del
        # total de registros, la UI muestra la base de cálculo.
        "registros_con_monto": filas_con_ingreso,
    }
    if devoluciones:
        kpis["devoluciones"] = devoluciones
    if roles.get("cantidad"):
        kpis["unidades_totales"] = round(
            float(_numeric_series(selection, roles["cantidad"]).dropna().sum()), 2
        )
    if has_costs and utilidad is not None:
        kpis["gastos_totales"] = _kpi(gastos, prev_costs)
        # Nota Fase 10 §4.2: esto es UTILIDAD BRUTA (venta − costo directo),
        # no ganancia neta — faltan gastos operacionales, sueldos, impuestos…
        # La clave JSON se mantiene por compatibilidad; la UI la rotula
        # "Utilidad Bruta" y "Resultado del Periodo".
        kpis["ganancia_neta"] = _kpi(utilidad, prev_utilidad)
        kpis["margen_utilidad_pct"] = {
            "valor": margen,
            "variacion_puntos": round(margen - prev_margen, 1)
            if margen is not None and prev_margen is not None
            else None,
        }
        kpis["flujo_caja"] = _kpi(utilidad, prev_utilidad)
        costo_pareado = float(costs[paired_mask].sum())
        kpis["cobertura_costos"] = {
            "filas_con_ingreso": filas_con_ingreso,
            "filas_con_ingreso_y_costo": filas_pareadas,
            "pct": cobertura_pct,
        }
        kpis["base_costos"] = {
            "filas_con_costo": int(costs.notna().sum()),
            "costo_total_conocido": round(gastos, 2),
            "filas_pareadas": filas_pareadas,
            "costo_pareado": round(costo_pareado, 2),
            "ingresos_pareados": round(ingresos_pareados, 2),
        }
    else:
        kpis["gastos_totales"] = None
        kpis["ganancia_neta"] = None
        kpis["margen_utilidad_pct"] = None
        kpis["flujo_caja"] = None

    # ── Agrupaciones sobre la selección ──
    def _has_data(role: str) -> bool:
        col = roles.get(role)
        if col is None:
            return False
        semantic = semantic_missing_mask(df[col], role)
        return bool((~physical_missing_mask(df[col]) & ~semantic).any())

    if currency.advertencia:
        warnings.insert(0, currency.advertencia)

    result: dict = {
        "moneda": currency.dominante,
        "moneda_mixta": currency.mixta,
        "moneda_detalle": currency.to_dict(),
        "datos_monetarios_disponibles": not currency.mixta,
        "mapeo": roles,
        "calculo_costos": {
            "origen": "cantidad_por_costo_unitario" if derived_unit_cost else "columna_costo",
            "columna_costo": roles.get("costo"),
            "columna_cantidad": roles.get("cantidad") if derived_unit_cost else None,
        } if has_costs else None,
        "calidad_costos": cost_quality,
        **({
            "exclusiones_indicadores": {
                "filas_anuladas": cancelled_rows,
                "columna_estado": status_column,
                "filas_totales_estructurales": total_rows,
            },
        } if status_column or cancelled_rows or total_rows else {}),
        # Fase 8: qué dimensiones REALES trae este dataset. El frontend adapta
        # Explorar y Resumen a esto (sin tarjetas vacías ni análisis imposibles).
        "dimensiones": {
            "fecha": bool(has_dates),
            # Fase 12: "monto" exige montos LEGIBLES, no solo texto en la
            # columna — si nada parsea, el frontend debe mostrar la guía de
            # mapeo, no un dashboard en $0.
            "monto": bool(amounts_all.notna().any()),
            "costo": bool(has_costs),
            "cantidad": _has_data("cantidad"),
            "categoria": _has_data("categoria"),
            "producto": _has_data("producto"),
            "canal": _has_data("canal"),
            "sucursal": _has_data("sucursal"),
            "cliente": _has_data("cliente"),
            "vendedor": _has_data("vendedor"),
        },
        "periodo": {
            "desde": date_from,
            "hasta": date_to,
            "mes_parcial": bool(locals().get("mes_parcial_sel", False)),
            "meses_disponibles": [str(m) for m in monthly.index] if has_dates else [],
            "sin_fecha": {
                "filas": sin_fecha,
                "monto": round(monto_sin_fecha, 2),
                "excluidas_por_filtro": bool((date_from or date_to) and sin_fecha),
            },
        },
        "kpis": kpis,
        "evolucion_mensual": evolucion,
    }

    group_costs = costs if has_costs else None
    if roles.get("categoria"):
        result["por_categoria"] = _group_sum(
            selection[roles["categoria"]], amounts, group_costs
        )
    canal_role = "canal" if roles.get("canal") else ("sucursal" if roles.get("sucursal") else None)
    result["agrupado_por_canal"] = canal_role
    if canal_role:
        # Fase 12: canal y producto también reciben utilidad/margen pareados
        # cuando hay costos — "qué canal/producto deja margen" es una de las
        # decisiones más citadas para una PyME.
        result["ventas_por_canal"] = _group_sum(
            selection[roles[canal_role]], amounts, group_costs
        )
    if roles.get("producto"):
        productos_completos = _group_sum(
            selection[roles["producto"]], amounts, group_costs
        )
        # Fase 12b §24: 12 productos — el Resumen muestra 5 y Explorar hasta
        # 8+; cortar en 5 dejaba a "Explorar" sin nada que explorar.
        result["top_productos"] = productos_completos[:12]
        # Fase 15: los LÍDERES se calculan sobre TODOS los productos ANTES del
        # recorte — un producto con brutas altas y devoluciones altas podía
        # desaparecer del top-12 (ordenado por netas) y las afirmaciones de
        # concentración quedaban ciegas a él.
        if productos_completos:
            def _lider(clave, minimo=False):
                candidatos = [
                    p for p in productos_completos if p.get(clave) is not None
                ]
                if not candidatos:
                    return None
                elegido = (min if minimo else max)(candidatos, key=lambda p: p[clave])
                lider = {"nombre": elegido["nombre"], clave: elegido[clave]}
                if clave == "ventas_brutas":
                    # La concentración comercial se afirma con ESTE número.
                    lider["participacion_bruta_pct"] = elegido.get(
                        "participacion_bruta_pct"
                    )
                return lider

            result["lideres_productos"] = {
                "por_ventas_brutas": _lider("ventas_brutas"),
                "por_ventas_netas": _lider("ventas_netas"),
                "por_utilidad": _lider("utilidad"),
                "mayor_devolucion": _lider("devoluciones", minimo=True),
                "total_productos": len(productos_completos),
            }

        # ── Fase 19: rentabilidad para DECIDIR (Explorar) ──
        # Resumen muestra los números; Explorar los interpreta. Clasificación
        # de portafolio por participación × margen (umbrales = las MEDIANAS
        # del propio archivo — la guía del analista compara contra tu propio
        # negocio, no contra rangos abstractos), productos con margen negativo,
        # ventas bajo costo y filas con margen atípico.
        if has_costs and productos_completos:
            con_margen = [
                item for item in productos_completos
                if item.get("margen_pct") is not None
                and item.get("participacion_bruta_pct") is not None
                and (item.get("filas_pareadas") or 0) > 0
            ]
            clasificacion: list[dict] = []
            umbrales = None
            if len(con_margen) >= 4:
                margenes = sorted(item["margen_pct"] for item in con_margen)
                participaciones = sorted(
                    item["participacion_bruta_pct"] for item in con_margen
                )

                def _mediana(valores: list[float]) -> float:
                    mitad = len(valores) // 2
                    if len(valores) % 2:
                        return float(valores[mitad])
                    return float((valores[mitad - 1] + valores[mitad]) / 2)

                margen_mediano = _mediana(margenes)
                participacion_mediana = _mediana(participaciones)
                umbrales = {
                    "margen_mediano_pct": round(margen_mediano, 1),
                    "participacion_mediana_pct": round(participacion_mediana, 2),
                }
                for item in con_margen:
                    alto_volumen = item["participacion_bruta_pct"] >= participacion_mediana
                    alto_margen = item["margen_pct"] >= margen_mediano
                    cuadrante = (
                        "estrella" if alto_volumen and alto_margen
                        else "vaca_lechera" if alto_volumen
                        else "oportunidad" if alto_margen
                        else "problema"
                    )
                    clasificacion.append({
                        "nombre": item["nombre"],
                        "participacion_bruta_pct": item["participacion_bruta_pct"],
                        "margen_pct": item["margen_pct"],
                        "utilidad": item.get("utilidad"),
                        "ingresos": item["ingresos"],
                        "filas_pareadas": item.get("filas_pareadas"),
                        "cuadrante": cuadrante,
                    })
            margen_negativo = sorted(
                (item for item in con_margen if item["margen_pct"] < 0),
                key=lambda item: item.get("utilidad") or 0,
            )[:10]
            paired_rows = amounts.notna() & costs.notna()
            bajo_costo_mask = paired_rows & (amounts < costs) & (amounts > 0)
            perdida_bajo_costo = float(
                (costs[bajo_costo_mask] - amounts[bajo_costo_mask]).sum()
            )
            margen_filas = (
                (amounts - costs) / amounts.where(amounts > 0)
            ).where(paired_rows)
            margen_valido = margen_filas.dropna()
            outliers_margen = 0
            if len(margen_valido) >= 20:
                q1_m, q3_m = margen_valido.quantile(0.25), margen_valido.quantile(0.75)
                iqr_m = float(q3_m - q1_m)
                if iqr_m > 0:
                    outliers_margen = int((
                        (margen_valido < q1_m - 3 * iqr_m)
                        | (margen_valido > q3_m + 3 * iqr_m)
                    ).sum())
            result["analisis_rentabilidad"] = {
                "clasificacion_productos": clasificacion,
                "umbrales": umbrales,
                "productos_margen_negativo": [
                    {
                        "nombre": item["nombre"],
                        "margen_pct": item["margen_pct"],
                        "utilidad": item.get("utilidad"),
                        "ingresos": item["ingresos"],
                    }
                    for item in margen_negativo
                ],
                "ventas_bajo_costo": {
                    "filas": int(bajo_costo_mask.sum()),
                    "perdida": round(perdida_bajo_costo, 2),
                },
                "filas_margen_atipico": outliers_margen,
            }

    # ── Fase 12: clientes (unicidad y concentración) ──
    # Riesgo clásico de PyME: depender de un cliente. Solo con columna cliente.
    if roles.get("cliente"):
        clientes_raw = selection[roles["cliente"]]
        no_identificado = {"sin nombre", "sin identificar", "cliente desconocido", "no informa"}
        absent = physical_missing_mask(clientes_raw) | semantic_missing_mask(
            clientes_raw, "cliente", column_type="texto"
        )
        valid_mask = ~absent & clientes_raw.map(
            lambda v: strip_accents_lower(str(v).strip()) not in no_identificado
        )
        if valid_mask.any():
            top = _sort_by_gross_share(
                _group_sum(clientes_raw[valid_mask], amounts[valid_mask], None)
            )
            # Fase 12b §21: el % del cliente principal es sobre las ventas CON
            # cliente identificado — si la mitad de las ventas no tiene
            # cliente, ese % NO es sobre el total y la UI debe decirlo.
            # Fase 13 (P0.3): la cobertura se mide sobre ventas BRUTAS
            # positivas — con devoluciones, el neto daba coberturas >100% o
            # negativas, ambas sin sentido.
            brutos_total = float(amounts[amounts > 0].sum())
            brutos_ident = float(amounts[valid_mask & (amounts > 0)].sum())
            result["clientes"] = {
                "unicos": int(clientes_raw[valid_mask].nunique()),
                "top": top[:5],
                # Fase 14b: la concentración es una afirmación de DISTRIBUCIÓN
                # → usa la participación bruta (suma 100%), no el % neto.
                "concentracion_top_pct": (
                    (
                        top[0].get("participacion_bruta_pct")
                        if top[0].get("participacion_bruta_pct") is not None
                        else top[0]["porcentaje"]
                    )
                    if top
                    else None
                ),
                "cobertura_identificacion_pct": (
                    round(brutos_ident / brutos_total * 100, 1) if brutos_total else None
                ),
            }

    # ── Fase 12: ventas por día de la semana ──
    # Con qué días se concentra la venta se decide dotación y horarios.
    if has_dates:
        dias_semana = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        sel_dates = dates_all[mask]
        wd = pd.DataFrame(
            {
                "dia": sel_dates.map(lambda d: d.weekday() if pd.notna(d) else None),
                "monto": amounts,
            }
        ).dropna(subset=["dia"])
        if not wd.empty:
            agg = wd.groupby("dia").agg(ingresos=("monto", "sum"), transacciones=("monto", "size"))
            result["por_dia_semana"] = [
                {
                    "dia": dias_semana[int(idx)],
                    "ingresos": round(float(row["ingresos"]), 2),
                    "transacciones": int(row["transacciones"]),
                }
                for idx, row in agg.sort_index().iterrows()
            ]

    # ── Fase 18: dimensiones flexibles (ventas por sucursal/región/zona/…) ──
    # Cualquier columna categórica razonable que NO sea ya un rol usado (canal,
    # categoría, producto…) genera su propia agrupación: cubre columnas propias
    # (Region, Zona, Tipo) y columnas enriquecidas por "Relacionar otras hojas"
    # (Sucursal, Comuna, Region de la maestra). El frontend las grafica.
    if bool(amounts_all.notna().any()):
        used_columns = {str(column) for column in roles.values() if column}
        priority_tokens = (
            "sucursal", "region", "comuna", "zona", "ciudad", "pais",
            "plataforma", "segmento", "tipo", "canal", "metodo", "forma",
        )
        skip_tokens = ("comentario", "observa", "nota", "descripcion", "email", "telefono", "direccion")
        id_prefixes = ("id", "codigo", "sku", "folio", "uuid", "rut", "numero", "nro")
        candidates: list[tuple[int, str]] = []
        for column in selection.columns:
            name = str(column)
            if name in used_columns or name == "hoja_origen":
                continue
            normalized = strip_accents_lower(name).replace("_", " ")
            compact = re.sub(r"[^a-z0-9]", "", normalized)
            if compact.startswith(id_prefixes):
                continue
            if any(token in normalized for token in skip_tokens):
                continue
            values = selection[name]
            filled = ~physical_missing_mask(values)
            if len(values) == 0 or float(filled.mean()) < 0.6:
                continue
            unique = values[filled].astype(str).str.strip().nunique()
            percentage_column = _is_percentage_column(name)
            if unique < 2 or (unique > 30 and not percentage_column):
                continue
            has_priority = any(token in normalized for token in priority_tokens)
            candidates.append((-1 if percentage_column else (0 if has_priority else 1), name))
        candidates.sort()
        flexibles: list[dict] = []
        for _, name in candidates[:4]:
            out_of_range = pd.Series(False, index=selection.index)
            grouping = selection[name]
            if _is_percentage_column(name):
                grouping, out_of_range = _percentage_buckets(selection, name)
            grupos = _group_sum(grouping, amounts, group_costs)
            if len(grupos) < 2:
                continue
            item = {
                "columna": name,
                "grupos": grupos[:12],
                "grupos_totales": len(grupos),
            }
            if bool(out_of_range.any()):
                item["fuera_de_rango"] = {
                    "filas": int(out_of_range.sum()),
                    "monto_asociado": round(float(amounts.loc[out_of_range].dropna().sum()), 2),
                }
            flexibles.append(item)
        if flexibles:
            result["agrupaciones_flexibles"] = flexibles

    # Fase 14: la proyección se calcula SOLO sobre meses completos — un mes
    # parcial al final deprimía la tasa de crecimiento con una caída ficticia.
    # Los meses proyectados siguen siendo los 3 POSTERIORES al final real de
    # la serie: la proyección nunca se superpone con un mes que tiene datos.
    monthly_completos = (
        monthly.iloc[:-1] if evolucion and evolucion[-1]["parcial"] else monthly
    )
    primer_mes_proyectado = (
        pd.Period(monthly.index[-1], freq="M") + 1 if len(monthly) else None
    )
    result["proyeccion"] = (
        _projection(monthly_completos, first_month=primer_mes_proyectado)
        if has_dates and not monthly_completos.empty
        else None
    )
    result["indicadores_financieros"] = {
        "disponible": False,
        "nota": (
            "ROA, ROE, liquidez, prueba ácida, rotación de inventario y días de "
            "cobro/pago requieren datos de balance (activos, pasivos, inventario, "
            "cuentas por cobrar/pagar). Se habilitan al conectar esos datos."
        ),
        "items": {ratio: None for ratio in FINANCIAL_RATIOS},
    }

    def _non_sales_contract(kind: str, rows_label: str) -> None:
        result["tipo_analisis"] = kind
        result["kpis"] = {
            "transacciones": None,
            rows_label: int(len(df)),
            "ingresos_totales": None,
            "ticket_promedio": None,
            "gastos_totales": None,
            "ganancia_neta": None,
            "margen_utilidad_pct": None,
            "flujo_caja": None,
        }
        result["evolucion_mensual"] = []
        result["por_categoria"] = []
        result["ventas_por_canal"] = []
        result["top_productos"] = []
        result["proyeccion"] = None

    def _column_containing(*tokens: str) -> str | None:
        return next(
            (
                column for normalized, column in normalized_columns.items()
                if all(token in normalized for token in tokens)
            ),
            None,
        )

    def _value_counts(column: str | None, limit: int = 20) -> list[dict[str, Any]]:
        if not column:
            return []
        values = df[column].loc[~physical_missing_mask(df[column])].astype(str).str.strip()
        return [
            {"nombre": str(name), "registros": int(total)}
            for name, total in values.value_counts().head(limit).items()
        ]
    if product_catalog:
        product_column = roles["producto"]
        cost_values = _numeric_series(df, roles.get("costo"))
        price_column = price_list_column or total_unit_cost_column or roles.get("monto")
        reference_type = (
            "precio_lista"
            if price_list_column
            else "costo_total_unitario"
            if total_unit_cost_column
            else None
        )
        price_values = _numeric_series(df, price_column)
        paired = cost_values.notna() & price_values.notna()
        margins = ((price_values - cost_values) / price_values.where(price_values != 0) * 100).where(paired)
        brand_column = next(
            (column for normalized, column in normalized_columns.items() if normalized == "marca"),
            None,
        )
        status_column = next(
            (
                column
                for normalized, column in normalized_columns.items()
                if normalized in {"estado", "activo", "activa"}
            ),
            None,
        )

        def stats(series: pd.Series) -> dict[str, float | None]:
            valid = series.dropna().astype(float)
            if valid.empty:
                return {"promedio": None, "mediana": None, "minimo": None, "maximo": None}
            return {
                "promedio": round(float(valid.mean()), 2),
                "mediana": round(float(valid.median()), 2),
                "minimo": round(float(valid.min()), 2),
                "maximo": round(float(valid.max()), 2),
            }

        valid_costs = cost_values.dropna().astype(float)
        positive_costs = valid_costs[valid_costs > 0]
        if len(positive_costs) >= 4:
            q1 = float(positive_costs.quantile(0.25))
            q3 = float(positive_costs.quantile(0.75))
            upper_cost = q3 + 1.5 * (q3 - q1)
        else:
            upper_cost = None
        atypical_cost = cost_values.notna() & (cost_values <= 0)
        if upper_cost is not None:
            atypical_cost = atypical_cost | (cost_values > upper_cost)

        ranking = pd.DataFrame(
            {
                "producto": df[product_column].astype(str),
                "costo": cost_values,
                "precio_lista": price_values,
                "margen_potencial_pct": margins,
                "requiere_revision": atypical_cost,
            }
        ).dropna(subset=["costo"]).sort_values("costo", ascending=False).head(12)

        def counts(column: str | None) -> list[dict[str, Any]]:
            if not column:
                return []
            values = df[column].loc[~physical_missing_mask(df[column])].astype(str).str.strip()
            return [
                {"nombre": str(name), "productos": int(total)}
                for name, total in values.value_counts().head(20).items()
            ]

        statuses = (
            df[status_column].astype(str).map(strip_accents_lower)
            if status_column
            else pd.Series([], dtype=str)
        )
        result["tipo_analisis"] = "catalogo_productos"
        result["analisis_productos"] = {
            "productos": int(df[product_column].loc[~physical_missing_mask(df[product_column])].nunique()),
            "referencia_tipo": reference_type,
            "costos": stats(cost_values),
            "precios_lista": stats(price_values),
            "margen_potencial": stats(margins),
            # No es valor de inventario: representa una unidad de cada fila
            # del catalogo. Se expone con ese nombre explicito para que la UI
            # no lo presente como un gasto real del negocio.
            "totales_catalogo_unitario": ({
                "costo": round(float(cost_values.dropna().sum()), 2),
                "precio_lista": round(float(price_values.dropna().sum()), 2),
                "utilidad_potencial": round(
                    float((price_values[paired] - cost_values[paired]).sum()), 2
                ),
                "productos_con_comparacion": int(paired.sum()),
            } if cost_values.notna().any() else None),
            "cobertura_costo_pct": round(float(cost_values.notna().mean() * 100), 1) if len(df) else 0.0,
            "ranking_costos": ranking.to_dict(orient="records"),
            "costos_tipicos": stats(cost_values.where(~atypical_cost)),
            "costos_a_revisar": {
                "registros": int(atypical_cost.sum()),
                "no_positivos": int((cost_values.notna() & (cost_values <= 0)).sum()),
                "sobre_limite_iqr": int(
                    (cost_values > upper_cost).sum()
                    if upper_cost is not None
                    else 0
                ),
                "limite_superior_iqr": (
                    round(upper_cost, 2) if upper_cost is not None else None
                ),
            },
            "categorias": counts(roles.get("categoria")),
            "marcas": counts(brand_column),
            "activos": int(statuses.isin({"si", "sí", "activo", "activa", "vigente"}).sum()) if len(statuses) else None,
            "inactivos": int(statuses.isin({"no", "inactivo", "inactiva", "descontinuado"}).sum()) if len(statuses) else None,
        }
        # Un costo/precio unitario es una propiedad del catálogo, no un hecho
        # transaccional. Se retiran las sumas comerciales genéricas para que
        # ningún consumidor las presente como gasto o ingreso del negocio.
        result["kpis"] = {
            "transacciones": int(len(df)),
            "productos": result["analisis_productos"]["productos"],
            "ingresos_totales": None,
            "ticket_promedio": None,
            "gastos_totales": None,
            "ganancia_neta": None,
            "margen_utilidad_pct": None,
            "flujo_caja": None,
        }
        result["evolucion_mensual"] = []
        result["por_categoria"] = []
        result["ventas_por_canal"] = []
        result["top_productos"] = []
        result["proyeccion"] = None
        reference_label = (
            "Costo_Total_Unitario"
            if reference_type == "costo_total_unitario"
            else "Precio_Lista"
        )
        if cost_values.notna().any():
            warnings.append(
                "Esta hoja se interpreta como catálogo de productos: "
                f"Costo_Unitario y {reference_label} se resumen por producto y no se suman como ventas."
            )
        else:
            warnings.append(
                "Esta hoja se interpreta como catálogo de productos: el precio de lista se resume por producto y no se suma como ventas reales."
            )
        if bool(atypical_cost.any()):
            warnings.append(
                f"{int(atypical_cost.sum())} costo(s) unitario(s) requieren revisión por ser no positivos o atípicos según IQR; no se corrigen ni excluyen de los totales."
            )
        result["advertencias"] = warnings
    elif campaign_profile:
        investment_column = _column_containing("inversion")
        impressions_column = _column_containing("impresion")
        clicks_column = _column_containing("clic")
        platform_column = _column_containing("plataforma")
        status_column = _column_containing("estado")
        investment = _numeric_series(df, investment_column)
        impressions = _numeric_series(df, impressions_column)
        clicks = _numeric_series(df, clicks_column)
        total_investment = float(investment.dropna().sum())
        total_impressions = float(impressions.dropna().sum())
        total_clicks = float(clicks.dropna().sum())
        _non_sales_contract("campanas_marketing", "campanas")
        # Fase 18: métricas POR PLATAFORMA para graficar (inversión, clics,
        # CTR y CPC por plataforma) y control de negocio clics > impresiones.
        por_plataforma: list[dict[str, Any]] = []
        if platform_column:
            plat_frame = pd.DataFrame({
                "plataforma": df[platform_column].astype(str).str.strip(),
                "inversion": investment,
                "impresiones": impressions,
                "clics": clicks,
            })
            plat_frame = plat_frame[plat_frame["plataforma"] != ""]
            for name, g in plat_frame.groupby("plataforma"):
                inv = float(g["inversion"].dropna().sum())
                imp = float(g["impresiones"].dropna().sum())
                clk = float(g["clics"].dropna().sum())
                por_plataforma.append({
                    "nombre": str(name),
                    "campanas": int(len(g)),
                    "inversion": round(inv, 2),
                    "impresiones": round(imp, 2),
                    "clics": round(clk, 2),
                    "ctr_pct": round(clk / imp * 100, 2) if imp else None,
                    "cpc": round(inv / clk, 2) if clk else None,
                })
            por_plataforma.sort(key=lambda item: item["inversion"], reverse=True)
        ctr_par = clicks.notna() & impressions.notna() & (impressions > 0)
        ctr_sobre_100 = int((ctr_par & (clicks > impressions)).sum())
        result["analisis_campanas"] = {
            "campanas": int(len(df)),
            "inversion": round(total_investment, 2),
            "impresiones": round(total_impressions, 2),
            "clics": round(total_clicks, 2),
            "ctr_pct": round(total_clicks / total_impressions * 100, 2) if total_impressions else None,
            "cpc": round(total_investment / total_clicks, 2) if total_clicks else None,
            "plataformas": _value_counts(platform_column),
            "estados": _value_counts(status_column),
            "por_plataforma": por_plataforma,
            "clics_sobre_impresiones": ctr_sobre_100,
        }
        warnings = [
            "Esta hoja se interpreta como campañas de marketing: inversión, impresiones, clics, CTR y CPC no se presentan como ventas."
        ]
        if ctr_sobre_100:
            warnings.append(
                f"{ctr_sobre_100} campaña(s) registran más clics que impresiones "
                "(CTR sobre 100%): revisa esos registros en el origen."
            )
    elif inventory_profile:
        stock_column = (
            _column_containing("stock", "disponible")
            or _column_containing("stock", "fisico")
            or _column_containing("stock", "sistema")
            or _column_containing("stock")
        )
        minimum_column = _column_containing("stock", "minimo")
        updated_column = _column_containing("ultima", "actualizacion")
        inventory_value_column = _column_containing("valor", "inventario")
        reference_cost_column = _column_containing("costo", "unitario")
        committed_column = _column_containing("unidades", "comprometidas")
        difference_column = _column_containing("diferencia", "conteo")
        stock = _numeric_series(df, stock_column)
        minimum = _numeric_series(df, minimum_column)
        inventory_value = _numeric_series(df, inventory_value_column)
        reference_cost = _numeric_series(df, reference_cost_column)
        committed = _numeric_series(df, committed_column)
        differences = _numeric_series(df, difference_column)
        paired_stock = stock.notna() & minimum.notna()
        _non_sales_contract("inventario", "registros_inventario")
        # Fase 18: stock POR SUCURSAL para graficar dónde está la existencia y
        # dónde se concentran los quiebres; más controles de stock negativo.
        stocks_negativos = int((stock < 0).sum())
        por_sucursal: list[dict[str, Any]] = []
        sucursal_column = roles.get("sucursal")
        if sucursal_column:
            inv_frame = pd.DataFrame({
                "sucursal": df[sucursal_column].astype(str).str.strip(),
                "stock": stock,
                "bajo": (paired_stock & (stock < minimum)),
                "negativo": stock < 0,
            })
            inv_frame = inv_frame[inv_frame["sucursal"] != ""]
            for name, g in inv_frame.groupby("sucursal"):
                por_sucursal.append({
                    "nombre": str(name),
                    "registros": int(len(g)),
                    "stock": round(float(g["stock"].dropna().sum()), 2),
                    "bajo_minimo": int(g["bajo"].sum()),
                    "stocks_negativos": int(g["negativo"].sum()),
                })
            por_sucursal.sort(key=lambda item: item["stock"], reverse=True)
        result["analisis_inventario"] = {
            "registros": int(len(df)),
            "productos": int(df[roles["producto"]].loc[~physical_missing_mask(df[roles["producto"]])].nunique()),
            "stock_total": round(float(stock.dropna().sum()), 2),
            "stock_minimo_total": round(float(minimum.dropna().sum()), 2),
            "valor_inventario": (
                round(float(inventory_value.dropna().sum()), 2)
                if inventory_value.notna().any()
                else None
            ),
            "costo_referencia_promedio": (
                round(float(reference_cost.dropna().mean()), 2)
                if reference_cost.notna().any()
                else None
            ),
            "unidades_comprometidas": (
                round(float(committed.dropna().sum()), 2)
                if committed.notna().any()
                else None
            ),
            "diferencia_conteo": (
                round(float(differences.dropna().sum()), 2)
                if differences.notna().any()
                else None
            ),
            "bajo_minimo": int((paired_stock & (stock < minimum)).sum()),
            "stocks_negativos": stocks_negativos,
            "cobertura_stock_pct": round(float(stock.notna().mean() * 100), 1) if len(df) else 0.0,
            "sucursales": _value_counts(roles.get("sucursal")),
            "por_sucursal": por_sucursal,
            "columna_actualizacion": updated_column,
        }
        warnings = [
            "Esta hoja se interpreta como inventario: el stock se resume como existencia y no como ventas o ingresos."
        ]
        if stocks_negativos:
            warnings.append(
                f"{stocks_negativos} registro(s) de inventario tienen stock "
                "negativo: pueden ser ajustes pendientes o errores de captura."
            )
    elif not transactional_profile:
        _non_sales_contract("generico", "registros")
        valid_cells = int(sum((~physical_missing_mask(df[column])).sum() for column in df.columns))
        total_cells = max(int(df.shape[0] * df.shape[1]), 1)

        # Fase 18: perfil estructural CON contenido — distribuciones de las
        # columnas categóricas y resumen de las numéricas, para que hojas de
        # clientes, sucursales, trabajadores, metas u otras tengan un resumen
        # útil y graficable sin inventar ventas.
        def _subtipo_generico() -> str | None:
            if non_sales_profile and non_sales_profile != "inventario":
                return non_sales_profile
            tokens = " ".join(
                strip_accents_lower(str(column)).replace("_", " ")
                for column in df.columns
            )
            if any(t in tokens for t in ("cargo", "sueldo", "salario", "empleado", "trabajador", "contrato")):
                return "trabajadores"
            if any(t in tokens for t in ("meta", "objetivo", "cumplimiento", "presupuesto")):
                return "metas"
            if roles.get("cliente") or any(t in tokens for t in ("email", "telefono", "rut")):
                return "clientes"
            if roles.get("sucursal") or any(t in tokens for t in ("comuna", "region", "direccion")):
                return "sucursales"
            return None

        subtype = _subtipo_generico()
        distribuciones_candidatas: list[tuple[int, dict[str, Any]]] = []
        numericas_candidatas: list[tuple[int, dict[str, Any], pd.Series]] = []
        id_prefixes = ("id", "codigo", "sku", "folio", "uuid", "rut", "numero", "nro")
        skip_tokens = ("email", "telefono", "direccion", "comentario", "observa", "nota", "descripcion", "nombre")

        numeric_priority: dict[str, tuple[str, ...]] = {
            "compras": ("total compra", "monto neto compra", "iva", "cantidad comprada", "costo unitario", "flete", "descuento"),
            "gastos": ("total gasto", "monto neto", "iva", "categoria", "tipo gasto"),
            "cobranzas": ("monto pago",),
            "metas": ("meta venta", "meta margen", "meta nuevos clientes"),
            "historial_costos": ("costo unitario",),
            "productos": ("precio lista", "stock minimo", "costo unitario"),
            "clientes": ("limite credito", "condicion pago"),
            "trabajadores": ("comision", "sueldo", "salario"),
        }

        def _priority(name: str) -> int:
            preferred = numeric_priority.get(subtype or "", ())
            for index, token in enumerate(preferred):
                if token in name:
                    return index
            return len(preferred) + 20

        def _numeric_format(name: str) -> tuple[str, str]:
            if _is_percentage_column(name):
                return "porcentaje", "promedio"
            if any(token in name for token in ("costo unitario", "costo ultima compra", "precio lista", "comision")):
                return "moneda" if "comision" not in name else "porcentaje", "promedio"
            if "dias" in name:
                return "numero", "promedio"
            if any(token in name for token in ("monto", "total", "valor", "limite credito", "flete", "iva", "costo", "precio", "meta venta")):
                return "moneda", "total"
            return "numero", "total"

        for column in df.columns:
            name = str(column)
            normalized = strip_accents_lower(name).replace("_", " ")
            compact = re.sub(r"[^a-z0-9]", "", normalized)
            if compact.startswith(id_prefixes) or any(t in normalized for t in skip_tokens):
                continue
            values = df[name]
            filled = ~physical_missing_mask(values)
            if not bool(filled.any()):
                continue
            numeric_values = _numeric_series(df, name)
            numeric_ratio = float(numeric_values.notna().sum()) / max(int(filled.sum()), 1)
            unique = values[filled].astype(str).str.strip().nunique()
            if numeric_ratio >= 0.8 and unique > 1:
                valid = numeric_values.dropna().astype(float)
                formato, destacado = _numeric_format(normalized)
                if formato == "porcentaje" and not valid.empty:
                    # Los porcentajes pueden venir como 0,18 o 18. Se expresan
                    # siempre en puntos porcentuales, incluso si la misma
                    # columna mezcla ambas convenciones, sin alterar el dataset.
                    valid = valid.where(valid.abs() > 1.5, valid * 100.0)
                    numeric_values = numeric_values.where(
                        numeric_values.abs() > 1.5, numeric_values * 100.0
                    )
                item = {
                    "columna": name,
                    "total": (
                        round(float(valid.sum()), 2)
                        if destacado == "total"
                        else None
                    ),
                    "promedio": round(float(valid.mean()), 2),
                    "mediana": round(float(valid.median()), 2),
                    "minimo": round(float(valid.min()), 2),
                    "maximo": round(float(valid.max()), 2),
                    "formato": formato,
                    "destacado": destacado,
                    "valores_validos": int(len(valid)),
                    "fuera_rango": (
                        int(((valid < 0) | (valid > 100)).sum())
                        if formato == "porcentaje"
                        else 0
                    ),
                }
                numericas_candidatas.append((_priority(normalized), item, numeric_values))
            elif 2 <= unique <= 30:
                distribution_priority = (
                    0 if any(token in normalized for token in ("estado", "categoria", "segmento", "region", "tipo", "medio", "forma", "activo", "fuente"))
                    else 10
                )
                distribuciones_candidatas.append((distribution_priority, {
                    "columna": name,
                    "valores": _value_counts(name, limit=12),
                    "valores_totales": int(unique),
                }))

        numericas_candidatas.sort(key=lambda item: (item[0], str(item[1]["columna"])))
        distribuciones_candidatas.sort(key=lambda item: (item[0], str(item[1]["columna"])))
        numericas = [item for _, item, _ in numericas_candidatas[:8]]
        distribuciones = [item for _, item in distribuciones_candidatas[:6]]

        evolution = None
        date_column = roles.get("fecha") or next(
            (
                column
                for normalized, column in normalized_columns.items()
                if "fecha" in normalized or normalized.startswith("mes")
            ),
            None,
        )
        if date_column and numericas_candidatas:
            _, primary_numeric, primary_values = numericas_candidatas[0]
            parsed_dates = map_unique(df[date_column], parse_date)
            temporal = pd.DataFrame({
                "mes": parsed_dates.map(
                    lambda value: value.strftime("%Y-%m") if pd.notna(value) else None
                ),
                "valor": primary_values,
            }).dropna(subset=["mes", "valor"])
            if not temporal.empty:
                operation = primary_numeric["destacado"]
                grouped = temporal.groupby("mes")["valor"]
                series = grouped.mean() if operation == "promedio" else grouped.sum()
                evolution = {
                    "columna": primary_numeric["columna"],
                    "operacion": operation,
                    "formato": primary_numeric["formato"],
                    "valores": [
                        {"mes": str(month), "valor": round(float(value), 2)}
                        for month, value in series.sort_index().items()
                    ],
                }

        result["analisis_generico"] = {
            "registros": int(len(df)),
            "columnas": int(len(df.columns)),
            "celdas_informadas_pct": round(valid_cells / total_cells * 100, 1),
            "columnas_disponibles": [str(column) for column in df.columns],
            "subtipo": subtype,
            "distribuciones": distribuciones,
            "numericas": numericas,
            "evolucion": evolution,
        }
        profile_labels = {
            "compras": "compras y abastecimiento",
            "gastos": "gastos operacionales",
            "cobranzas": "cobranzas y pagos",
            "metas": "metas planificadas",
            "historial_costos": "historial de costos",
            "productos": "maestra de productos",
            "proveedores": "maestra de proveedores",
            "clientes": "maestra de clientes",
            "sucursales": "maestra de sucursales",
            "trabajadores": "equipo de trabajo",
        }
        label = profile_labels.get(subtype or "", "perfil estructural")
        warnings = [
            f"Esta hoja se interpreta como {label}. Sus valores se resumen con semántica operacional y no se presentan como ventas, ticket ni utilidad."
        ]
        percentage_issues = sum(
            int(item.get("fuera_rango", 0)) for item in numericas
        )
        if percentage_issues:
            warnings.append(
                f"{percentage_issues} porcentaje(s) están fuera del rango 0–100%; se conservan y se señalan para revisión."
            )
    result["advertencias"] = warnings
    if currency.mixta:
        _block_monetary_outputs(result, currency)
    return _json_safe_metrics(result)
