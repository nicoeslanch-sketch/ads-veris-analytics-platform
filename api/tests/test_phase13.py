"""Pruebas de la Fase 13: cuentas sin plan + triage verificado del 2º informe."""

import pandas as pd
import pytest
from fastapi import HTTPException

from app.capabilities import (
    Capability,
    normalize_plan,
    plan_allows,
    require_capability_for_user,
)
from app.engine.clean import analyze_and_clean
from app.engine.loader import _detect_separator, load_dataframe_with_report
from app.engine.metrics import compute_metrics, detect_currency
from app.engine.standardize import format_number, parse_number, standardize_dataframe


def _run(csv: str):
    df, report = load_dataframe_with_report("t.csv", csv.encode("utf-8"))
    return analyze_and_clean(df, None, apply=True), report


# ── Cuentas sin plan (Fase 13) ───────────────────────────────────────────────


def test_sin_plan_no_tiene_capacidades():
    assert normalize_plan("sin_plan") == "sin_plan"
    assert not plan_allows("sin_plan", Capability.STANDARDIZE)
    assert not plan_allows("sin_plan", Capability.CLEAN)


def test_cuentas_existentes_conservan_basico():
    """Sin fila en profiles o plan legado → 'basico': nadie pierde acceso."""
    assert normalize_plan(None) == "basico"
    assert normalize_plan("basico") == "basico"
    assert plan_allows("basico", Capability.STANDARDIZE)


def test_sin_plan_recibe_403_con_mensaje_de_planes(monkeypatch):
    from app import capabilities

    class FakeSettings:
        plan_enforcement = True
        supabase_url = "https://example.supabase.co"
        supabase_service_role_key = "clave"

    monkeypatch.setattr(
        capabilities, "get_profile_flags", lambda uid, st: ("sin_plan", False)
    )
    with pytest.raises(HTTPException) as excinfo:
        require_capability_for_user("u1", Capability.STANDARDIZE, FakeSettings())
    assert excinfo.value.status_code == 403
    assert "plan activo" in excinfo.value.detail
    assert "Planes" in excinfo.value.detail


# ── P0.6: precisión numérica conservada ──────────────────────────────────────


def test_precision_numerica_no_se_trunca():
    assert format_number(0.0049) == "0.0049"
    assert format_number(1.23456) == "1.23456"
    assert format_number(1234.56) == "1234.56"
    assert format_number(850000.0) == "850000"


# ── P0.7: la hora se conserva (y la medianoche de Excel no) ──────────────────


def test_hora_se_conserva_en_estandarizacion():
    df = pd.DataFrame({"Fecha": ["15/07/2026 08:15", "15/07/2026 18:40"], "Ventas": ["1", "2"]})
    out, _ = standardize_dataframe(df)
    valores = list(out["Fecha"])
    assert "15/07/2026 08:15" in valores
    assert "15/07/2026 18:40" in valores  # dos eventos del día siguen distintos


def test_medianoche_de_excel_no_se_conserva():
    df = pd.DataFrame({"Fecha": ["2026-05-01 00:00:00", "2026-05-02 00:00:00"], "Ventas": ["1", "2"]})
    out, _ = standardize_dataframe(df)
    assert list(out["Fecha"]) == ["01/05/2026", "02/05/2026"]


# ── P0.3: porcentajes sobre ventas brutas positivas ──────────────────────────


def test_porcentajes_con_devoluciones_no_explotan():
    csv = (
        "Fecha;Producto;Ventas\n"
        "05/01/2026;A;100000\n"
        "06/01/2026;B;-90000\n"  # neto 10.000: antes A mostraba "1.000%"
    )
    result, _ = _run(csv)
    m = compute_metrics(result["_df_limpio"])
    productos = {p["nombre"]: p for p in m["top_productos"]}
    assert productos["A"]["porcentaje"] == 100.0  # sobre brutos positivos
    assert productos["B"]["porcentaje"] == -90.0
    assert m["kpis"]["ingresos_totales"]["valor"] == 10000.0  # el neto no cambia


# ── P0.4: mes incompleto comparado por días equivalentes ─────────────────────


def test_mes_parcial_compara_dias_equivalentes():
    filas = [f"{d:02d}/06/2026;1000" for d in range(1, 31)]  # junio completo: 30.000
    filas += [f"{d:02d}/07/2026;1000" for d in range(1, 16)]  # julio hasta el 15: 15.000
    csv = "Fecha;Ventas\n" + "\n".join(filas)
    result, _ = _run(csv)
    m = compute_metrics(result["_df_limpio"], date_from="2026-07-01", date_to="2026-07-31")
    kpis = m["kpis"]
    assert kpis["ingresos_totales"]["valor"] == 15000.0
    # vs jun 1–15 (15.000): 0% — con el mes completo habría mostrado −50% falso
    assert kpis["ingresos_totales"]["variacion_pct"] == 0.0
    assert m["periodo"]["mes_parcial"] is True
    assert any("incompleto" in a for a in m["advertencias"])


