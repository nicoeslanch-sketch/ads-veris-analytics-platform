"""Regression evidence from the challenging multi-sheet workbook audit."""

import copy

import pandas as pd
import pytest

from app.engine.clean import analyze_and_clean
from app.engine.metrics import compute_metrics
from app.language_normalization import normalize_query
from app.support_knowledge import answer_for


def _expenses():
    return compute_metrics(pd.DataFrame({
        "ID_Gasto": ["G1", "G2", "G3"],
        "Fecha Gasto": ["01/01/2026", "01/02/2026", "02/02/2026"],
        "Categoria Gasto": ["Arriendo", "Arriendo", "Logistica"],
        "Monto Neto": [100, 200, 300], "IVA": [19, 38, 57],
        "Total Gasto": [119, 238, 357], "Estado": ["Pagado"] * 3,
    }))


def test_cleaning_detaches_heavy_provenance_but_preserves_source_and_types(monkeypatch):
    from app.engine import clean
    from app.engine.standardize import standardize_dataframe
    source = pd.DataFrame({"ID": ["001", "002", "002"], "Monto": ["1.000", "2.000", "2.000"]})
    source.attrs = {"source_rows": [5, 7, 9], "source_sheet": "Datos"}
    standardized = standardize_dataframe(source)
    attrs_before = copy.deepcopy(standardized[0].attrs)
    detect = clean._detect_problems
    def check(frame, *args, **kwargs):
        assert "source_rows" not in frame.attrs
        return detect(frame, *args, **kwargs)
    monkeypatch.setattr(clean, "_detect_problems", check)
    result = analyze_and_clean(source, {}, True, standardized=standardized, eliminar_duplicados=True)
    assert result["_source_rows_limpio"] == [5, 7]
    assert result["_df_limpio"].attrs["source_rows"] == [5, 7]
    assert source.attrs["source_rows"] == [5, 7, 9]
    assert standardized[0].attrs == attrs_before
    assert result["_df_limpio"]["ID"].tolist() == ["001", "002"]


def test_operational_metrics_filter_dates_and_reconcile_breakdowns():
    frame = pd.DataFrame({
        "Fecha Gasto": ["01/01/2026", "01/02/2026", "02/02/2026"],
        "Categoria Gasto": ["Arriendo", "Arriendo", "Logistica"],
        "Monto Neto": [100, 200, 300], "Total Gasto": [119, 238, 357],
    })
    metrics = compute_metrics(frame, date_from="2026-02-01", date_to="2026-02-28")
    generic = metrics["analisis_generico"]
    assert generic["registros"] == 2
    net = next(row for row in generic["numericas"] if row["columna"] == "Monto Neto")
    assert net["total"] == 500
    grouped = next(row for row in generic["desgloses"] if row["columna"] == "Monto Neto")
    assert sum(row["valor"] for row in grouped["valores"]) == 500
    assert [row["mes"] for row in generic["evolucion"]["valores"]] == ["2026-02"]


def test_constant_operational_metric_is_not_dropped_and_goals_are_not_customers():
    metrics = compute_metrics(pd.DataFrame({
        "Mes": ["01/01/2026", "01/02/2026"], "ID_Sucursal": ["S1", "S2"],
        "Meta Venta Neta": [100, 100], "Meta Nuevos Clientes": [5, 8],
    }))
    assert metrics["kpis"]["ingresos_totales"] is None
    assert not metrics.get("clientes")
    assert not metrics.get("agrupaciones_flexibles")
    assert any(row["total"] == 200 for row in metrics["analisis_generico"]["numericas"])
    answer = answer_for("cual es la meta nuevos clientes", metrics=metrics)
    assert answer["matched_key"] == "metric_generic_numeric"
    assert "13" in answer["answer"]


def test_ambiguous_amount_does_not_leak_sales_charts():
    metrics = compute_metrics(pd.DataFrame({
        "Fecha": ["01/01/2026"] * 3, "Monto": [100, 200, 300],
        "Descuento_Pct": [0.1, 0.2, 0.3],
    }))
    assert metrics["kpis"]["ingresos_totales"] is None
    assert not metrics.get("agrupaciones_flexibles")


