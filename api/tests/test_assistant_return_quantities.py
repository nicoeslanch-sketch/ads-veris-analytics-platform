"""A quantity of returns must never be answered with all units sold."""

import pytest

from app.support_knowledge import answer_for
from tests.assistant_scenarios import screenshot_metrics


@pytest.mark.parametrize("question", [
    "cuantas unidades devolvieron", "cuantas unidades fueron devueltas",
    "cantidad de unidades negativas", "total de unidades de devoluciones",
    "unidades devueltas", "cuantas unidades son reversas",
])
@pytest.mark.parametrize("known", [True, False])
def test_return_quantity_uses_negative_units_only_when_published(question, known):
    metrics = screenshot_metrics()
    if known:
        metrics["kpis"]["unidades_detalle"] = {
            "positivas": 201328, "negativas": -5, "filas_sin_cantidad": 1,
            "filas_monto_negativo_cantidad_positiva": 1,
        }
    reply = answer_for(question, metrics=metrics)
    assert "201.323" not in reply["answer"], reply
    if known:
        assert "5 unidades" in reply["answer"], reply
        assert "no confirma" in reply["answer"].lower(), reply
        assert "positiva" in reply["answer"] and "sin cantidad" in reply["answer"], reply
    else:
        assert reply["confidence"] != "high", reply
        assert "No tengo" in reply["answer"], reply