def test_mes_completo_sigue_comparando_mes_completo():
    filas = [f"{d:02d}/06/2026;1000" for d in range(1, 31)]
    filas += [f"{d:02d}/07/2026;2000" for d in range(1, 32)]
    csv = "Fecha;Ventas\n" + "\n".join(filas)
    result, _ = _run(csv)
    m = compute_metrics(result["_df_limpio"], date_from="2026-07-01", date_to="2026-07-31")
    assert m["periodo"]["mes_parcial"] is False
    assert m["kpis"]["ingresos_totales"]["variacion_pct"] == round(
        (62000 - 30000) / 30000 * 100, 1
    )


# ── P0.5: monedas que el parser acepta ahora se DETECTAN ─────────────────────


def test_uf_y_otras_monedas_detectadas():
    moneda, aviso = detect_currency(pd.Series(["UF 100", "UF 250"]))
    assert moneda == "UF"
    assert aviso is not None  # "sin conversión a pesos chilenos"
    moneda2, aviso2 = detect_currency(pd.Series(["ARS 25.000", "CLP 800"]))
    assert aviso2 is not None and "más de una moneda" in aviso2


# ── Utilidad mensual sin filas pareadas → None, jamás $0 ─────────────────────


def test_mes_sin_costos_pareados_no_inventa_utilidad_cero():
    csv = (
        "Fecha;Ventas;Costo\n"
        "05/01/2026;100000;60000\n"
        "05/02/2026;80000;\n"  # febrero: ventas sin ningún costo
    )
    result, _ = _run(csv)
    m = compute_metrics(result["_df_limpio"])
    feb = next(e for e in m["evolucion_mensual"] if e["mes"] == "2026-02")
    assert feb["utilidad"] is None
    assert feb["margen_pareado_pct"] is None
    assert feb["cobertura_costos_pct"] == 0.0


# ── "Total Energies" con solo dos columnas se conserva ───────────────────────


def test_total_energies_dos_columnas_se_conserva():
    csv = "Cliente;Ventas\nACME;100\nTotal Energies;200\n"
    df, report = load_dataframe_with_report("t.csv", csv.encode())
    assert len(df) == 2
    assert report["filas_totales_omitidas"] == 0


def test_fila_total_exacta_si_se_omite():
    csv = "Cliente;Ventas\nACME;100\nBeta;200\nTotal;300\n"
    df, report = load_dataframe_with_report("t.csv", csv.encode())
    assert len(df) == 2


# ── P0.1: la calidad no "mejora" con nulos preservados ───────────────────────


def test_calidad_no_sube_por_nulos_preservados():
    csv = "Fecha;Nota;Ventas\n" + "\n".join(
        f"{d:02d}/01/2026;;{d * 100}" for d in range(1, 21)
    )
    result, _ = _run(csv)
    antes = result["resumen"]["calidad_antes"]
    despues = result["resumen"]["calidad_despues"]
    # Los nulos siguen ahí: la calidad no puede saltar a 100 sin corregir nada
    assert despues < 100.0
    assert abs(despues - antes) < 10.0


# ── CSV con comas entrecomilladas ────────────────────────────────────────────


def test_separador_ignora_comas_entre_comillas():
    sample = 'cliente,descripcion,monto\nACME,"Servicio, instalación y soporte",100000\nBeta,"Retiro, embalaje",50000\n'
    assert _detect_separator(sample) == ","
    df, _ = load_dataframe_with_report("q.csv", sample.encode())
    assert len(df.columns) == 3
    assert len(df) == 2


# ── Conteo real de fusiones fuzzy (antes: capado a 5 ejemplos) ───────────────


def test_fusiones_fuzzy_cuenta_real():
    ciudades = [
        "Santiago", "Valparaiso", "Concepcion", "Antofagasta",
        "Temuco", "Rancagua", "Iquique", "Talca",
    ]
    typos = [
        "Santigo", "Valparasio", "Concepcio", "Antofagast",
        "Temucco", "Rancagau", "Iquiqe", "Talcaa",
    ]  # 8 typos: más que los 5 ejemplos que guarda el reporte
    valores = [c for c in ciudades for _ in range(6)] + typos
    df = pd.DataFrame({"Sucursal": valores, "Ventas": ["100"] * len(valores)})
    out, report = standardize_dataframe(df)
    fusiones = report["fusiones_texto"]
    assert fusiones["total"] >= 8  # el conteo ya no está capado por los ejemplos
    assert len(fusiones["ejemplos"]) <= 5
