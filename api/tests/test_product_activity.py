import pandas as pd
import pytest

from app.engine.product_activity import product_activity


def activity(rows, months=None, key="id_producto"):
    frame = pd.DataFrame(rows, columns=[key, "producto", "fecha", "monto"])
    return product_activity(frame, "producto", pd.to_datetime(frame.fecha), frame.monto,
                            months if months is not None else [
                                {"mes": f"2026-0{month}", "ingresos": 100, "parcial": False}
                                for month in [4, 5, 6]])


def test_tracks_ids_not_names_and_keeps_leading_zeros():
    result = activity([("001", "Antes", "2026-01-01", 100),
                       ("001", "Renombrado", "2026-03-31", 200),
                       ("002", "Renombrado", "2026-06-01", 50)])
    assert result["total_sin_ventas"] == 1
    assert result["productos"][0] == {
        "id": "001", "nombre": "Renombrado", "ultima_venta": "2026-03-31",
        "meses_sin_venta_observada": 3, "ingresos_historicos": 300.0,
    }
    assert result["fecha_corte"] == "2026-06-30"


def test_undated_positive_sale_prevents_inactivity_claim():
    result = activity([("001", "A", "2026-01-01", 100), ("001", "A", None, 10)])
    assert result["productos"] == []


def test_returns_and_zero_values_are_not_sales():
    result = activity([("001", "A", "2026-01-01", 100), ("001", "A", "2026-06-01", -10),
                       ("001", "A", "2026-06-02", 0)])
    assert result["productos"][0]["meses_sin_venta_observada"] == 5


@pytest.mark.parametrize("months", [[], [{"mes": "2026-06", "ingresos": 10}],
    [{"mes": month, "ingresos": 10} for month in ["2026-02", "2026-04", "2026-06"]],
    [{"mes": f"2026-0{month}", "ingresos": 10, "parcial": month == 6} for month in [4, 5, 6]],
])
def test_requires_three_consecutive_nonpartial_months(months):
    assert activity([("001", "A", "2026-01-01", 100)], months) is None


def test_never_infers_identity_from_names_or_missing_keys():
    assert activity([("A", "A", "2026-01-01", 100)], key="nombre") is None
    assert activity([(None, "A", "2026-01-01", 100)]) is None


def test_output_is_bounded_without_understating_total():
    result = activity([(str(i), "A", "2026-01-01", 10) for i in range(15)])
    assert len(result["productos"]) == 10
    assert result["total_sin_ventas"] == 15
