"""Regresiones de las pruebas manuales de estado, perfiles y exportación."""

import io

import openpyxl
import pandas as pd

from app.engine.mapping import detect_column_roles
from app.engine.metrics import CurrencyDetection, compute_metrics
from app.engine.standardize import standardize_dataframe
from app.routes import pipeline


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
