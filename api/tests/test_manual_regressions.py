"""Regresiones de las pruebas manuales de estado, perfiles y exportación."""

import io

import openpyxl
import pandas as pd

from app.engine.business import _attribute_consistency
from app.engine.mapping import detect_column_roles
from app.engine.metrics import CurrencyDetection, compute_metrics
from app.engine.standardize import parse_date, standardize_dataframe
from app.routes import pipeline


def test_sku_name_conflict_is_detected_against_master():
    """SKU que existe en el maestro pero con nombre distinto = conflicto (no
    huérfano). Un SKU inexistente no cuenta aquí (eso es huérfano)."""
    ventas = pd.DataFrame(
        {
            "SKU_Producto": ["SKU-1", "SKU-2", "SKU-3", "SKU-9"],
            "Producto": ["Lápiz Azul", "TÓNER negro ", "Producto Equivocado", "X"],
        }
    )
    maestro = pd.DataFrame(
        {
            "SKU_Producto": ["SKU-1", "SKU-2", "SKU-3"],
            "Producto": ["Lapiz azul", "Toner Negro", "Guante Nitrilo"],
        }
    )
    res = _attribute_consistency(
        ventas, "SKU_Producto", "Producto", maestro, "SKU_Producto", "Producto", "V-P"
    )
    # SKU-1 y SKU-2 coinciden (ignorando acentos/mayúsculas/espacios); SKU-3 no.
    # SKU-9 no está en el maestro: no se revisa (no infla el conflicto).
    assert res["filas"] == 3
    assert res["huerfanas"] == 1
    assert res["validas"] == 2


def test_year_month_values_parse_to_first_of_month():
    """Meses como '2025-10' u '08/2025' (Mes Vigencia, Mes de metas) deben
    quedar como fecha (día 1), no como 'fecha no interpretable'."""
    assert parse_date("2025-10") == pd.Timestamp(2025, 10, 1)
    assert parse_date("2025-2") == pd.Timestamp(2025, 2, 1)
    assert parse_date("08/2025") == pd.Timestamp(2025, 8, 1)
    assert parse_date("12.2024") == pd.Timestamp(2024, 12, 1)
    # Mes fuera de rango o sin año de 4 dígitos no se fuerza a fecha.
    assert parse_date("2025-13") is None
    assert parse_date("10/25") is None
    # Las fechas completas de siempre siguen intactas.
    assert parse_date("15/02/2025") == pd.Timestamp(2025, 2, 15)
    assert parse_date("2026-05-01") == pd.Timestamp(2026, 5, 1)


def test_flete_total_excluded_and_zero_iva_not_flagged_as_mismatch():
    """Regresión (frente 1, commit 04c6467) sin cobertura dedicada según la
    auditoría externa: "Flete Total" contiene la subcadena "total" pero es un
    componente de línea, no el total del documento -- no debe validarse
    contra neto+IVA (generaba ~300 falsos positivos). Un IVA en cero (exento,
    ej. Remuneraciones) tampoco es un error de tasa -- solo se marca un IVA
    PRESENTE que no cuadra (generaba ~178 falsos positivos)."""
    rows = []
    for i in range(15):
        monto = 1000 + i
        iva = round(monto * 0.19)
        rows.append({
            "Monto": monto, "IVA": iva,
            # "Flete Total" antes de "Total Documento" a propósito: si el
            # filtro por palabra clave no excluyera "flete", el primer
            # candidato encontrado por orden de columnas sería el equivocado.
            "Flete Total": 500,
            "Total Documento": monto + iva,
        })
    # Filas exentas: IVA en cero, no es un error de tasa.
    for i in range(3):
        monto = 2000 + i
        rows.append({
            "Monto": monto, "IVA": 0,
            "Flete Total": 500,
            "Total Documento": monto,
        })
    # Filas con un error real de IVA (muy distinto de la tasa del 19%).
    for i in range(2):
        monto = 3000 + i
        rows.append({
            "Monto": monto, "IVA": 1,
            "Flete Total": 500,
            "Total Documento": monto + 1,
        })
    df = pd.DataFrame(rows)
    result = {
        "column_types": {col: "numero" for col in df.columns},
        "mapeo": {"monto": "Monto"},
        "carga": {},
    }

    yellow, _red, _observations = pipeline._export_annotations(result, df)

    # "Flete Total" jamás se valida como el total del documento.
    assert not any(col == "Flete Total" for (_row, col) in yellow)
    # Las 3 filas exentas (índices 15-17) no se marcan como error de tasa.
    for row_idx in range(15, 18):
        assert (row_idx, "IVA") not in yellow
    # Las 2 filas con IVA realmente distinto de la tasa SÍ se marcan.
    for row_idx in range(18, 20):
        assert (row_idx, "IVA") in yellow


