"""Catálogo ampliado de relaciones entre hojas para el workspace de Resumen.

Este módulo NO reemplaza ``detect_relationships`` (que sigue alimentando la
autodetección de "Visión del negocio"). Vive aparte para poder listar TODAS las
relaciones seguras de un libro —no solo la recomendada— y clasificarlas en una
plantilla de dashboard, sin alterar la semántica que usa el modo ``append_join``.

Reutiliza los mismos umbrales y validaciones de :mod:`multi_sheet`:
- ``relation_stats`` mide cobertura, solapamiento, cardinalidad y seguridad.
- Solo se aprueban ``uno_a_uno`` y ``muchos_a_uno`` (left join). Se bloquean
  ``uno_a_muchos``, ``muchos_a_muchos`` y claves derechas duplicadas.
- Dos hojas transaccionales compatibles NO se relacionan: son responsabilidad
  del modo ``append`` ("Unir periodos de venta").
"""

from __future__ import annotations

import itertools
import re
import unicodedata
from typing import Any

import pandas as pd

from .business import _dates, _sheet_kind, _text_key
from .mapping import norm_key, resolve_mapping
from .metrics import (
    CurrencyDetection,
    is_transaction_profile,
)
from .multi_sheet import (
    MAX_RELATION_KEYS,
    _candidate_pairs,
    is_unit_cost_column,
    join_related_frames,
    relation_stats,
)
from .quality import find_column

# Plantillas de dashboard que el frontend sabe renderizar.
RELATIONSHIP_TEMPLATES = (
    "products_sales",
    "sales_costs",
    "sales_inventory",
    "sales_customers",
    "sales_sellers",
    "sales_branches",
    "purchases_costs",
    "expenses_branches",
    "generic",
)


def _slug(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char)).lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-") or "hoja"


def relationship_id(
    left_sheet: str,
    right_sheet: str,
    left_keys: list[str],
    right_keys: list[str],
) -> str:
    """ID determinista derivado de las hojas y claves (Parte 4)."""

    left_part = "+".join(_slug(key) for key in left_keys)
    right_part = "+".join(_slug(key) for key in right_keys)
    return f"{_slug(left_sheet)}~{_slug(right_sheet)}~{left_part}~{right_part}"


def _inventory_product_key(frame: pd.DataFrame, mapping: dict[str, str]) -> str | None:
    return (
        mapping.get("producto")
        or find_column(frame.columns, "sku", "producto")
        or find_column(frame.columns, "id", "producto")
    )


