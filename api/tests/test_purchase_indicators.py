"""Missing purchase amounts must not become certified zero balances."""

import pandas as pd
import pytest

from app.engine.business import analyze_business_workbook
from app.engine.mapping import resolve_mapping


def _analyze(purchases, **options):
    frames = {
        "Ventas": pd.DataFrame({
            "IDVenta": ["V1"], "Fecha Venta": ["2026-02-10"],
            "IDProducto": ["P1"], "Cantidad": [1], "Monto Venta": [100],
        }),
        "Compras": purchases,
    }
    mappings = {name: resolve_mapping(list(frame.columns), None)
                for name, frame in frames.items()}
    analysis = analyze_business_workbook(frames, mappings, {}, **options)
    indicators = {item["id"]: item
                  for category in analysis["catalogo_indicadores"]["categorias"]
                  for item in category["indicadores"]}
    return analysis, indicators


@pytest.mark.parametrize("amounts", [None, [None, None], ["sin dato", "error"]])
def test_missing_purchase_amounts_are_unavailable_not_zero(amounts):
    purchases = pd.DataFrame({
        "IDCompra": ["C1", "C2"], "Fecha Compra": ["2026-02-10"] * 2,
        "Estado": ["Recibida"] * 2,
    })
    if amounts is not None:
        purchases["Monto Neto"] = amounts
    original = purchases.copy(deep=True)
    analysis, indicators = _analyze(purchases)
    assert analysis["operacion"]["compras_efectivas"] is None
    assert indicators["compras_netas"]["valor"] is None
    assert indicators["compras_netas"]["estado"] == "unavailable"
    assert indicators["compras_netas"]["advertencias"]
    pd.testing.assert_frame_equal(purchases, original)


def test_partial_purchase_amounts_publish_coverage_and_warning():
    purchases = pd.DataFrame({
        "IDCompra": ["C1", "C2", "C3"],
        "Fecha Compra": ["2026-02-10"] * 3,
        "Estado": ["Recibida", "Recibida", "Anulada"],
        "Monto Neto": [120, None, 900],
    })
    analysis, indicators = _analyze(purchases)
    indicator = indicators["compras_netas"]
    assert analysis["operacion"]["compras_efectivas"] == 120
    assert indicator["valor"] == 120
    assert indicator["estado"] == "partial"
    assert indicator["cobertura_datos_pct"] == 50
    assert any("parcial" in warning.lower() for warning in indicator["advertencias"])


@pytest.mark.parametrize("amount", [0, 120])
def test_observed_zero_and_complete_purchase_amounts_remain_available(amount):
    purchases = pd.DataFrame({
        "IDCompra": ["C1"], "Fecha Compra": ["2026-02-10"],
        "Estado": ["Recibida"], "Monto Neto": [amount],
    })
    analysis, indicators = _analyze(purchases)
    assert analysis["operacion"]["compras_efectivas"] == amount
    assert indicators["compras_netas"]["estado"] == "available"
    assert indicators["compras_netas"]["cobertura_datos_pct"] == 100


def test_no_eligible_purchase_amount_in_period_is_not_invented_zero():
    purchases = pd.DataFrame({
        "IDCompra": ["C1", "C2"],
        "Fecha Compra": ["2026-01-10", "2026-02-10"],
        "Estado": ["Recibida", "Anulada"], "Monto Neto": [120, 900],
    })
    analysis, indicators = _analyze(purchases, date_from="2026-02-01", date_to="2026-02-28")
    assert analysis["operacion"]["compras_efectivas"] is None
    assert indicators["compras_netas"]["estado"] == "unavailable"


def test_purchase_dimensional_filter_does_not_substitute_global_amount():
    purchases = pd.DataFrame({
        "IDCompra": ["C1"], "Fecha Compra": ["2026-02-10"],
        "Estado": ["Recibida"], "Monto Neto": [120],
    })
    analysis, indicators = _analyze(purchases, filters={"producto": "P1"})
    assert analysis["operacion"]["compras_efectivas"] is None
    assert indicators["compras_netas"]["estado"] == "unavailable"


@pytest.mark.parametrize("freights", [[None, None], ["error", "sin dato"]])
def test_missing_freight_is_unavailable_not_zero(freights):
    purchases = pd.DataFrame({
        "IDCompra": ["C1", "C2"], "Fecha Compra": ["2026-02-10"] * 2,
        "Monto Neto": [120, 80], "Flete": freights,
    })
    _, indicators = _analyze(purchases)
    assert indicators["fletes_compra"]["valor"] is None
    assert indicators["fletes_compra"]["estado"] == "unavailable"
    assert indicators["fletes_compra"]["advertencias"]


def test_partial_freight_publishes_coverage_without_repeating_document_value():
    purchases = pd.DataFrame({
        "IDCompra": ["C1", "C1", "C2"], "Fecha Compra": ["2026-02-10"] * 3,
        "Monto Neto": [120, 80, 50], "Flete": [10, 10, None],
    })
    _, indicators = _analyze(purchases)
    indicator = indicators["fletes_compra"]
    assert indicator["valor"] == 10
    assert indicator["estado"] == "partial"
    assert indicator["cobertura_datos_pct"] == 50
    assert indicator["advertencias"]


def test_conflicting_freight_repetitions_do_not_keep_an_arbitrary_first_value():
    purchases = pd.DataFrame({
        "IDCompra": ["C1", " c1 "], "Fecha Compra": ["2026-02-10"] * 2,
        "Monto Neto": [120, 80], "Flete": [10, 20],
    })
    _, indicators = _analyze(purchases)
    assert indicators["fletes_compra"]["valor"] is None
    assert indicators["fletes_compra"]["estado"] == "unavailable"
    assert any("distintos" in warning for warning in indicators["fletes_compra"]["advertencias"])


def test_freight_without_document_identity_cannot_claim_document_level_total():
    purchases = pd.DataFrame({
        "Fecha Compra": ["2026-02-10"] * 2,
        "Monto Neto": [120, 80], "Flete": [10, 10],
    })
    _, indicators = _analyze(purchases)
    assert indicators["fletes_compra"]["valor"] is None
    assert indicators["fletes_compra"]["estado"] == "unavailable"


def test_freight_document_ids_preserve_leading_zeroes_and_observed_zero():
    purchases = pd.DataFrame({
        "IDCompra": ["C01", "C1", "C0"],
        "Fecha Compra": ["2026-02-10"] * 3,
        "Monto Neto": [120, 80, 10], "Flete": [10, 20, 0],
    })
    _, indicators = _analyze(purchases)
    assert indicators["fletes_compra"]["valor"] == 30
    assert indicators["fletes_compra"]["estado"] == "available"
    assert indicators["fletes_compra"]["cobertura_datos_pct"] == 100


def test_document_with_missing_and_present_repetition_uses_known_freight_once():
    purchases = pd.DataFrame({
        "IDCompra": ["C1", "C1"], "Fecha Compra": ["2026-02-10"] * 2,
        "Monto Neto": [120, 80], "Flete": [None, 10],
    })
    _, indicators = _analyze(purchases)
    assert indicators["fletes_compra"]["valor"] == 10
    assert indicators["fletes_compra"]["cobertura_datos_pct"] == 100


def test_small_missing_share_still_marks_purchase_total_partial():
    purchases = pd.DataFrame({
        "IDCompra": [f"C{index}" for index in range(501)],
        "Fecha Compra": ["2026-02-10"] * 501,
        "Monto Neto": [1] * 500 + [None],
    })
    _, indicators = _analyze(purchases)
    assert indicators["compras_netas"]["valor"] == 500
    assert indicators["compras_netas"]["estado"] == "partial"