def test_channel_equivalences_are_role_scoped_and_auditable():
    frame = pd.DataFrame(
        {
            "Canal": ["Tda", "Tienda", "Online", "On line", "WEB", "Market place"],
            "Producto": ["WEB", "Tda", "Online", "On line", "Marketplace", "Market place"],
        }
    )

    standardized, report = standardize_dataframe(
        frame, mapping={"canal": "Canal", "producto": "Producto"}
    )

    assert standardized["Canal"].tolist() == [
        "Tienda", "Tienda", "Online", "Online", "Online", "Marketplace"
    ]
    # La normalización genérica de espacios puede unir On line/Online, pero
    # las equivalencias semánticas WEB→Online y Tda→Tienda son solo de Canal.
    assert standardized["Producto"].iloc[0] == "WEB"
    assert standardized["Producto"].iloc[1] == "Tda"
    assert report["cambios"]["equivalencias_canal"] == 4


def test_date_range_reports_undated_rows_and_amount_without_losing_global_total():
    frame = pd.DataFrame(
        {"Fecha": ["01/01/2025", "", "15/02/2025"], "Monto": [100, 250, 300]}
    )
    complete = compute_metrics(frame, {"fecha": "Fecha", "monto": "Monto"})
    filtered = compute_metrics(
        frame,
        {"fecha": "Fecha", "monto": "Monto"},
        date_from="2025-01-01",
        date_to="2025-01-31",
    )

    assert complete["kpis"]["ingresos_totales"]["valor"] == 650
    assert complete["periodo"]["sin_fecha"] == {
        "filas": 1, "monto": 250.0, "excluidas_por_filtro": False
    }
    assert filtered["kpis"]["ingresos_totales"]["valor"] == 100
    assert filtered["periodo"]["sin_fecha"]["excluidas_por_filtro"] is True
    assert any("250" in warning and "excluye" in warning for warning in filtered["advertencias"])


def test_campaign_inventory_and_generic_profiles_do_not_invent_sales():
    campaigns = pd.DataFrame(
        {
            "ID_Campana": ["A", "B"],
            "Plataforma": ["Meta", "Google"],
            "Inversion": [100, 300],
            "Impresiones": [1000, 3000],
            "Clics": [10, 30],
            "Estado": ["Activa", "Pausada"],
        }
    )
    campaign_metrics = compute_metrics(campaigns)
    assert campaign_metrics["tipo_analisis"] == "campanas_marketing"
    assert campaign_metrics["analisis_campanas"]["ctr_pct"] == 1.0
    assert campaign_metrics["analisis_campanas"]["cpc"] == 10.0
    assert campaign_metrics["kpis"]["ingresos_totales"] is None
    assert "cliente" not in detect_column_roles(list(campaigns.columns))

    inventory = pd.DataFrame(
        {
            "ID_Producto": ["P1", "P2"],
            "ID_Sucursal": ["S1", "S1"],
            "Stock": [5, 2],
            "Stock_Minimo": [3, 4],
            "Ultima_Actualizacion": ["01/01/2025", "01/01/2025"],
        }
    )
    inventory_metrics = compute_metrics(
        inventory, {"producto": "ID_Producto", "sucursal": "ID_Sucursal"}
    )
    assert inventory_metrics["tipo_analisis"] == "inventario"
    assert inventory_metrics["analisis_inventario"]["stock_total"] == 7
    assert inventory_metrics["analisis_inventario"]["bajo_minimo"] == 1
    assert inventory_metrics["kpis"]["ingresos_totales"] is None

    generic = compute_metrics(pd.DataFrame({"Paso": ["A", "B"], "Detalle": ["x", "y"]}))
    assert generic["tipo_analisis"] == "generico"
    assert generic["kpis"]["transacciones"] is None
    assert generic["kpis"]["ingresos_totales"] is None


def test_clean_response_exposes_typed_currency_without_internal_dataframe():
    detection = CurrencyDetection(
        "USD", ("USD",), {"USD": 2}, False, None, {"monto": {"USD": 2}}
    )
    response = pipeline._public_clean_response(
        {"_moneda": detection, "_df_limpio": pd.DataFrame(), "resumen": {}},
        "ventas.xlsx",
    )
    assert response["moneda"] == "USD"
    assert response["moneda_detalle"]["detectadas"] == ["USD"]
    assert "_df_limpio" not in response


def test_identical_export_requests_reuse_one_job(monkeypatch):
    pipeline._EXPORT_CACHE.clear()
    pipeline._EXPORT_INFLIGHT.clear()
    calls = 0

    def fake_export(*_args):
        nonlocal calls
        calls += 1
        return b"xlsx", "out.xlsx", "application/test"

    monkeypatch.setattr(pipeline, "_clean_download_book_uncached_sync", fake_export)
    manifest = {"hojas": [{"nombre": "Ventas", "revision": 4}]}
    first = pipeline._clean_download_book_sync("x.xlsx", b"same", manifest, "xlsx", None, "d1")
    second = pipeline._clean_download_book_sync("x.xlsx", b"same", manifest, "xlsx", None, "d1")
    assert first == second
    assert calls == 1


def test_exported_workbook_requests_formula_recalculation():
    workbook = openpyxl.Workbook()
    pipeline._request_excel_recalculation(workbook)
    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    restored = openpyxl.load_workbook(output, data_only=False)
    assert restored.calculation.calcMode == "auto"
    assert restored.calculation.fullCalcOnLoad is True
    assert restored.calculation.forceFullCalc is True
