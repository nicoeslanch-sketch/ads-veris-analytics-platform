"""Fase 20 — Catálogo ampliado de relaciones y dashboard por relación.

Cubre la detección segura de múltiples relaciones, el bloqueo de uniones que
multiplican filas o alteran totales, y el cálculo determinista de los dashboards
por plantilla (Productos↔Ventas, Ventas↔Costos, Ventas↔Inventario, genérico).
"""

import io

import pandas as pd
import pytest

from app.engine.multi_sheet import join_related_frames, relation_stats
from app.engine.relationship_dashboard import build_relationship_dashboard
from app.engine.relationships import (
    detect_relationship_catalog,
    relationship_id,
)
from app.routes.pipeline import (
    _relationship_catalog_sync,
    _relationship_dashboard_sync,
    _validate_manual_relationship,
)


def _ventas() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ID_Venta": ["V1", "V2", "V3", "V4", "V5", "V6"],
            "Fecha": [
                "2025-01-05", "2025-01-20", "2025-02-08",
                "2025-02-15", "2025-03-03", "2025-03-25",
            ],
            "ID_Producto": ["0001", "0002", "0001", "0003", "0002", "0001"],
            "Cantidad": [2, 1, 3, 1, 5, 2],
            "Monto_Venta": [2000, 1500, 3000, 900, 7500, 2000],
        }
    )


def _productos() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ID_Producto": ["0001", "0002", "0003"],
            "Nombre_Producto": ["Alfa", "Beta", "Gamma"],
            "Categoria": ["Bebidas", "Snacks", "Bebidas"],
            "Costo_Unitario": [500, 600, 300],
        }
    )


def _clientes() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ID_Cliente": ["C1", "C2", "C3"],
            "Nombre_Cliente": ["Uno", "Dos", "Tres"],
        }
    )


def _relation(left, right, left_keys, right_keys):
    return {
        "left_sheet": left,
        "right_sheet": right,
        "left_keys": left_keys,
        "right_keys": right_keys,
        "type": "left",
    }


# ── Catálogo ─────────────────────────────────────────────────────────────────
def test_catalog_detects_safe_relationship_with_deterministic_id():
    frames = {"Ventas": _ventas(), "Productos": _productos()}
    catalog = detect_relationship_catalog(frames, {}, {})
    assert catalog["relationships"], "debe encontrar al menos una relación segura"
    relation = catalog["relationships"][0]
    assert relation["left_sheet"] == "Ventas"
    assert relation["right_sheet"] == "Productos"
    assert relation["safe"] is True
    assert relation["recommended"] is True
    assert relation["cardinality"] == "muchos_a_uno"
    assert relation["template"] == "sales_costs"
    assert relation["id"] == relationship_id(
        "Ventas", "Productos", ["ID_Producto"], ["ID_Producto"]
    )


def test_catalog_id_is_stable_across_calls():
    frames = {"Ventas": _ventas(), "Productos": _productos()}
    first = detect_relationship_catalog(frames, {}, {})["relationships"][0]["id"]
    second = detect_relationship_catalog(frames, {}, {})["relationships"][0]["id"]
    assert first == second


def test_catalog_finds_multiple_safe_relationships():
    ventas = _ventas()
    ventas["ID_Cliente"] = ["C1", "C2", "C1", "C3", "C2", "C1"]
    frames = {"Ventas": ventas, "Productos": _productos(), "Clientes": _clientes()}
    catalog = detect_relationship_catalog(frames, {}, {})
    templates = {rel["template"] for rel in catalog["relationships"]}
    assert "sales_costs" in templates
    assert "sales_customers" in templates
    assert len(catalog["relationships"]) >= 2


def test_catalog_preserves_leading_zeros_in_keys():
    frames = {"Ventas": _ventas(), "Productos": _productos()}
    catalog = detect_relationship_catalog(frames, {}, {})
    relation = catalog["relationships"][0]
    assert relation["overlap"] == pytest.approx(1.0)
    assert relation["coverage_left"] == pytest.approx(1.0)