def test_sales_dimensions_do_not_turn_taxes_and_amounts_into_categories():
    metrics = compute_metrics(pd.DataFrame({
        "Fecha": ["01/01/2026"] * 3, "Ventas": [100, 200, 300],
        "IVA": [19, 38, 57], "Total Documento": [119, 238, 357],
        "Estado": ["Pagado", "Pendiente", "Pagado"],
    }))
    columns = [item["columna"] for item in metrics.get("agrupaciones_flexibles", [])]
    assert "Estado" in columns
    assert "IVA" not in columns
    assert "Total Documento" not in columns


def test_inventory_risk_uses_record_grain_and_customer_count_is_direct():
    inventory = answer_for("cuantos bajo el minimo", metrics={
        "analisis_inventario": {"registros": 10, "productos": 3, "bajo_minimo": 5},
    })
    assert "5 registros" in inventory["answer"]
    assert "5 productos" not in inventory["answer"]
    customers = answer_for("cuantos clientes tengo", metrics={
        "clientes": {"unicos": 3, "top": [{"nombre": "A", "ingresos": 100}]},
    })
    assert customers["matched_key"] == "metric_customer_count"
    assert customers["answer"].startswith("Hay 3 clientes")


@pytest.mark.parametrize(("question", "key", "value"), [
    ("cuantogaste", "metric_generic_numeric", "$714"),
    ("cual es mi gasto neto", "metric_generic_numeric", "$600"),
    ("cual es el gasto mas alto", "metric_generic_numeric", "$357"),
    ("cual es la categoria principal", "metric_generic_distribution", "Arriendo"),
    ("cuanto gaste por categoria", "metric_generic_breakdown", "$357"),
    ("dame un resumen", "metric_generic_overview", "3 registros"),
    ("cuanto es el iva", "metric_generic_numeric", "$114"),
])
def test_operational_conversation_uses_the_correct_measure(question, key, value):
    answer = answer_for(question, metrics=_expenses())
    assert answer["matched_key"] == key
    assert value in answer["answer"]


def test_statistic_follow_up_changes_operation_not_column():
    metrics = _expenses()
    history = [{"role": "user", "content": "cual es el gasto promedio"}]
    maximum = answer_for("y el maximo", metrics=metrics, history=history)
    assert "maximo" in maximum["answer"]
    assert "$357" in maximum["answer"]
    median = answer_for("cual es la mediana", metrics=metrics, history=history)
    assert "La mediana" in median["answer"]
    assert "$238" in median["answer"]


def test_missing_credit_limits_do_not_turn_into_file_upload_advice():
    metrics = {"moneda": "CLP", "analisis_generico": {
        "subtipo": "clientes", "registros": 20, "numericas": [], "distribuciones": [],
    }}
    history = []
    for question in ("cual es el limite credito promedio", "y el maximo", "y la mediana"):
        answer = answer_for(question, metrics=metrics, history=history)
        assert answer["matched_key"] == "metric_generic_numeric_unavailable"
        assert "15 MB" not in answer["answer"]
        history.extend([{"role": "user", "content": question},
                        {"role": "assistant", "content": answer["answer"]}])
    summary = answer_for("dame un resumen", metrics=metrics)
    assert ". ." not in summary["answer"]


@pytest.mark.parametrize("column", ["MetaMargenPct", "Meta Margen Bruto %"])
def test_camelcase_goals_are_percentages_not_additive_sales_or_realized_margin(column):
    metrics = compute_metrics(pd.DataFrame({
        "Periodo": ["2026-01", "2026-02"], "IDSucursal": ["S1", "S1"],
        "MetaVentasNeto_CLP": [1000, 2000], column: [0.3, 0.4],
    }))
    margin = next(r for r in metrics["analisis_generico"]["numericas"] if r["columna"] == column)
    assert margin["formato"] == "porcentaje"
    assert margin["total"] is None
    assert margin["promedio"] == 35
    history = []
    for question, expected_key, value in (
        ("cuanto es mi meta venta neta", "metric_generic_numeric", "$3.000"),
        ("y la meta margen bruto", "metric_generic_numeric", "35%"),
        ("cual es la mediana", "metric_generic_numeric", "35%"),
        ("y el maximo", "metric_generic_numeric", "40%"),
        ("cual es la meta nuevos clientes", "metric_generic_numeric_unavailable", "No hay una meta"),
    ):
        answer = answer_for(question, metrics=metrics, history=history)
        assert answer["matched_key"] == expected_key, answer
        assert value in answer["answer"], answer
        history.extend([{"role": "user", "content": question}, {"role": "assistant", "content": answer["answer"]}])


