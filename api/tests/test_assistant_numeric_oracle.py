"""Independent five-row oracle: signed sales, costs, months and categories."""

from copy import deepcopy

import pandas as pd
import pytest

from app.engine.clean import analyze_and_clean
from app.engine.metrics import compute_metrics
from app.support_knowledge import answer_for
from app.metric_assistant import format_amount


@pytest.fixture
def oracle_metrics():
    frame = pd.DataFrame({
        "Fecha": ["2026-01-10", "2026-02-10", "2026-01-15", "2026-02-15", "2026-02-20"],
        "Categoria": ["Retail", "Retail", "Ferreteria", "Distribucion", "Retail"],
        "Cantidad": [10, 30, 20, 5, -5],
        "Venta": [100, 300, 200, 50, -50],
        "Costo": [60, 180, 120, 30, -30],
    })
    result = compute_metrics(frame, mapping={
        "fecha": "Fecha", "categoria": "Categoria", "cantidad": "Cantidad",
        "monto": "Venta", "costo": "Costo",
    })
    assert result["kpis"]["ingresos_totales"]["valor"] == 600
    assert result["kpis"]["gastos_totales"]["valor"] == 360
    assert result["kpis"]["ganancia_neta"]["valor"] == 240
    assert result["kpis"]["margen_utilidad_pct"]["valor"] == 40
    assert result["kpis"]["unidades_totales"] == 60
    return result


def test_ranking_percentage_matches_net_amount_after_returns(oracle_metrics):
    reply = answer_for("que categoria vendio mas", metrics=oracle_metrics)
    assert "$350" in reply["answer"]
    assert "58,3% de las ventas netas" in reply["answer"], reply
    assert "61,5%" not in reply["answer"]


def test_long_conversation_uses_real_engine_metrics(oracle_metrics):
    history = []
    for question, expected in [
        ("cuantosingresostengo", ["$600"]),
        ("cuanto suman Distribucion y Ferreteria", ["$250", "Distribucion", "Ferreteria"]),
        ("cual fue la peor categoria", ["Distribucion", "$50"]),
        # February ends on day 20 in the source: only January is comparable.
        ("mejor mes de Retail", ["Retail", "2026-01", "$100", "completa"]),
        ("cuantas unidades vendi en general", ["60"]),
        ("cuantas unidades devolvieron", ["5 unidades", "no confirma"]),
        ("que hace esta plataforma", ["Limpieza", "Explorar"]),
        ("necesito ayuda de un humano", ["servicios@adsveris.com"]),
        ("mis ingresos en general", ["$600"]),
    ]:
        reply = answer_for(question, metrics=oracle_metrics, history=history[-12:])
        for part in expected:
            assert part in reply["answer"], (question, reply)
        history += [{"role": "user", "content": question}, {"role": "assistant", "content": reply["answer"]}]


def test_dataset_currency_switch_does_not_convert_or_reuse_old_amounts(oracle_metrics):
    uf = deepcopy(oracle_metrics)
    uf["moneda"] = "UF"
    reply = answer_for("mis ingresos totales", metrics=uf, history=[
        {"role": "user", "content": "mis ingresos totales"},
        {"role": "assistant", "content": "Tu archivo anterior tiene $999.999 de ingresos."},
    ])
    assert "UF 600" in reply["answer"] and "999.999" not in reply["answer"]


@pytest.mark.parametrize("amount,expected", [(0.004, "UF 0,004"), (1.239, "UF 1,239"),
                                           (1e-9, "<UF 0,00000001"), (-1e-9, ">UF -0,00000001")])
def test_bot_does_not_erase_small_uf_balances(amount, expected):
    assert format_amount(amount, "UF") == expected


def test_bot_preserves_foreign_currency_cents():
    assert format_amount(12.34, "USD") == "US$12,34"
    assert format_amount(12.34, "EUR") == "EUR 12,34"


def test_out_of_range_number_is_preserved_for_review_not_summed_or_deleted():
    frame = pd.DataFrame({"Venta": ["10", "1e309", "20"], "ID": ["001", "002", "003"],
                          "Fecha": ["2026-01-01"] * 3})
    mapping = {"monto": "Venta", "fecha": "Fecha"}
    result = analyze_and_clean(frame, None, True, mapping=mapping)
    cleaned = result["_df_limpio"]
    assert cleaned["ID"].tolist() == ["001", "002", "003"]
    assert cleaned["Venta"].tolist() == ["10", "1e309", "20"]
    assert result["problemas"]["tipos_incorrectos"] == 1
    metrics = compute_metrics(cleaned, mapping=mapping)
    assert metrics["kpis"]["ingresos_totales"]["valor"] == 30
