"""Pruebas de la Fase 12b: triage verificado del informe de calidad externo.

Cada test corresponde a un punto del informe que se CONFIRMÓ contra el código
antes de corregirse.
"""

import io

import pandas as pd

from app.engine.clean import analyze_and_clean
from app.engine.loader import (
    MAX_COLUMNS,
    UnsupportedFileError,
    load_dataframe_with_report,
)
from app.engine.metrics import compute_metrics
from app.engine.standardize import column_comma3_convention, parse_number


def _run(csv: str, apply: bool = True):
    df, report = load_dataframe_with_report("t.csv", csv.encode("utf-8"))
    return analyze_and_clean(df, None, apply=apply), report


# ── P0.1: los valores no interpretables se CONSERVAN ─────────────────────────


def test_fechas_y_numeros_ilegibles_se_conservan():
    csv = (
        "Fecha;Ventas\n"
        "05/01/2026;100000\n"
        "31/02/2026;pendiente confirmar\n"  # fecha imposible + monto ilegible
    )
    result, _ = _run(csv)
    df = result["_df_limpio"]
    valores = df.iloc[1].tolist()
    assert "31/02/2026" in valores  # la fecha imposible NO se vació
    assert any("pendiente" in str(v).lower() for v in valores)  # el monto tampoco
    # Y siguen contando como problema tras la limpieza (la calidad no puede
    # "mejorar" destruyendo la evidencia)
    assert result["resumen"]["calidad_despues"] < 100.0


def test_ingresos_ignoran_los_ilegibles_preservados():
    csv = "Fecha;Ventas\n05/01/2026;100000\n06/01/2026;por confirmar\n"
    result, _ = _run(csv)
    m = compute_metrics(result["_df_limpio"])
    assert m["kpis"]["ingresos_totales"]["valor"] == 100000.0
    assert m["kpis"]["registros_con_monto"] == 1


# ── P0.4: "1,234" por evidencia de columna ───────────────────────────────────


def test_coma_ambigua_con_evidencia_us_es_miles():
    serie = pd.Series(["1,234", "12,345.67", "2,500"])
    convention, ambiguous = column_comma3_convention(serie)
    assert convention == "miles"
    assert parse_number("1,234", comma3_convention="miles") == 1234


def test_coma_ambigua_sin_evidencia_sigue_decimal_y_avisa():
    serie = pd.Series(["1,234", "500", "80"])
    convention, ambiguous = column_comma3_convention(serie)
    assert convention == "decimal"
    assert ambiguous == 1
    assert parse_number("1,234") == 1.234  # comportamiento es-CL intacto
    # El pipeline avisa la ambigüedad
    csv = "Fecha;Ventas\n05/01/2026;1,234\n06/01/2026;500\n"
    result, _ = _run(csv)
    assert any("ambiguos" in a for a in result.get("avisos", []))


def test_coma_decimal_clara_no_cambia():
    assert parse_number("12,5") == 12.5
    assert parse_number("1.234,56") == 1234.56
    assert parse_number("1,234.56") == 1234.56


# ── §7: el nombre "fecha" ya no basta con una sola celda ─────────────────────


def test_columna_texto_con_nombre_fecha_no_se_clasifica_fecha():
    csv = (
        "Fecha entrega;Ventas\n"
        "por coordinar;100\n"
        "cliente avisa;200\n"
        "05/01/2026;300\n"  # 1 de 3 con forma de fecha (33%... bajo 60%)
        "sin definir;400\n"
        "pendiente;500\n"
    )
    result, _ = _run(csv, apply=False)
    # 1/5 = 20% < 30%: la columna queda como texto, nada se marca inválido
    assert result["column_types"]["Fecha entrega"] == "texto"


# ── §13: margen mensual pareado en la evolución ──────────────────────────────


def test_evolucion_trae_margen_pareado_por_mes():
    csv = (
        "Fecha;Ventas;Costo\n"
        "05/01/2026;100000;60000\n"
        "10/01/2026;100000;\n"  # sin costo: NO diluye el margen del mes
    )
    result, _ = _run(csv)
    m = compute_metrics(result["_df_limpio"])
    enero = m["evolucion_mensual"][0]
    # margen pareado: (100000-60000)/100000 = 40% — no 40000/200000 = 20%
    assert enero["margen_pareado_pct"] == 40.0
    assert enero["cobertura_costos_pct"] == 50.0