def test_catalog_supports_composite_keys():
    ventas = pd.DataFrame(
        {
            "Fecha": ["2025-01-01", "2025-01-02", "2025-01-03"],
            "ID_Producto": ["P1", "P1", "P2"],
            "ID_Sucursal": ["S1", "S2", "S1"],
            "Cantidad": [1, 1, 1],
            "Monto_Venta": [100, 200, 300],
        }
    )
    precios = pd.DataFrame(
        {
            "ID_Producto": ["P1", "P1", "P2"],
            "ID_Sucursal": ["S1", "S2", "S1"],
            "Costo_Unitario": [40, 45, 90],
        }
    )
    stats = relation_stats(
        ventas, ["ID_Producto", "ID_Sucursal"], precios, ["ID_Producto", "ID_Sucursal"]
    )
    assert stats.safe is True
    assert stats.cardinality in {"muchos_a_uno", "uno_a_uno"}


def test_catalog_reports_no_relationships_for_unrelated_sheets():
    ventas = _ventas().drop(columns=["ID_Producto"])
    otras = pd.DataFrame({"Concepto": ["A", "B"], "Detalle": ["x", "y"]})
    catalog = detect_relationship_catalog({"Ventas": ventas, "Notas": otras}, {}, {})
    assert catalog["relationships"] == []
    assert catalog["message"] is not None


def test_catalog_does_not_relate_two_transactional_sheets():
    enero = _ventas()
    febrero = _ventas()
    catalog = detect_relationship_catalog({"Enero": enero, "Febrero": febrero}, {}, {})
    assert catalog["relationships"] == []


def test_catalog_hides_inventory_costs_without_supported_template():
    inventory = pd.DataFrame(
        {
            "Fecha Corte": ["2026-01-31", "2026-01-31"],
            "SKU_Producto": ["P1", "P2"],
            "Stock Disponible": [10, 20],
            "Valor Inventario": [4000, 12000],
        }
    )
    costs = pd.DataFrame(
        {
            "SKU_Producto": ["P1", "P2"],
            "Costo Unitario": [400, 600],
        }
    )
    catalog = detect_relationship_catalog(
        {"Inventario": inventory, "Costos_Productos": costs},
        {},
        {},
    )
    assert catalog["relationships"] == []
    assert catalog["discarded_count"] == 1


def test_catalog_does_not_offer_sales_inventory_when_sku_is_not_unique():
    inventory = pd.DataFrame(
        {
            "Fecha_Corte": ["2026-01-31", "2026-01-31", "2026-02-28"],
            "SKU_Producto": ["0001", "0001", "0002"],
            "ID_Sucursal": ["S1", "S2", "S1"],
            "Stock_Disponible": [10, 8, 20],
            "Costo_Unitario": [500, 500, 600],
        }
    )
    catalog = detect_relationship_catalog(
        {"Ventas": _ventas(), "Inventario": inventory},
        {},
        {},
    )

    assert catalog["relationships"] == []


def test_consolidated_catalog_does_not_offer_duplicated_inventory_reference():
    second = _ventas().assign(
        ID_Venta=lambda frame: frame["ID_Venta"] + "-B",
        Fecha="2026-01-05",
    )
    inventory = pd.DataFrame(
        {
            "SKU_Producto": ["0001", "0001", "0002", "0003"],
            "ID_Sucursal": ["S1", "S2", "S1", "S1"],
            "Stock_Disponible": [10, 8, 20, 4],
            "Costo_Unitario": [500, 500, 600, 300],
        }
    )
    catalog = detect_relationship_catalog(
        {
            "Ventas_2025": _ventas(),
            "Ventas_2026": second,
            "Inventario": inventory,
        },
        {},
        {},
    )

    assert all(item["right_sheet"] != "Inventario" for item in catalog["relationships"])


