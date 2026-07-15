"""Pruebas de la Fase 12: exactitud auditada de los dashboards.

Cada valor esperado está calculado A MANO (verdad independiente del motor)
sobre un dataset sintético controlado: 3 meses, costos parciales, una fila sin
fecha, un monto ilegible, una categoría vacía, una reversa y un cero.
"""

import io

import pandas as pd
import pytest

from app.engine.clean import analyze_and_clean
from app.engine.loader import load_dataframe_with_report
from app.engine.metrics import compute_metrics

CSV_AUDIT = (
    "Fecha;Categoria;Canal;Producto;Ventas;Costo;Cantidad\n"
    "05/01/2026;A;Web;P1;100000;60000;2\n"
    "10/01/2026;A;Tienda;P2;50000;;1\n"
    "15/01/2026;B;Web;P1;200000;120000;4\n"
    "20/01/2026;B;Tienda;P3;0;0;0\n"
    "03/02/2026;A;Web;P2;80000;40000;2\n"
    "09/02/2026;B;Web;P3;-20000;;1\n"
    "14/02/2026;;Tienda;P1;120000;70000;3\n"
    "21/02/2026;A;Web;P1;150000;90000;3\n"
    "02/03/2026;B;Tienda;P2;90000;50000;2\n"
    "18/03/2026;A;Web;P3;60000;;1\n"
    ";A;Web;P1;40000;20000;1\n"
    "25/03/2026;B;Tienda;P2;N/A;;1\n"
)


@pytest.fixture(scope="module")
def metrics_audit():
    df, _ = load_dataframe_with_report("audit.csv", CSV_AUDIT.encode("utf-8"))
    result = analyze_and_clean(df, None, apply=True)
    return compute_metrics(result["_df_limpio"])


def test_totales_toman_todas_las_filas(metrics_audit):
    """Verdad a mano: 11 montos legibles suman 870.000 (incluye reversa y cero)."""
    kpis = metrics_audit["kpis"]
    assert kpis["ingresos_totales"]["valor"] == 870000.0
    assert kpis["transacciones"] == 12
    assert kpis["ticket_promedio"] == round(870000 / 11, 2)
    assert kpis["unidades_totales"] == 21.0


def test_utilidad_y_cobertura_pareadas(metrics_audit):
    """8 filas con ingreso Y costo: 780.000 − 450.000 = 330.000 (42.3%)."""
    kpis = metrics_audit["kpis"]
    assert kpis["gastos_totales"]["valor"] == 450000.0
    assert kpis["ganancia_neta"]["valor"] == 330000.0
    assert kpis["margen_utilidad_pct"]["valor"] == 42.3
    assert kpis["cobertura_costos"] == {
        "filas_con_ingreso": 11,
        "filas_con_ingreso_y_costo": 8,
        "pct": 72.7,
    }


def test_evolucion_mensual_exacta(metrics_audit):
    evo = {e["mes"]: e for e in metrics_audit["evolucion_mensual"]}
    assert evo["2026-01"]["ingresos"] == 350000.0
    assert evo["2026-02"]["ingresos"] == 330000.0
    assert evo["2026-03"]["ingresos"] == 150000.0
    assert metrics_audit["periodo"]["meses_disponibles"] == ["2026-01", "2026-02", "2026-03"]


def test_venta_sin_fecha_avisa_y_suma_al_total(metrics_audit):
    """La fila de 40.000 sin fecha SUMA al total pero no a la evolución — con aviso."""
    suma_evo = sum(e["ingresos"] for e in metrics_audit["evolucion_mensual"])
    assert suma_evo == 830000.0  # 870.000 − 40.000 sin fecha
    assert any("no tienen fecha válida" in a for a in metrics_audit["advertencias"])


def test_categorias_cuadran_con_el_total(metrics_audit):
    cats = {c["nombre"]: c for c in metrics_audit["por_categoria"]}
    assert cats["A"]["ingresos"] == 480000.0
    assert cats["B"]["ingresos"] == 270000.0
    assert cats["Sin clasificar"]["ingresos"] == 120000.0
    assert sum(c["ingresos"] for c in cats.values()) == 870000.0


def test_margen_por_grupo_usa_filas_pareadas(metrics_audit):
    """Antes: 160.000/480.000 = 33.3% (dividía por ingresos SIN costo).
    Correcto: 160.000/370.000 = 43.2% (misma regla que el KPI global)."""
    cats = {c["nombre"]: c for c in metrics_audit["por_categoria"]}
    assert cats["A"]["margen_pct"] == 43.2
    # Producto y canal también reciben margen pareado (decisión PyME clave)
    tp = {p["nombre"]: p for p in metrics_audit["top_productos"]}
    assert "margen_pct" in tp["P1"]


