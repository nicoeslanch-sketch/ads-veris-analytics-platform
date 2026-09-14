"""Adversarial data-integrity checks independent from the UI and upload routes."""

import pandas as pd
import pytest

from app.engine.business import _applicable_unit_cost, _formula_controls, analyze_business_workbook
from app.engine.metrics import CurrencyDetection
from app.engine.multi_sheet import join_related_frames, relation_stats
from app.engine.relationship_dashboard import build_relationship_dashboard
from app.engine.relationships import detect_relationship_catalog
from app.engine.standardize import normalize_headers, standardize_dataframe


@pytest.mark.parametrize("headers", [
    ["Monto", "Monto", "Monto_2"],
    ["A", "A", "A_2", "A_3", "A_2_2"],
    ["  Monto  ", "Monto", "Monto_2"],
    ["", "columna_1", "columna_1_2"],
    ["A_2", "A", "A", "A_2"],
    ["CATEGORIA", "categoria", "categoria_2"],
])
def test_normalized_headers_are_unique_lossless_and_idempotent(headers):
    original_values = [str(position) for position in range(len(headers))]
    frame = pd.DataFrame([original_values], columns=headers)
    normalize_headers(frame)
    assert len({column.casefold() for column in frame}) == len(headers)
    assert frame.iloc[0].tolist() == original_values
    assert normalize_headers(frame) == 0


def _sales(dates=("2025-03-01",), product="P1"):
    return pd.DataFrame({
        "ID_Venta": [f"V{i}" for i in range(len(dates))],
        "Fecha": list(dates), "ID_Producto": [product] * len(dates),
        "Nombre_Producto": ["Producto Uno"] * len(dates),
        "Cantidad": [2] * len(dates), "Monto_Venta": [100] * len(dates),
    })


def _history(costs=(10, 20, 30), starts=("2025-01-01", "2025-02-01", "2025-02-01")):
    return pd.DataFrame({
        "ID_Producto": ["P1"] * len(costs),
        "Fecha_Desde": list(starts), "Costo_Unitario": list(costs),
    })


def _costs(sales, history, current=None):
    return _applicable_unit_cost(
        sales, "ID_Producto", pd.to_datetime(sales["Fecha"]),
        current, "ID_Producto" if current is not None else None,
        "Costo_Unitario" if current is not None else None, history,
    )


def _relation(append=False):
    return {
        "id": "history", "left_sheet": "Ventas", "right_sheet": "Historial_Costos",
        "left_keys": ["ID_Producto"], "right_keys": ["ID_Producto"], "type": "left",
        "join_strategy": "vigencia_por_fecha",
        **({"append_sheets": ["Ventas", "Ventas_2026"]} if append else {}),
    }


def _currency(code):
    return {"_moneda": CurrencyDetection(
        dominante=code, detectadas=(code,), conteos={code: 1}, mixta=False,
    )}


def test_conflicting_historical_version_does_not_resurrect_older_cost():
    sales = _sales(("2025-01-15", "2025-03-01"))
    costs, sources, quality = _costs(sales, _history())
    assert costs.iloc[0] == 10
    assert pd.isna(costs.iloc[1])
    assert pd.isna(sources.iloc[1])
    assert quality["claves_historicas_conflictivas"] == 1


@pytest.mark.parametrize("invalid_cost", [None, "sin dato", 0, -5])
def test_invalid_historical_version_is_an_explicit_gap(invalid_cost):
    history = _history((10, invalid_cost), ("2025-01-01", "2025-02-01"))
    costs, sources, _ = _costs(_sales(), history)
    assert costs.isna().all()
    assert sources.isna().all()


def test_historical_gap_may_use_current_cost_only_as_an_estimate():
    current = pd.DataFrame({"ID_Producto": ["P1"], "Costo_Unitario": [45]})
    costs, sources, _ = _costs(_sales(), _history(), current)
    assert costs.iloc[0] == 45
    assert sources.iloc[0] == "catalogo_actual_estimado"