def test_catalog_adds_all_sales_periods_to_costs_without_replacing_individual_views():
    first = _ventas()
    second = _ventas().assign(
        ID_Venta=lambda frame: frame["ID_Venta"] + "-B",
        Fecha="2026-01-05",
    )
    catalog = detect_relationship_catalog(
        {
            "Ventas_2025": first,
            "Ventas_2026": second,
            "Productos": _productos(),
        },
        {},
        {},
    )
    consolidated = [
        item for item in catalog["relationships"] if item.get("append_sheets")
    ]
    assert len(consolidated) == 1
    assert consolidated[0]["label"] == "Todas las ventas ↔ Productos"
    assert consolidated[0]["append_sheets"] == ["Ventas_2025", "Ventas_2026"]
    assert consolidated[0]["recommended"] is True
    # Cuando hay varios periodos equivalentes se ofrece una sola conexión
    # consolidada; así el workspace no repite dashboards semestrales.
    assert sum(
        item["left_sheet"].startswith("Ventas_")
        and not item.get("append_sheets")
        for item in catalog["relationships"]
    ) == 0


def test_catalog_recognizes_neutral_month_names_as_sales_by_structure():
    january = pd.DataFrame(
        {
            "ID Producto": ["A", "B"],
            "ID Cliente": ["C1", "C2"],
            "Fecha": ["2026-01-01", "2026-01-02"],
            "Cantidad": [2, 1],
            "Venta": [2000, 1500],
        }
    )
    february = january.assign(Fecha="2026-02-01")
    products = pd.DataFrame(
        {
            "ID Producto": ["A", "B"],
            "Producto": ["Alfa", "Beta"],
            "Costo_Unitario": [500, 600],
        }
    )
    catalog = detect_relationship_catalog(
        {"Enero": january, "Febrero": february, "Productos": products},
        {},
        {},
    )
    consolidated = [
        item for item in catalog["relationships"] if item.get("append_sheets")
    ]
    assert len(consolidated) == 1
    assert consolidated[0]["append_sheets"] == ["Enero", "Febrero"]
    assert consolidated[0]["template"] == "sales_costs"


# ── Seguridad de la unión ────────────────────────────────────────────────────
def test_many_to_many_is_blocked():
    left = pd.DataFrame({"K": ["a", "a", "b", "b"], "Monto_Venta": [1, 2, 3, 4], "Fecha": ["2025-01-01"] * 4})
    right = pd.DataFrame({"K": ["a", "a", "b"], "Attr": ["x", "y", "z"]})
    stats = relation_stats(left, ["K"], right, ["K"])
    assert stats.cardinality == "muchos_a_muchos"
    assert stats.safe is False


def test_duplicate_right_key_is_blocked():
    left = pd.DataFrame({"K": ["a", "b", "c"], "Monto_Venta": [1, 2, 3], "Fecha": ["2025-01-01"] * 3})
    right = pd.DataFrame({"K": ["a", "a", "b", "c"], "Attr": ["x", "y", "z", "w"]})
    stats = relation_stats(left, ["K"], right, ["K"])
    assert stats.safe is False
    assert "duplicad" in (stats.reason or "").lower()
    assert stats.left_rows == 3
    assert stats.projected_rows == 4
    assert stats.right_duplicate_keys == 1
    assert stats.unmatched_rows == 0


def test_repeated_missing_placeholders_do_not_make_reference_many_to_many():
    left = pd.DataFrame(
        {
            "K": ["a", "a", "b", "none"],
            "Monto_Venta": [10, 15, 20, 30],
            "Fecha": ["2025-01-01"] * 4,
        }
    )
    right = pd.DataFrame(
        {
            "K": ["a", "b", "c", "None", "null"],
            "Attr": ["A", "B", "C", "sin clave 1", "sin clave 2"],
        }
    )

    stats = relation_stats(left, ["K"], right, ["K"])
    assert stats.safe is True
    assert stats.right_duplicate_keys == 0
    assert stats.cardinality == "muchos_a_uno"

    merged, _mapping, provenance = join_related_frames(
        {"Ventas": left, "Referencia": right},
        {},
        _relation("Ventas", "Referencia", ["K"], ["K"]),
    )
    assert len(merged) == len(left)
    assert merged["Attr"].tolist()[:3] == ["A", "A", "B"]
    assert pd.isna(merged["Attr"].iloc[3])
    assert provenance["filas_sin_correspondencia"] == 0