def collapse_inventory_snapshots(
    frame: pd.DataFrame,
    keys: list[str] | None = None,
    mapping: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Reduce una hoja de inventario con varios snapshots al último válido por
    clave, para que su relación con ventas sea muchos_a_uno (no multiplica filas).

    Si no hay fecha de snapshot se toma la última ocurrencia. Cuando no hay
    duplicados el resultado es idéntico a la entrada.
    """

    if keys is None:
        product_key = _inventory_product_key(frame, mapping or {})
        keys = [product_key] if product_key else []
    valid_keys = [key for key in keys if key and key in frame.columns]
    if not valid_keys:
        return frame
    date_col = find_column(frame.columns, "fecha") or find_column(frame.columns, "snapshot")
    work = frame.copy()
    if date_col and date_col in work.columns:
        work["__snapshot_order"] = _dates(work, date_col)
        valid_dates = work["__snapshot_order"].dropna()
        if not valid_dates.empty:
            # A snapshot is a coherent cut of the whole inventory. Mixing the
            # latest row per SKU can carry stale branches from older cuts and
            # inflate stock. Prefer the latest global cut, then deduplicate keys.
            work = work.loc[work["__snapshot_order"].eq(valid_dates.max())]
        work = work.sort_values("__snapshot_order", kind="stable")
    grouped = work.groupby(
        [work[key].map(_text_key) for key in valid_keys], dropna=False, sort=False
    )
    collapsed = grouped.tail(1).drop(columns=["__snapshot_order"], errors="ignore")
    collapsed = collapsed.reset_index(drop=True)
    collapsed.attrs.update(frame.attrs)
    return collapsed


def _has_derived_unit_cost(
    right_mapping: dict[str, str],
    left_mapping: dict[str, str],
) -> bool:
    """¿La derecha aporta costo unitario que la venta puede multiplicar?"""

    return bool(
        is_unit_cost_column(right_mapping.get("costo"))
        and left_mapping.get("cantidad")
        and left_mapping.get("monto")
    )


def _is_sales_transaction(
    name: str,
    frame: pd.DataFrame,
    mapping: dict[str, str],
) -> bool:
    """Reconoce ventas por semántica aunque la hoja se llame solo "Enero".

    Los dominios operacionales conocidos (compras, gastos, inventario, etc.)
    nunca se reinterpretan como ventas. Para nombres neutros se exige el perfil
    transaccional completo detectado por el motor.
    """

    kind = _sheet_kind(name, frame)
    if kind == "ventas":
        return True
    sheet_tokens = set(_slug(name).split("-"))
    non_sales_tokens = {
        "compra",
        "compras",
        "gasto",
        "gastos",
        "inventario",
        "stock",
        "costo",
        "costos",
        "producto",
        "productos",
        "cliente",
        "clientes",
        "proveedor",
        "proveedores",
        "cobranza",
        "cobranzas",
        "meta",
        "metas",
        "sucursal",
        "sucursales",
        "vendedor",
        "vendedores",
    }
    if sheet_tokens & non_sales_tokens:
        return False
    return is_transaction_profile(frame.columns, mapping)


def classify_relationship_template(
    left_name: str,
    left_frame: pd.DataFrame,
    left_mapping: dict[str, str],
    right_name: str,
    right_frame: pd.DataFrame,
    right_mapping: dict[str, str],
) -> tuple[str, str, str]:
    """Clasifica la relación en (template, label, purpose).

    Se basa en el perfil detectado de cada hoja (roles del mapeo + columnas +
    nombre como señal secundaria), nunca en nombres exactos de hoja.
    """

    left_kind = _sheet_kind(left_name, left_frame)
    right_kind = _sheet_kind(right_name, right_frame)
    left_sales = _is_sales_transaction(left_name, left_frame, left_mapping)
    label = f"{right_name} ↔ {left_name}"

    def build(template: str, purpose: str, pretty: str) -> tuple[str, str, str]:
        return template, pretty, purpose

    # Inventario puede traer costo unitario, pero no es una maestra de costos:
    # suele tener varias sucursales/snapshots por SKU. Clasificarlo primero evita
    # ofrecerlo como una unión many-to-one que después falla por claves repetidas.
    if left_sales and right_kind == "inventario":
        return build("sales_inventory", "ventas_inventario", f"{left_name} ↔ {right_name}")
    # Ventas ↔ Costos: la maestra aporta costo unitario multiplicable por cantidad.
    if left_sales and _has_derived_unit_cost(right_mapping, left_mapping):
        return build("sales_costs", "ventas_costos", f"{left_name} ↔ {right_name}")
    if left_sales and right_kind in {"costos", "historial_costos"}:
        return build("sales_costs", "ventas_costos", f"{left_name} ↔ {right_name}")
    if left_sales and right_kind == "clientes":
        return build("sales_customers", "ventas_clientes", f"{left_name} ↔ {right_name}")
    if left_sales and right_kind == "vendedores":
        return build("sales_sellers", "ventas_vendedores", f"{left_name} ↔ {right_name}")
    if left_sales and right_kind == "sucursales":
        return build("sales_branches", "ventas_sucursales", f"{left_name} ↔ {right_name}")
    if left_sales and right_kind == "productos":
        return build("products_sales", "productos_ventas", f"{right_name} ↔ {left_name}")
    if left_kind == "compras" and right_kind in {"costos", "historial_costos", "productos", "proveedores"}:
        return build("purchases_costs", "compras_costos", f"{left_name} ↔ {right_name}")
    if left_kind == "gastos" and right_kind == "sucursales":
        return build("expenses_branches", "gastos_sucursales", f"{left_name} ↔ {right_name}")
    # Solo una tabla de ventas puede producir "Ventas ↔ Costos". Inventario,
    # compras u otros hechos también pueden traer monto/cantidad, pero tratarlos
    # como ventas crea dashboards financieros falsos.
    if left_sales and _has_derived_unit_cost(right_mapping, left_mapping):
        return build("sales_costs", "ventas_costos", f"{left_name} ↔ {right_name}")
    # Ventas contra una maestra genérica de producto.
    if left_sales and right_kind == "productos" and left_mapping.get("producto"):
        return build("products_sales", "productos_ventas", f"{right_name} ↔ {left_name}")
    return build("generic", "relacion_generica", label)


def _unsupported_generic_pair(
    left_name: str,
    left: pd.DataFrame,
    right_name: str,
    right: pd.DataFrame,
) -> bool:
    """Descarta cruces que comparten una clave pero no tienen todavía una
    plantilla empresarial honesta. No deben aparecer para terminar luego en
    "Conexión no disponible"."""

    kinds = {_sheet_kind(left_name, left), _sheet_kind(right_name, right)}
    return kinds in (
        {"inventario", "costos"},
        {"inventario", "historial_costos"},
    )


def _consolidated_sales_relationships(
    frames: dict[str, pd.DataFrame],
    resolved: dict[str, dict[str, str]],
    results: dict[str, dict],
) -> list[dict[str, Any]]:
    """Crea conexiones explícitas de todos los periodos de venta con una
    dimensión de costos/productos. La izquierda se concatena, nunca se une
    horizontalmente, por lo que no multiplica filas ni altera ventas."""

    sales_names = [
        name
        for name, frame in frames.items()
        if _is_sales_transaction(name, frame, resolved[name])
    ]
    if len(sales_names) < 2:
        return []

    combined = pd.concat(
        [frames[name].copy() for name in sales_names],
        ignore_index=True,
        sort=False,
    )
    consolidated: list[dict[str, Any]] = []
    supported_right_kinds = {
        "costos",
        "productos",
        "clientes",
        "vendedores",
        "sucursales",
        "cobranzas",
        "historial_costos",
    }
    for right_name, right in frames.items():
        if right_name in sales_names:
            continue
        right_kind = _sheet_kind(right_name, right)
        right_mapping = resolved[right_name]
        if right_kind not in supported_right_kinds:
            continue
        combined_mapping = resolve_mapping(
            [str(column) for column in combined.columns],
            resolved[sales_names[0]],
        )
        if right_kind == "historial_costos":
            left_key = (
                find_column(combined.columns, "sku", "producto")
                or find_column(combined.columns, "id", "producto")
            )
            right_key = (
                find_column(right.columns, "sku", "producto")
                or find_column(right.columns, "id", "producto")
            )
            if not left_key or not right_key:
                continue
            left_values = {
                _text_key(value) for value in combined[left_key] if _text_key(value)
            }
            right_values = {
                _text_key(value) for value in right[right_key] if _text_key(value)
            }
            overlap = (
                len(left_values & right_values) / max(len(left_values), 1)
            )
            consolidated.append(
                {
                    "id": relationship_id(
                        "todas-las-ventas", right_name, [left_key], [right_key]
                    ),
                    "left_sheet": sales_names[0],
                    "append_sheets": sales_names,
                    "right_sheet": right_name,
                    "left_keys": [left_key],
                    "right_keys": [right_key],
                    "type": "left",
                    "template": "sales_costs",
                    "label": f"Todas las ventas ↔ {right_name}",
                    "purpose": "ventas_costos",
                    "coverage_left": round(overlap, 4),
                    "coverage_right": 1.0,
                    "overlap": round(overlap, 4),
                    "cardinality": "muchos_a_uno_temporal",
                    "safe": True,
                    "recommended": False,
                    "source": "automatic",
                    "currency_compatible": True,
                    "reason": None,
                    "join_strategy": "vigencia_por_fecha",
                }
            )
            continue
        right_eval = right
        best, _ = _best_relationship_for_pair(
            sales_names[0],
            combined,
            right_name,
            right_eval,
        )
        if not best or not best["safe"]:
            continue
        template, label, purpose = classify_relationship_template(
            sales_names[0],
            combined,
            combined_mapping,
            right_name,
            right,
            right_mapping,
        )
        currency_ok = all(
            _currency_compatible(
                purpose, sale_name, right_name, results
            )[0]
            for sale_name in sales_names
        )
        if not currency_ok:
            continue
        consolidated.append(
            {
                "id": relationship_id(
                    "todas-las-ventas",
                    right_name,
                    best["left_keys"],
                    best["right_keys"],
                ),
                "left_sheet": sales_names[0],
                "append_sheets": sales_names,
                "right_sheet": right_name,
                "left_keys": best["left_keys"],
                "right_keys": best["right_keys"],
                "type": "left",
                "template": template,
                "label": f"Todas las ventas ↔ {right_name}",
                "purpose": purpose,
                "coverage_left": best["coverage_left"],
                "coverage_right": best["coverage_right"],
                "overlap": best["overlap"],
                "cardinality": best["cardinality"],
                "safe": True,
                "recommended": False,
                "source": "automatic",
                "currency_compatible": True,
                "reason": None,
            }
        )
    return consolidated


def _best_relationship_for_pair(
    left_name: str,
    left: pd.DataFrame,
    right_name: str,
    right: pd.DataFrame,
) -> tuple[dict[str, Any] | None, bool]:
    """Devuelve (mejor_relación_segura | mejor_candidata, hubo_candidatas).

    Prioriza clave simple segura; si ninguna simple es segura, prueba una clave
    compuesta de hasta dos columnas. Cuando nada es seguro devuelve la candidata
    con mejor solapamiento para poder informar el motivo.
    """

    pairs = _candidate_pairs(left, right)
    if not pairs:
        return None, False

    single_candidates: list[dict[str, Any]] = []
    for left_key, right_key in pairs:
        stats = relation_stats(left, [left_key], right, [right_key])
        single_candidates.append(
            {
                "left_keys": [left_key],
                "right_keys": [right_key],
                **stats.to_dict(),
            }
        )
    safe_single = [item for item in single_candidates if item["safe"]]
    if safe_single:
        best = max(safe_single, key=lambda item: (item["overlap"], item["coverage_left"]))
        return best, True

    for combo in itertools.combinations(pairs[:6], 2):
        left_keys = [pair[0] for pair in combo]
        right_keys = [pair[1] for pair in combo]
        if len(left_keys) > MAX_RELATION_KEYS:
            continue
        stats = relation_stats(left, left_keys, right, right_keys)
        if stats.safe:
            return (
                {
                    "left_keys": left_keys,
                    "right_keys": right_keys,
                    **stats.to_dict(),
                },
                True,
            )

    best_unsafe = max(
        single_candidates, key=lambda item: (item["overlap"], item["coverage_left"])
    )
    return best_unsafe, True


def _currency_compatible(
    purpose: str,
    left_name: str,
    right_name: str,
    results: dict[str, dict],
) -> tuple[bool, str | None]:
    """Bloquea sumas monetarias entre monedas incompatibles (igual que hoy)."""

    if purpose not in {"ventas_costos", "compras_costos"}:
        return True, None
    left_currency = results.get(left_name, {}).get("_moneda")
    right_currency = results.get(right_name, {}).get("_moneda")
    if not isinstance(left_currency, CurrencyDetection) or not isinstance(
        right_currency, CurrencyDetection
    ):
        return True, None
    if left_currency.mixta or right_currency.mixta:
        return False, (
            "Una de las hojas contiene monedas mezcladas; no se pueden calcular "
            "costos ni utilidad con esta relación."
        )
    if left_currency.dominante != right_currency.dominante:
        return False, (
            f"Los montos de {left_name} están en {left_currency.dominante} y "
            f"los de {right_name} en {right_currency.dominante}; no se relacionan "
            "sin una conversión explícita."
        )
    return True, None


def detect_relationship_catalog(
    frames: dict[str, pd.DataFrame],
    mappings: dict[str, dict[str, str]] | None = None,
    results: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Catálogo determinista de TODAS las relaciones seguras del libro.

    Contrato (Parte 4): ``{"relationships": [...], "discarded_count": int,
    "message": str | None}``. Cada relación trae un ID determinista, la plantilla
    de dashboard y la metadata de seguridad. Solo aprueba automáticamente
    ``uno_a_uno`` y ``muchos_a_uno``; el resto se descarta y se cuenta.
    """

    mappings = mappings or {}
    results = results or {}
    resolved = {
        name: resolve_mapping([str(column) for column in frame.columns], mappings.get(name))
        for name, frame in frames.items()
    }
    kinds = {name: _sheet_kind(name, frames[name]) for name in frames}
    sales_names = [name for name, kind in kinds.items() if kind == "ventas"]

    supported_orientations = {
        ("ventas", "productos"),
        ("ventas", "costos"),
        ("ventas", "historial_costos"),
        ("ventas", "clientes"),
        ("ventas", "vendedores"),
        ("ventas", "sucursales"),
        ("ventas", "inventario"),
        ("ventas", "cobranzas"),
        ("productos", "proveedores"),
        ("compras", "productos"),
        ("compras", "proveedores"),
        ("inventario", "productos"),
        ("gastos", "sucursales"),
        ("clientes", "vendedores"),
        ("vendedores", "sucursales"),
        ("metas", "sucursales"),
        ("campanas", "sucursales"),
    }

    def orient_pair(first: str, second: str) -> tuple[str, str] | None:
        if (kinds[first], kinds[second]) in supported_orientations:
            return first, second
        if (kinds[second], kinds[first]) in supported_orientations:
            return second, first
        return None

    relationships: list[dict[str, Any]] = []
    discarded = 0
    for first, second in itertools.combinations(frames, 2):
        oriented = orient_pair(first, second)
        if oriented is None:
            if _unsupported_generic_pair(first, frames[first], second, frames[second]):
                discarded += 1
            continue
        left_name, right_name = oriented
        # When periods are split across several sales sheets, only the
        # consolidated relationship is presented. This avoids duplicated
        # dashboards that disagree simply because each one sees half a year.
        if kinds[left_name] == "ventas" and len(sales_names) > 1:
            continue
        left = frames[left_name]
        right = frames[right_name]
        temporal_history = kinds[right_name] == "historial_costos"
        # El catálogo no inventa unicidad colapsando snapshots o sucursales.
        # Si la referencia repite la clave elegida, la conexión no es ejecutable
        # como muchos-a-uno y no debe aparecer como disponible.
        right_eval = right
        if temporal_history:
            left_key = (
                find_column(left.columns, "sku", "producto")
                or find_column(left.columns, "id", "producto")
            )
            right_key = (
                find_column(right.columns, "sku", "producto")
                or find_column(right.columns, "id", "producto")
            )
            if not left_key or not right_key:
                continue
            left_values = {
                _text_key(value) for value in left[left_key] if _text_key(value)
            }
            right_values = {
                _text_key(value) for value in right[right_key] if _text_key(value)
            }
            coverage = len(left_values & right_values) / max(len(left_values), 1)
            best = {
                "left_keys": [left_key],
                "right_keys": [right_key],
                "coverage_left": round(coverage, 4),
                "coverage_right": 1.0,
                "overlap": round(coverage, 4),
                "cardinality": "muchos_a_uno_temporal",
                "safe": True,
                "reason": None,
            }
            had_candidates = True
        else:
            best, had_candidates = _best_relationship_for_pair(
                left_name, left, right_name, right_eval
            )
        if best is None:
            continue
        template, label, purpose = classify_relationship_template(
            left_name, left, resolved[left_name], right_name, right, resolved[right_name]
        )
        if template == "generic" and _unsupported_generic_pair(
            left_name, left, right_name, right
        ):
            discarded += 1
            continue
        currency_ok, currency_reason = _currency_compatible(
            purpose, left_name, right_name, results
        )
        safe = bool(best["safe"] and currency_ok)
        reason = best.get("reason")
        if not currency_ok:
            reason = currency_reason
        entry = {
            "id": relationship_id(
                left_name, right_name, best["left_keys"], best["right_keys"]
            ),
            "left_sheet": left_name,
            "right_sheet": right_name,
            "left_keys": best["left_keys"],
            "right_keys": best["right_keys"],
            "type": "left",
            "template": template,
            "label": label,
            "purpose": purpose,
            "coverage_left": best["coverage_left"],
            "coverage_right": best["coverage_right"],
            "overlap": best["overlap"],
            "cardinality": best["cardinality"],
            "safe": safe,
            "recommended": False,
            "source": "automatic",
            "currency_compatible": currency_ok,
            "reason": reason,
            **({"join_strategy": "vigencia_por_fecha"} if temporal_history else {}),
        }
        if safe:
            # Una conexión puede tener cardinalidad segura y aun así violar
            # una invariancia financiera (filas, ventas, cantidades o costos).
            # La probamos antes de publicarla: el selector manual solo muestra
            # conexiones que realmente pueden ejecutarse con este archivo.
            try:
                join_related_frames(
                    {left_name: left, right_name: right_eval},
                    {
                        left_name: resolved[left_name],
                        right_name: resolved[right_name],
                    },
                    entry,
                )
            except (KeyError, TypeError, ValueError):
                discarded += 1
                continue
            relationships.append(entry)
        elif had_candidates:
            discarded += 1

    relationships.extend(
        _consolidated_sales_relationships(frames, resolved, results)
    )

    # Orden de utilidad: costos primero, luego el resto por solapamiento.
    template_order = {
        "sales_costs": 0,
        "products_sales": 1,
        "sales_inventory": 2,
        "sales_customers": 3,
        "sales_sellers": 4,
        "sales_branches": 5,
        "purchases_costs": 6,
        "expenses_branches": 7,
        "generic": 8,
    }
    relationships.sort(
        key=lambda item: (
            0 if item.get("append_sheets") else 1,
            template_order.get(item["template"], 9),
            -item["overlap"],
            -item["coverage_left"],
            item["label"],
        )
    )
    if relationships:
        relationships[0]["recommended"] = True

    message = None
    if not relationships:
        message = (
            "No encontramos relaciones seguras entre estas hojas. Puedes crear "
            "una conexión personalizada o analizar las hojas por separado."
        )
    return {
        "relationships": relationships,
        "discarded_count": discarded,
        "message": message,
    }