def test_sales_headers_are_not_a_customer_master_or_realized_revenue():
    metrics = compute_metrics(pd.DataFrame({
        "IDVenta": ["V1", "V2", "V3"],
        "FechaVenta": ["2026-01-02"] * 3,
        "IDCliente": ["C1", "C1", "C2"],
        "EstadoVenta": ["Pagada", "Anulada", "Pagada"],
    }))
    assert metrics["analisis_generico"]["subtipo"] == "cabeceras_ventas"
    assert metrics["kpis"]["ingresos_totales"] is None
    for question in ("dame un resumen", "cuantos clientes tengo", "mis ingresos totales", "cuanta utilidad tengo"):
        answer = answer_for(question, metrics=metrics)
        assert answer["matched_key"] == "metric_document_headers", answer
        assert "3 registros de cabeceras de ventas" in answer["answer"]
        assert "IDVenta" in answer["answer"]


def test_absent_cost_coverage_is_not_presented_as_zero_cost():
    answer = answer_for("y mis costos", metrics={
        "moneda": "CLP", "analisis_negocio": {"estado_resultados": {
            "ventas_observadas": 100, "costo_venta_conocido": 0, "cobertura_costos_pct": 0,
        }},
    })
    assert answer["matched_key"] == "metric_business_finances"
    assert "Costo de venta conocido no disponible" in answer["answer"]
    assert "$0" not in answer["answer"]


@pytest.mark.parametrize(("raw", "expected"), [
    ("puedo confiar en estos numeros", "puedo confiar en estos numeros"),
    ("unidadescomprometidas", "unidades comprometidas"),
    ("diferenciadeconteo", "diferencia de conteo"),
    ("cual es la medaina", "cual es la mediana"),
    ("categroia", "categoria"),
    ("quien es mi mejor vendedor", "quien es mi mejor vendedor"),
    ("SKU-003 PROV-017", "sku 003 prov 017"),
    ("no se pudo conectar al servidro", "no se pudo conectar al servidor"),
])
def test_typo_dictionary_preserves_valid_words_and_identifiers(raw, expected):
    assert normalize_query(raw) == expected


def test_inventory_conversation_routes_before_sales_dimensions():
    metrics = {"moneda": "CLP", "analisis_inventario": {
        "stock_total": 100, "productos": 10, "bajo_minimo": 2,
        "unidades_comprometidas": 8, "diferencia_conteo": -2,
        "por_sucursal": [{"nombre": "S1", "stock": 70, "bajo_minimo": 0},
                         {"nombre": "S2", "stock": 30, "bajo_minimo": 2}],
    }}
    history = []
    for question, expected in [("que sucursal tiene mas stock", "S1"),
                               ("y cual tiene menos", "S2"),
                               ("cuantas unidadescomprometidas tengo", "8 unidades"),
                               ("cual es la diferenciadeconteo", "-2 unidades"),
                               ("cuantos estan bajo el minimo", "2 registros")]:
        answer = answer_for(question, metrics=metrics, history=history)
        assert answer["matched_key"].startswith("metric_inventory")
        assert expected in answer["answer"]
        history.append({"role": "user", "content": question})


@pytest.mark.parametrize(("question", "key", "value"), [
    ("que mes vendi mas", "metric_best_month", "$300"),
    ("quemesvendimas", "metric_best_month", "$300"),
    ("en que mes vendimos menos", "metric_worst_month", "$100"),
    ("cual es el mes con mayores ingresos", "metric_best_month", "$300"),
    ("en que mes facture menos", "metric_worst_month", "$100"),
])
def test_natural_month_questions_read_the_dashboard(question, key, value):
    answer = answer_for(question, metrics={
        "moneda": "CLP", "evolucion_mensual": [
            {"mes": "2026-01", "ingresos": 100},
            {"mes": "2026-02", "ingresos": 300},
        ],
    })
    assert answer["matched_key"] == key
    assert value in answer["answer"]


def test_missing_liquidity_explains_which_balance_sources_are_needed():
    answer = answer_for("tengo buena liquidez", metrics=_expenses())
    assert "activos corrientes" in answer["answer"]
    assert "pasivos corrientes" in answer["answer"]