def test_join_that_multiplies_rows_is_blocked():
    left = pd.DataFrame({"K": ["a", "b"], "Monto_Venta": [10, 20], "Fecha": ["2025-01-01", "2025-01-02"]})
    right = pd.DataFrame({"K": ["a", "a", "b"], "Attr": ["x", "y", "z"]})
    with pytest.raises(ValueError):
        join_related_frames(
            {"Ventas": left, "Ref": right}, {}, _relation("Ventas", "Ref", ["K"], ["K"])
        )


def test_join_preserves_rows_and_totals():
    ventas = _ventas()
    productos = _productos()
    merged, mapping, provenance = join_related_frames(
        {"Ventas": ventas, "Productos": productos},
        {},
        _relation("Ventas", "Productos", ["ID_Producto"], ["ID_Producto"]),
    )
    assert provenance["rows_before"] == provenance["rows_after"] == len(ventas)
    assert merged["Monto_Venta"].sum() == ventas["Monto_Venta"].sum()
    assert merged["Cantidad"].sum() == ventas["Cantidad"].sum()


# ── Dashboards por plantilla ─────────────────────────────────────────────────
def test_products_sales_dashboard_has_expected_kpis():
    productos = _productos().drop(columns=["Costo_Unitario"])
    dashboard = build_relationship_dashboard(
        {"Ventas": _ventas(), "Productos": productos},
        {},
        {},
        _relation("Ventas", "Productos", ["ID_Producto"], ["ID_Producto"]),
    )
    assert dashboard["template"] == "products_sales"
    kpis = {kpi["id"]: kpi for kpi in dashboard["kpis"]}
    assert kpis["ingresos"]["value"] == pytest.approx(16900.0)
    assert kpis["productos"]["value"] == 3


def test_sales_costs_dashboard_margin_only_on_paired_sales():
    ventas = _ventas()
    ventas.loc[len(ventas)] = ["V7", "2025-03-28", "0009", 1, 5000]
    dashboard = build_relationship_dashboard(
        {"Ventas": ventas, "Productos": _productos()},
        {},
        {},
        _relation("Ventas", "Productos", ["ID_Producto"], ["ID_Producto"]),
    )
    assert dashboard["template"] == "sales_costs"
    kpis = {kpi["id"]: kpi for kpi in dashboard["kpis"]}
    assert kpis["ventas"]["value"] == pytest.approx(21900.0)
    assert kpis["cobertura"]["value"] < 100
    # 1000+600+1500+300+3000+1000 = 7400; la venta de 5000 sin costo no suma.
    assert kpis["costo"]["value"] == pytest.approx(7400.0)


def test_consolidated_sales_costs_dashboard_preserves_rows_and_sales_total():
    first = _ventas()
    second = _ventas().assign(
        ID_Venta=lambda frame: frame["ID_Venta"] + "-B",
        Fecha="2026-01-05",
    )
    frames = {
        "Ventas_2025": first,
        "Ventas_2026": second,
        "Productos": _productos(),
    }
    relationship = detect_relationship_catalog(frames, {}, {})["relationships"][0]
    dashboard = build_relationship_dashboard(frames, {}, {}, relationship)
    kpis = {kpi["id"]: kpi for kpi in dashboard["kpis"]}
    assert relationship["append_sheets"] == ["Ventas_2025", "Ventas_2026"]
    assert dashboard["available"] is True
    assert dashboard["quality"]["rows_before"] == len(first) + len(second)
    assert dashboard["quality"]["rows_after"] == len(first) + len(second)
    assert kpis["ventas"]["value"] == pytest.approx(
        first["Monto_Venta"].sum() + second["Monto_Venta"].sum()
    )
    assert {chart["kind"] for chart in dashboard["charts"]} >= {"bar", "combo"}