# ── §16: devoluciones visibles ───────────────────────────────────────────────


def test_devoluciones_reportadas():
    csv = "Fecha;Ventas\n05/01/2026;100000\n06/01/2026;-20000\n"
    result, _ = _run(csv)
    m = compute_metrics(result["_df_limpio"])
    assert m["kpis"]["ingresos_totales"]["valor"] == 80000.0  # netos
    assert m["kpis"]["devoluciones"] == {"monto": -20000.0, "filas": 1}
    assert any("NETOS" in a for a in m["advertencias"])


# ── §21/§22: coberturas expuestas ────────────────────────────────────────────


def test_clientes_cobertura_identificacion():
    csv = (
        "Fecha;Cliente;Ventas\n"
        "05/01/2026;ACME;100000\n"
        "06/01/2026;;100000\n"  # mitad de las ventas sin cliente
    )
    result, _ = _run(csv)
    m = compute_metrics(result["_df_limpio"])
    assert m["clientes"]["cobertura_identificacion_pct"] == 50.0


def test_grupos_exponen_base_de_calculo():
    csv = (
        "Fecha;Categoria;Ventas;Costo\n"
        "05/01/2026;A;100000;60000\n"
        "06/01/2026;A;100000;\n"
        "07/01/2026;B;50000;30000\n"
    )
    result, _ = _run(csv)
    m = compute_metrics(result["_df_limpio"])
    cats = {c["nombre"]: c for c in m["por_categoria"]}
    assert cats["A"]["filas"] == 2
    assert cats["A"]["filas_pareadas"] == 1
    assert cats["A"]["cobertura_costos_pct"] == 50.0


# ── §9: columnas vacías — detectar sí, eliminar no por defecto ───────────────


def test_columna_vacia_se_detecta_pero_no_se_elimina_por_defecto():
    csv = "Fecha;Notas;Ventas\n05/01/2026;;100\n06/01/2026;;200\n"
    result, _ = _run(csv)
    assert result["problemas"]["columnas_vacias"] == 1
    assert "Notas" in list(result["_df_limpio"].columns)  # conservada
    # Con la regla activada explícitamente, sí se elimina
    df, _ = load_dataframe_with_report("t.csv", csv.encode())
    applied = analyze_and_clean(df, {"columnas_vacias": True}, apply=True)
    assert "Notas" not in list(applied["_df_limpio"].columns)


# ── §10: "Total Energies" al final NO es una fila de totales ─────────────────


def test_fila_de_datos_que_empieza_con_total_no_se_elimina():
    csv = (
        "Fecha;Cliente;Ventas\n"
        "05/01/2026;ACME;100\n"
        "06/01/2026;Total Energies;200\n"  # empresa real al FINAL
    )
    df, report = load_dataframe_with_report("t.csv", csv.encode())
    # La fila tiene otras celdas con texto no numérico (la fecha ya la hace
    # no-resumen): se conserva
    assert len(df) == 2
    assert report["filas_totales_omitidas"] == 0


def test_fila_resumen_real_si_se_elimina():
    csv = "Cliente;Ventas\nACME;100\nBeta;200\nTotal;300\n"
    df, report = load_dataframe_with_report("t.csv", csv.encode())
    assert len(df) == 2
    assert report["filas_totales_omitidas"] == 1


# ── §30: límites de columnas y celdas ────────────────────────────────────────


def test_limite_de_columnas():
    headers = ";".join(f"c{i}" for i in range(MAX_COLUMNS + 1))
    row = ";".join("1" for _ in range(MAX_COLUMNS + 1))
    try:
        load_dataframe_with_report("t.csv", f"{headers}\n{row}\n".encode())
        raise AssertionError("debió rechazar el archivo")
    except UnsupportedFileError as err:
        assert "columnas" in str(err)


# ── §24: hasta 12 productos ──────────────────────────────────────────────────


def test_top_productos_hasta_doce():
    filas = "\n".join(f"05/01/2026;P{i:02d};{1000 * (i + 1)}" for i in range(15))
    csv = "Fecha;Producto;Ventas\n" + filas
    result, _ = _run(csv)
    m = compute_metrics(result["_df_limpio"])
    assert len(m["top_productos"]) == 12