def test_duplicate_identical_history_remains_usable_without_multiplication():
    costs, sources, quality = _costs(_sales(), _history((10, 20, 20)))
    assert costs.tolist() == [20]
    assert sources.tolist() == ["historial_asof"]
    assert quality["claves_historicas_conflictivas"] == 0


def test_explicit_validity_end_is_inclusive_and_not_carried_forward():
    history = _history((10,), ("2025-01-01",))
    history["Fecha_Hasta"] = ["2025-02-28"]
    costs, _, _ = _costs(_sales(("2025-02-28", "2025-03-01")), history)
    assert costs.iloc[0] == 10
    assert pd.isna(costs.iloc[1])


@pytest.mark.parametrize("end", ["fecha incorrecta", "2024-12-31"])
def test_invalid_validity_end_does_not_turn_into_open_ended_cost(end):
    history = _history((10,), ("2025-01-01",))
    history["Fecha_Hasta"] = [end]
    assert _costs(_sales(), history)[0].isna().all()


@pytest.mark.parametrize("end", [None, ""])
def test_physically_empty_validity_end_means_open_ended(end):
    history = _history((10,), ("2025-01-01",))
    history["Fecha_Hasta"] = [end]
    assert _costs(_sales(), history)[0].tolist() == [10]


@pytest.mark.parametrize("append", [False, True])
def test_temporal_cost_dashboard_blocks_uf_clp_arithmetic(append):
    frames = {"Ventas": _sales(), "Historial_Costos": _history((10,), ("2025-01-01",))}
    results = {"Ventas": _currency("CLP"), "Historial_Costos": _currency("UF")}
    if append:
        frames["Ventas_2026"] = _sales(("2026-01-01",))
        results["Ventas_2026"] = _currency("CLP")
    dashboard = build_relationship_dashboard(frames, {}, results, _relation(append))
    assert dashboard["available"] is False
    assert "monedas incompatibles" in dashboard["message"]
    assert not any(r["right_sheet"] == "Historial_Costos"
                   for r in detect_relationship_catalog(frames, {}, results)["relationships"])


@pytest.mark.parametrize("append", [False, True])
def test_history_catalog_requires_actual_temporal_coverage(append):
    frames = {"Ventas": _sales(), "Historial_Costos": _history((10,), ("2027-01-01",))}
    if append:
        frames["Ventas_2026"] = _sales(("2026-01-01",))
    assert not any(r["right_sheet"] == "Historial_Costos"
                   for r in detect_relationship_catalog(frames)["relationships"])


def test_valid_history_is_available_for_a_single_sales_sheet():
    frames = {"Ventas": _sales(), "Historial_Costos": _history((10, 20, 20))}
    catalog = detect_relationship_catalog(frames)
    relation = next(r for r in catalog["relationships"] if r["right_sheet"] == "Historial_Costos")
    assert relation["cardinality"] == "muchos_a_uno_temporal"
    assert relation["coverage_left"] == 1
    dashboard = build_relationship_dashboard(
        frames, {"Ventas": {"producto": "Nombre_Producto"}}, {}, relation,
    )
    assert dashboard["available"] is True
    assert dashboard["quality"]["rows_before"] == dashboard["quality"]["rows_after"] == 1
    kpis = {item["id"]: item["value"] for item in dashboard["kpis"]}
    assert kpis["costo"] == 40


def test_composite_join_preserves_rows_totals_and_orphans():
    sales = pd.DataFrame({
        "ID_Producto": ["P1", "P1", "P2", "P3"],
        "ID_Sucursal": ["S1", "S2", "S1", "S1"],
        "Monto": [10, 20, -5, 7],
    })
    reference = pd.DataFrame({
        "ID_Producto": ["P1", "P1", "P2"],
        "ID_Sucursal": ["S1", "S2", "S1"], "Etiqueta": ["A", "B", "C"],
    })
    keys = ["ID_Producto", "ID_Sucursal"]
    assert not relation_stats(sales, keys[:1], reference, keys[:1]).safe
    stats = relation_stats(sales, keys, reference, keys)
    assert stats.safe and stats.unmatched_rows == 1
    joined, _, _ = join_related_frames(
        {"Ventas": sales, "Referencia": reference}, {},
        {"left_sheet": "Ventas", "right_sheet": "Referencia", "left_keys": keys,
         "right_keys": keys, "type": "left"},
    )
    assert len(joined) == len(sales)
    assert joined["Monto"].sum() == sales["Monto"].sum()