def test_consolidated_relationship_requires_two_sales_sheets_and_keeps_costs_out():
    base = _relation("Ventas_2025", "Productos", ["ID_Producto"], ["ID_Producto"])
    with pytest.raises(Exception):
        _validate_manual_relationship({**base, "append_sheets": ["Ventas_2025"]})
    with pytest.raises(Exception):
        _validate_manual_relationship(
            {**base, "append_sheets": ["Ventas_2025", "Productos"]}
        )

    parsed = _validate_manual_relationship(
        {**base, "append_sheets": ["Ventas_2025", "Ventas_2026"]}
    )
    assert parsed["append_sheets"] == ["Ventas_2025", "Ventas_2026"]


def test_missing_cost_is_not_zero():
    ventas = pd.DataFrame(
        {
            "ID_Venta": ["V1", "V2"],
            "Fecha": ["2025-01-01", "2025-01-02"],
            "ID_Producto": ["P1", "P9"],
            "Cantidad": [1, 1],
            "Monto_Venta": [1000, 1000],
        }
    )
    productos = pd.DataFrame(
        {
            "ID_Producto": ["P1", "P9"],
            "Nombre_Producto": ["A", "Nueve"],
            "Costo_Unitario": [400, None],
        }
    )
    dashboard = build_relationship_dashboard(
        {"Ventas": ventas, "Productos": productos},
        {},
        {},
        _relation("Ventas", "Productos", ["ID_Producto"], ["ID_Producto"]),
    )
    kpis = {kpi["id"]: kpi for kpi in dashboard["kpis"]}
    assert kpis["costo"]["value"] == pytest.approx(400.0)
    assert kpis["cobertura"]["value"] == pytest.approx(50.0)
    assert any(alert["id"] == "costos_faltantes" for alert in dashboard["alerts"])
    rows = {row["nombre"]: row for row in dashboard["table"]["rows"]}
    assert rows["A"]["margen"] == pytest.approx(60.0)
    assert rows["Nueve"]["utilidad"] is None
    assert rows["Nueve"]["margen"] is None


def test_product_detail_margin_uses_only_income_with_paired_cost():
    ventas = pd.DataFrame(
        {
            "ID_Venta": ["V1", "V2"],
            "Fecha": ["2025-01-01", "2025-01-02"],
            "ID_Producto": ["P1", "P1"],
            # La segunda línea no permite derivar costo, pero conserva ingreso.
            "Cantidad": [1, None],
            "Monto_Venta": [1000, 1000],
        }
    )
    productos = pd.DataFrame(
        {
            "ID_Producto": ["P1"],
            "Nombre_Producto": ["Producto parcial"],
            "Costo_Unitario": [400],
        }
    )

    dashboard = build_relationship_dashboard(
        {"Ventas": ventas, "Productos": productos},
        {},
        {},
        _relation("Ventas", "Productos", ["ID_Producto"], ["ID_Producto"]),
    )

    kpis = {kpi["id"]: kpi for kpi in dashboard["kpis"]}
    row = dashboard["table"]["rows"][0]
    assert kpis["utilidad"]["value"] == pytest.approx(600.0)
    assert row["ingresos"] == pytest.approx(2000.0)
    assert row["ingresos_pareados"] == pytest.approx(1000.0)
    assert row["cobertura"] == pytest.approx(50.0)
    assert row["utilidad"] == pytest.approx(600.0)
    assert row["margen"] == pytest.approx(60.0)
    assert sum(
        item["utilidad"] or 0 for item in dashboard["table"]["rows"]
    ) == pytest.approx(kpis["utilidad"]["value"])