def test_grupo_sin_costos_no_inventa_margen(metrics_audit):
    """P3: ventas 40.000 con un solo costo pareado (el cero) — el margen de un
    grupo sin filas pareadas se omite, jamás un 0 falso."""
    canales = {c["nombre"]: c for c in metrics_audit["ventas_por_canal"]}
    assert canales["Web"]["ingresos"] == 610000.0
    assert canales["Tienda"]["ingresos"] == 260000.0


def test_gastos_mensuales_incluyen_costos_sin_ingreso():
    """Fila con costo legible y monto ilegible: el gasto aparece en el KPI Y
    en el gráfico mensual (antes el gráfico lo perdía y no cuadraban)."""
    csv = "Fecha;Ventas;Costo\n05/01/2026;100000;60000\n10/01/2026;N/A;30000\n"
    df, _ = load_dataframe_with_report("b.csv", csv.encode())
    m = compute_metrics(analyze_and_clean(df, None, apply=True)["_df_limpio"])
    assert m["kpis"]["gastos_totales"]["valor"] == 90000.0
    assert m["evolucion_mensual"][0]["gastos"] == 90000.0


def test_dimension_monto_exige_montos_legibles():
    """Columna de monto con puro texto ilegible → dimensiones.monto False:
    el frontend muestra la guía de mapeo, no un dashboard en $0."""
    csv = "Fecha;Ventas\n05/01/2026;N/A\n06/01/2026;pendiente\n"
    df, _ = load_dataframe_with_report("c.csv", csv.encode())
    m = compute_metrics(analyze_and_clean(df, None, apply=True)["_df_limpio"])
    assert m["dimensiones"]["monto"] is False


def test_excel_con_encabezados_duplicados_no_crashea():
    buf = io.BytesIO()
    pd.DataFrame(
        [["01/05/2026", 100, 200], ["02/05/2026", 300, 400]],
        columns=["Fecha", "Ventas", "Ventas"],
    ).to_excel(buf, index=False)
    df, report = load_dataframe_with_report("dup.xlsx", buf.getvalue())
    assert list(df.columns) == ["Fecha", "Ventas", "Ventas.1"]
    assert any("repetido" in a for a in report["avisos"])
    m = compute_metrics(analyze_and_clean(df, None, apply=True)["_df_limpio"])
    assert m["kpis"]["ingresos_totales"]["valor"] == 400.0


def test_excel_encabezados_repetidos_no_colisionan_con_un_sufijo_existente():
    buf = io.BytesIO()
    pd.DataFrame(
        [["01/05/2026", 100, 200, 300]],
        columns=["Fecha", "Ventas", "Ventas.1", "Ventas"],
    ).to_excel(buf, index=False)

    df, report = load_dataframe_with_report("sufijos.xlsx", buf.getvalue())

    assert list(df.columns) == ["Fecha", "Ventas", "Ventas.1", "Ventas.2"]
    assert len(set(df.columns)) == len(df.columns)
    assert any("repetido" in warning for warning in report["avisos"])


CSV_CLIENTES = (
    "Fecha;Cliente;Producto;Ventas;Costo\n"
    "05/01/2026;ACME;P1;100000;60000\n"
    "06/01/2026;Beta Ltda;P1;50000;30000\n"
    "12/01/2026;ACME;P2;200000;\n"
    "13/01/2026;Sin Nombre;P2;30000;10000\n"
)


@pytest.fixture(scope="module")
def metrics_clientes():
    df, _ = load_dataframe_with_report("cli.csv", CSV_CLIENTES.encode())
    return compute_metrics(analyze_and_clean(df, None, apply=True)["_df_limpio"])


def test_clientes_concentracion(metrics_clientes):
    """ACME 300.000 de 350.000 identificados (85.7%); 'Sin Nombre' NO es un cliente."""
    clientes = metrics_clientes["clientes"]
    assert clientes["unicos"] == 2
    assert clientes["top"][0]["nombre"] == "ACME"
    assert clientes["top"][0]["ingresos"] == 300000.0
    assert clientes["concentracion_top_pct"] == 85.7


def test_por_dia_semana(metrics_clientes):
    """05 y 12 de enero 2026 son lunes; 06 y 13, martes."""
    dias = {d["dia"]: d for d in metrics_clientes["por_dia_semana"]}
    assert dias["lunes"]["ingresos"] == 300000.0
    assert dias["lunes"]["transacciones"] == 2
    assert dias["martes"]["ingresos"] == 80000.0


def test_filtro_mes_calendario(metrics_audit):
    """Febrero completo se compara contra enero; los totales del mes cuadran."""
    df, _ = load_dataframe_with_report("audit.csv", CSV_AUDIT.encode("utf-8"))
    df_limpio = analyze_and_clean(df, None, apply=True)["_df_limpio"]
    feb = compute_metrics(df_limpio, date_from="2026-02-01", date_to="2026-02-28")
    assert feb["kpis"]["ingresos_totales"]["valor"] == 330000.0
    assert feb["kpis"]["transacciones"] == 4
    assert feb["kpis"]["ingresos_totales"]["variacion_pct"] == round(
        (330000 - 350000) / 350000 * 100, 1
    )