def test_identifiers_and_invalid_dates_survive_standardization():
    source = pd.DataFrame({
        "ID_Cliente": ["001", "1", "A-007"],
        "Fecha": ["31/01/2026", "31/02/2026", "01/03/2026"],
        "Monto UF": ["UF 1,50", "UF 2,75", "sin dato"],
    })
    source.attrs["adsveris_source_rows"] = [7, 8, 9]
    cleaned, report = standardize_dataframe(source)
    assert cleaned["ID_Cliente"].tolist() == source["ID_Cliente"].tolist()
    assert cleaned.loc[1, "Fecha"] == "31/02/2026"
    assert cleaned.loc[2, "Monto UF"] == "sin dato"
    assert cleaned.attrs["adsveris_source_rows"] == [7, 8, 9]
    assert len(cleaned) == len(source)


def test_many_to_many_is_blocked_before_any_amount_is_multiplied():
    left = pd.DataFrame({"ID_Producto": ["P1", "P1"], "Monto": [100, 200]})
    right = pd.DataFrame({"ID_Producto": ["P1", "P1", "P1"], "Etiqueta": ["A", "B", "C"]})
    stats = relation_stats(left, ["ID_Producto"], right, ["ID_Producto"])
    assert not stats.safe
    assert stats.cardinality == "muchos_a_muchos"
    assert stats.projected_rows == 6
    with pytest.raises(ValueError, match="duplicadas"):
        join_related_frames({"Ventas": left, "Referencia": right}, {}, {
            "left_sheet": "Ventas", "right_sheet": "Referencia",
            "left_keys": ["ID_Producto"], "right_keys": ["ID_Producto"], "type": "left",
        })


def test_normalizing_identifier_padding_cannot_hide_a_reference_collision():
    left = pd.DataFrame({"ID_Producto": ["P1", "P2", "P3"]})
    right = pd.DataFrame({"ID_Producto": ["P1", "P01", "P2", "P3"]})
    stats = relation_stats(left, ["ID_Producto"], right, ["ID_Producto"])
    assert stats.right_duplicate_keys == 1
    assert not stats.safe


def test_business_connections_use_product_id_not_its_display_name():
    frames = {
        "Ventas": _sales(), "Historial_Costos": _history((10, 20, 20)),
        "Productos": pd.DataFrame({"ID_Producto": ["P1"], "Nombre_Producto": ["Maestro Uno"], "Categoria": ["Cat A"]}),
    }
    result = analyze_business_workbook(frames, {"Ventas": {
        "producto": "Nombre_Producto", "fecha": "Fecha", "monto": "Monto_Venta", "cantidad": "Cantidad",
    }}, {})
    assert result["estado_resultados"]["costo_venta_conocido"] == 40
    assert result["estado_resultados"]["utilidad_bruta"] == 60
    assert result["calidad"]["costos"]["filas_costo_historico"] == 1
    assert result["agrupaciones"]["categorias"][0]["nombre"] == "Cat A"


def test_purchase_net_control_includes_explicit_freight():
    purchases = pd.DataFrame({
        "Cantidad Comprada": [8], "Costo Unitario Compra": [70550],
        "Descuento Compra %": [0.08], "Flete Total": [3274],
        "Monto Neto Compra": [522522], "IVA": [99279], "Total Compra": [621801],
    })
    controls = _formula_controls({"Compras": purchases}, {"compras": ["Compras"]})
    net_control = next(control for control in controls if control["control"] == "neto_compra")
    assert net_control["filas_evaluadas"] == 1
    assert net_control["filas_inconsistentes"] == 0