def test_extreme_unit_cost_stays_in_the_total_but_is_flagged_for_review():
    """Regresión QA: un costo unitario atípico (ej. un error de captura o un
    ítem realmente premium) es un dato REAL del maestro -- excluirlo del
    cálculo dejaba esa venta "sin costo" en vez de usar su valor real, y
    escondía el impacto en vez de mostrarlo. Ahora se incluye siempre en el
    total y solo se marca aparte (cobertura 100%, no 95.2%) para que quien
    certifique el resultado sepa qué fila conviene revisar."""
    product_ids = [f"P{i:02d}" for i in range(21)]
    ventas = pd.DataFrame(
        {
            "ID_Venta": [f"V{i:02d}" for i in range(21)],
            "Fecha": ["2025-01-01"] * 21,
            "ID_Producto": product_ids,
            "Cantidad": [1] * 21,
            "Monto_Venta": [1000] * 21,
        }
    )
    productos = pd.DataFrame(
        {
            "ID_Producto": product_ids,
            "Nombre_Producto": product_ids,
            "Costo_Unitario": [400] * 20 + [20_000_000],
        }
    )
    dashboard = build_relationship_dashboard(
        {"Ventas": ventas, "Productos": productos},
        {},
        {},
        _relation("Ventas", "Productos", ["ID_Producto"], ["ID_Producto"]),
    )
    kpis = {kpi["id"]: kpi for kpi in dashboard["kpis"]}
    # 20 × 400 + 1 × 20.000.000: el costo atípico se suma, no se descarta.
    assert kpis["costo"]["value"] == pytest.approx(20_008_000.0)
    assert kpis["cobertura"]["value"] == pytest.approx(100.0)
    assert "estimado" in kpis["costo"]["label"].lower()
    assert any("extremo" in warning for warning in dashboard["quality"]["warnings"])
    # El aviso debe reflejar que el dato se mantiene, no que se excluyó.
    assert any("se mantienen en el cálculo" in warning for warning in dashboard["quality"]["warnings"])


def test_sales_relationship_uses_declared_period_when_no_filter_is_selected():
    ventas = pd.DataFrame(
        {
            "ID_Venta": ["V1", "V2"],
            "Fecha": ["2025-06-01", "2026-01-01"],
            "ID_Producto": ["P1", "P1"],
            "Cantidad": [1, 1],
            "Monto_Venta": [1000, 9000],
        }
    )
    productos = pd.DataFrame(
        {
            "ID_Producto": ["P1"],
            "Nombre_Producto": ["A"],
            "Costo_Unitario": [400],
        }
    )
    parametros = pd.DataFrame(
        {
            "Parametro": ["Periodo ventas"],
            "Valor": ["01-01-2025 a 31-12-2025"],
        }
    )
    dashboard = build_relationship_dashboard(
        {"Ventas": ventas, "Productos": productos, "Parametros": parametros},
        {},
        {},
        _relation("Ventas", "Productos", ["ID_Producto"], ["ID_Producto"]),
    )
    kpis = {kpi["id"]: kpi for kpi in dashboard["kpis"]}
    assert dashboard["period"]["desde"] == "2025-01-01"
    assert dashboard["period"]["hasta"] == "2025-12-31"
    assert kpis["ventas"]["value"] == pytest.approx(1000.0)


def test_all_missing_costs_are_unavailable_instead_of_zero():
    productos = _productos()
    productos["Costo_Unitario"] = None
    dashboard = build_relationship_dashboard(
        {"Ventas": _ventas(), "Productos": productos},
        {},
        {},
        _relation("Ventas", "Productos", ["ID_Producto"], ["ID_Producto"]),
    )
    kpis = {kpi["id"]: kpi for kpi in dashboard["kpis"]}
    assert kpis["costo"]["value"] is None
    assert kpis["costo"]["available"] is False
    assert kpis["utilidad"]["value"] is None
    assert kpis["margen"]["value"] is None


def test_inventory_dashboard_does_not_duplicate_stock():
    ventas = pd.DataFrame(
        {
            "ID_Venta": ["V1", "V2", "V3", "V4"],
            "Fecha": ["2025-03-01", "2025-03-10", "2025-03-20", "2025-03-30"],
            "ID_Producto": ["P1", "P1", "P2", "P1"],
            "Cantidad": [10, 10, 2, 10],
            "Monto_Venta": [1000, 1000, 400, 1000],
        }
    )
    inventario = pd.DataFrame(
        {
            "ID_Producto": ["P1", "P2"],
            "Nombre_Producto": ["Uno", "Dos"],
            "Categoria": ["A", "B"],
            "Stock_Sistema": [30, 500],
            "Fecha_Snapshot": ["2025-03-31", "2025-03-31"],
        }
    )
    dashboard = build_relationship_dashboard(
        {"Ventas": ventas, "Inventario": inventario},
        {},
        {},
        _relation("Ventas", "Inventario", ["ID_Producto"], ["ID_Producto"]),
    )
    assert dashboard["template"] == "sales_inventory"
    kpis = {kpi["id"]: kpi for kpi in dashboard["kpis"]}
    assert kpis["stock"]["value"] == pytest.approx(530.0)


def test_inventory_uses_last_snapshot():
    ventas = pd.DataFrame(
        {
            "ID_Venta": ["V1"],
            "Fecha": ["2025-03-15"],
            "ID_Producto": ["P1"],
            "Cantidad": [5],
            "Monto_Venta": [500],
        }
    )
    inventario = pd.DataFrame(
        {
            "ID_Producto": ["P1", "P1"],
            "Nombre_Producto": ["Uno", "Uno"],
            "Stock_Sistema": [100, 40],
            "Fecha_Snapshot": ["2025-03-01", "2025-03-31"],
        }
    )
    dashboard = build_relationship_dashboard(
        {"Ventas": ventas, "Inventario": inventario},
        {},
        {},
        _relation("Ventas", "Inventario", ["ID_Producto"], ["ID_Producto"]),
    )
    kpis = {kpi["id"]: kpi for kpi in dashboard["kpis"]}
    assert kpis["stock"]["value"] == pytest.approx(40.0)


def test_inventory_coverage_days():
    ventas = pd.DataFrame(
        {
            "ID_Venta": [f"V{i}" for i in range(10)],
            "Fecha": [f"2025-03-{i + 1:02d}" for i in range(10)],
            "ID_Producto": ["P1"] * 10,
            "Cantidad": [2] * 10,
            "Monto_Venta": [100] * 10,
        }
    )
    inventario = pd.DataFrame(
        {
            "ID_Producto": ["P1"],
            "Nombre_Producto": ["Uno"],
            "Stock_Sistema": [20],
            "Fecha_Snapshot": ["2025-03-31"],
        }
    )
    dashboard = build_relationship_dashboard(
        {"Ventas": ventas, "Inventario": inventario},
        {},
        {},
        _relation("Ventas", "Inventario", ["ID_Producto"], ["ID_Producto"]),
    )
    table = dashboard["table"]
    assert table is not None
    row = table["rows"][0]
    assert row["dias_cobertura"] == pytest.approx(10.0, abs=0.5)
    assert row["estado"] in {"alto", "medio"}


def test_period_filter_narrows_dashboard():
    dashboard = build_relationship_dashboard(
        {"Ventas": _ventas(), "Productos": _productos()},
        {},
        {},
        _relation("Ventas", "Productos", ["ID_Producto"], ["ID_Producto"]),
        date_from="2025-03-01",
        date_to="2025-03-31",
    )
    kpis = {kpi["id"]: kpi for kpi in dashboard["kpis"]}
    assert kpis["ventas"]["value"] == pytest.approx(9500.0)


def test_mixed_currency_blocks_cost_dashboard():
    from app.engine.metrics import CurrencyDetection

    ventas = pd.DataFrame(
        {
            "ID_Venta": ["V1", "V2"],
            "Fecha": ["2025-01-01", "2025-01-02"],
            "ID_Producto": ["P1", "P2"],
            "Cantidad": [1, 1],
            "Monto_Venta": [1000, 2000],
        }
    )
    productos = pd.DataFrame(
        {"ID_Producto": ["P1", "P2"], "Nombre_Producto": ["A", "B"], "Costo_Unitario": [400, 800]}
    )
    results = {
        "Ventas": {
            "_moneda": CurrencyDetection(
                dominante="CLP", detectadas=("CLP",), conteos={"CLP": 2}, mixta=False
            )
        },
        "Productos": {
            "_moneda": CurrencyDetection(
                dominante="USD", detectadas=("USD",), conteos={"USD": 2}, mixta=False
            )
        },
    }
    dashboard = build_relationship_dashboard(
        {"Ventas": ventas, "Productos": productos},
        {},
        results,
        _relation("Ventas", "Productos", ["ID_Producto"], ["ID_Producto"]),
    )
    assert dashboard["available"] is False
    assert "moneda" in dashboard["message"].lower()


def test_generic_relationship_dashboard():
    ventas = pd.DataFrame(
        {
            "ID_Venta": ["V1", "V2", "V3"],
            "Fecha": ["2025-01-01", "2025-01-02", "2025-01-03"],
            "ID_Externo": ["E1", "E2", "E1"],
            "Monto_Venta": [100, 200, 300],
        }
    )
    referencia = pd.DataFrame({"ID_Externo": ["E1", "E2"], "Etiqueta": ["Uno", "Dos"]})
    dashboard = build_relationship_dashboard(
        {"Ventas": ventas, "Referencia": referencia},
        {},
        {},
        _relation("Ventas", "Referencia", ["ID_Externo"], ["ID_Externo"]),
    )
    assert dashboard["template"] == "generic"
    kpis = {kpi["id"]: kpi for kpi in dashboard["kpis"]}
    assert kpis["filas"]["value"] == 3
    assert kpis["cobertura"]["available"] is True


def test_empty_right_table_is_safe_message():
    ventas = _ventas()
    productos = pd.DataFrame({"ID_Producto": [], "Nombre_Producto": [], "Costo_Unitario": []})
    dashboard = build_relationship_dashboard(
        {"Ventas": ventas, "Productos": productos},
        {},
        {},
        _relation("Ventas", "Productos", ["ID_Producto"], ["ID_Producto"]),
    )
    assert dashboard["available"] is False


def test_null_ids_do_not_crash_dashboard():
    ventas = _ventas()
    ventas.loc[0, "ID_Producto"] = None
    dashboard = build_relationship_dashboard(
        {"Ventas": ventas, "Productos": _productos()},
        {},
        {},
        _relation("Ventas", "Productos", ["ID_Producto"], ["ID_Producto"]),
    )
    assert dashboard["available"] is True
    assert dashboard["quality"]["rows_before"] == dashboard["quality"]["rows_after"] == 6


# ── Camino del endpoint (sync) con XLSX + manifiesto real ────────────────────
def _multi_sheet_book() -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        _ventas().to_excel(writer, sheet_name="Ventas", index=False)
        _productos().to_excel(writer, sheet_name="Productos", index=False)
    return output.getvalue()


def _book_manifest() -> dict:
    return {
        "hojas": [
            {
                "nombre": "Ventas",
                "procesar": True,
                "rules": {},
                "mapping": {
                    "fecha": "Fecha",
                    "producto": "ID_Producto",
                    "cantidad": "Cantidad",
                    "monto": "Monto_Venta",
                },
                "scope": {},
                "eliminar_duplicados": False,
            },
            {
                "nombre": "Productos",
                "procesar": True,
                "rules": {},
                "mapping": {
                    "producto": "Nombre_Producto",
                    "categoria": "Categoria",
                    "costo": "Costo_Unitario",
                },
                "scope": {},
                "eliminar_duplicados": False,
            },
        ]
    }


def test_catalog_sync_endpoint_path_returns_relationship():
    catalog = _relationship_catalog_sync("libro.xlsx", _multi_sheet_book(), _book_manifest())
    assert catalog["relationships"], "el camino del endpoint debe detectar la relación"
    assert catalog["relationships"][0]["safe"] is True


def test_dashboard_sync_endpoint_path_preserves_totals():
    relation = _relationship_catalog_sync(
        "libro.xlsx", _multi_sheet_book(), _book_manifest()
    )["relationships"][0]
    dashboard = _relationship_dashboard_sync(
        "libro.xlsx", _multi_sheet_book(), _book_manifest(), relation, None, None
    )
    assert dashboard["available"] is True
    assert dashboard["quality"]["rows_before"] == dashboard["quality"]["rows_after"] == 6
