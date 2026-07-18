"""Regression coverage for intelligent selection, chained analysis and export."""

import io
import os
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

from app.engine.audit import build_audit_dataframe
from app.engine.export import safe_export_dataframe
from app.engine.loader import load_dataframe_with_report
from app.engine.metrics import compute_metrics
from app.engine.multi_sheet import build_analysis_frame, validate_analysis_scope
from app.routes.pipeline import _clean_download_book_sync
from app.routes.pipeline import _cache_key


def _classified_workbook() -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(
            {
                "ID": list(range(1, 9)),
                "Monto": [100, 200, 300, 400, 500, 600, 700, 800],
            }
        ).to_excel(writer, sheet_name="Ventas", index=False)
        pd.DataFrame({"LEEME": ["No modificar"], "Paso": ["Conservar"]}).to_excel(
            writer, sheet_name="LEEME_NO_PROCESAR", index=False
        )
        pd.DataFrame({"Titulo": ["Portada"]}).to_excel(
            writer, sheet_name="Presentacion", index=False
        )
    return output.getvalue()


def test_sheet_classification_is_explainable_and_never_removes_sheets():
    content = _classified_workbook()
    _, report = load_dataframe_with_report("libro.xlsx", content, sheet="Ventas")
    profiles = {item["nombre"]: item for item in report["clasificacion_hojas"]}

    assert list(profiles) == ["Ventas", "LEEME_NO_PROCESAR", "Presentacion"]
    assert profiles["Ventas"]["clasificacion"] == "datos"
    assert profiles["Ventas"]["recomendacion"] == "procesar"
    assert profiles["LEEME_NO_PROCESAR"]["clasificacion"] == "auxiliar"
    assert profiles["LEEME_NO_PROCESAR"]["recomendacion"] == "conservar_sin_procesar"
    assert profiles["Presentacion"]["clasificacion"] == "ambigua"
    assert all(profile["motivos"] for profile in profiles.values())


def test_append_then_join_derives_cost_without_changing_rows_or_income():
    january = pd.DataFrame(
        {"ID_Producto": ["A", "B"], "Cantidad": [2, 1], "Monto": [500, 300]}
    )
    february = pd.DataFrame(
        {"ID_Producto": ["A", "B"], "Cantidad": [1, 3], "Monto": [250, 900]}
    )
    products = pd.DataFrame(
        {"ID_Producto": ["A", "B"], "Producto": ["Uno", "Dos"], "Categoria": ["X", "Y"], "Costo_Unitario": [100, 200]}
    )
    frames = {"Enero": january, "Febrero": february, "Productos": products}
    mappings = {
        "Enero": {"producto": "ID_Producto", "cantidad": "Cantidad", "monto": "Monto"},
        "Febrero": {"producto": "ID_Producto", "cantidad": "Cantidad", "monto": "Monto"},
        "Productos": {"producto": "Producto", "categoria": "Categoria", "costo": "Costo_Unitario"},
    }
    scope = validate_analysis_scope(
        {
            "mode": "append_join",
            "sheets": ["Enero", "Febrero", "Productos"],
            "append_sheets": ["Enero", "Febrero"],
            "active_sheet": "Enero",
            "join": {
                "left_sheet": "Enero",
                "right_sheet": "Productos",
                "left_keys": ["ID_Producto"],
                "right_keys": ["ID_Producto"],
                "type": "left",
            },
        },
        list(frames),
    )

    joined, mapping, provenance = build_analysis_frame(frames, mappings, scope)

    assert len(joined) == 4
    assert joined["Monto"].sum() == 1950
    assert joined["Costo_Venta"].sum() == 1100
    assert joined["Utilidad_Bruta"].sum() == 850
    assert mapping["costo"] == "Costo_Venta"
    assert provenance["join"]["filas_sin_correspondencia"] == 0
    assert provenance["join"]["costo_derivado"]["cobertura_costos_pct"] == 100.0


def test_product_catalog_has_unit_statistics_not_fake_cost_sum():
    frame = pd.DataFrame(
        {
            "Producto": ["A", "B", "C"],
            "Categoria": ["X", "X", "Y"],
            "Marca": ["M1", "M2", "M1"],
            "Costo_Unitario": [50, 80, 120],
            "Precio_Lista": [100, 160, 200],
            "Estado": ["Activo", "Activo", "Inactivo"],
        }
    )
    metrics = compute_metrics(
        frame,
        {"producto": "Producto", "categoria": "Categoria", "costo": "Costo_Unitario", "monto": "Precio_Lista"},
    )

    assert metrics["tipo_analisis"] == "catalogo_productos"
    assert metrics["analisis_productos"]["productos"] == 3
    assert metrics["analisis_productos"]["costos"] == {
        "promedio": 83.33,
        "mediana": 80.0,
        "minimo": 50.0,
        "maximo": 120.0,
    }
    assert metrics["kpis"]["gastos_totales"] is None
    assert metrics["kpis"]["ingresos_totales"] is None


def test_numeric_export_types_only_values_that_parse():
    exported = safe_export_dataframe(
        pd.DataFrame({"Cantidad": ["2", "N/D"], "Monto": ["1.500", "1,234"], "Texto": ["001", "=2+2"]}),
        numeric_columns={"Cantidad", "Monto"},
    )

    assert exported.loc[0, "Cantidad"] == 2
    assert exported.loc[0, "Monto"] == 1500
    assert exported.loc[1, "Cantidad"] == "N/D"
    assert exported.loc[1, "Monto"] == "1,234"
    assert exported.loc[0, "Texto"] == "001"
    assert exported.loc[1, "Texto"] == "'=2+2"


def test_cache_key_includes_dataset_revision_rules_mapping_sheet_and_engine():
    base = _cache_key(
        b"data",
        {"textos": True},
        True,
        {"monto": "Venta"},
        {},
        "Enero",
        False,
        "dataset-1",
        7,
    )
    assert base != _cache_key(
        b"data",
        {"textos": True},
        True,
        {"monto": "Venta"},
        {},
        "Enero",
        False,
        "dataset-1",
        8,
    )
    assert base != _cache_key(
        b"data",
        {"textos": True},
        True,
        {"monto": "Venta"},
        {},
        "Febrero",
        False,
        "dataset-1",
        7,
    )


def test_audit_records_duplicate_even_when_user_keeps_it():
    original = pd.DataFrame({"ID": ["A", "A"], "Monto": ["100", "100"]})
    cleaned = original.copy()
    audit = build_audit_dataframe(
        filename="ventas.csv",
        original=original,
        cleaned=cleaned,
        original_source_rows=[2, 3],
        cleaned_source_rows=[2, 3],
        source_sheet=None,
        column_types={"ID": "texto", "Monto": "numero"},
        column_confidence={"ID": 1.0, "Monto": 1.0},
        mapping={"monto": "Monto"},
        rules={},
        scope=None,
        removed_rows=[],
        detected_duplicate_rows=[{"fila_origen": 3, "motivo": "exacta"}],
        source_sha256="abc",
    )

    kept = audit[audit["accion"] == "duplicado_detectado_y_conservado"]
    assert kept["fila_origen"].tolist() == [3]


def test_single_scope_export_does_not_create_related_sheet():
    content = _classified_workbook()
    names = ["Ventas", "LEEME_NO_PROCESAR", "Presentacion"]
    manifest = {
        "hojas": [
            {
                "nombre": name,
                "procesar": name == "Ventas",
                "rules": {},
                "mapping": {"monto": "Monto"} if name == "Ventas" else {},
                "scope": {},
                "eliminar_duplicados": False,
                "status": "pendiente",
                "error": "",
            }
            for name in names
        ]
    }
    payload, _, _ = _clean_download_book_sync(
        "libro.xlsx",
        content,
        manifest,
        "xlsx",
        {"mode": "single", "sheets": ["Ventas"], "active_sheet": "Ventas"},
    )
    workbook = openpyxl.load_workbook(io.BytesIO(payload), data_only=False)
    assert "Datos_relacionados" not in workbook.sheetnames
    assert workbook["LEEME_NO_PROCESAR"]["A2"].value == "No modificar"


_stress_path = os.getenv("ADSVERIS_STRESS_XLSX")
_small_path = os.getenv("ADSVERIS_SMALL_XLSX")
STRESS_PATH = Path(_stress_path) if _stress_path else None
SMALL_PATH = Path(_small_path) if _small_path else None


@pytest.mark.skipif(
    SMALL_PATH is None or not SMALL_PATH.is_file(),
    reason="Define ADSVERIS_SMALL_XLSX para ejecutar la regresion del libro pequeno",
)
def test_small_workbook_exact_regression():
    from app.engine.standardize import parse_number
    from app.routes.pipeline import _analyze_cached

    content = SMALL_PATH.read_bytes()
    names = ["Ventas_Enero", "Ventas_Febrero"]
    before = [
        _analyze_cached(SMALL_PATH.name, content, None, True, sheet=name, eliminar_duplicados=False)
        for name in names
    ]
    after = [
        _analyze_cached(SMALL_PATH.name, content, None, True, sheet=name, eliminar_duplicados=True)
        for name in names
    ]

    def amount(results):
        return sum(
            float(result["_df_limpio"][result["mapeo"]["monto"]].map(parse_number).dropna().sum())
            for result in results
        )

    assert sum(len(result["_df_limpio"]) for result in before) == 24
    assert amount(before) == 5_789_480
    assert sum(len(result["_df_limpio"]) for result in after) == 23
    assert amount(after) == 5_699_510


@pytest.mark.skipif(
    STRESS_PATH is None or not STRESS_PATH.is_file(),
    reason="Define ADSVERIS_STRESS_XLSX para ejecutar la regresion del libro de estres",
)
def test_stress_workbook_verifiable_regressions():
    from app.routes.pipeline import _analyze_cached

    content = STRESS_PATH.read_bytes()
    names = ["Ventas_Ene_Abr_2025", "Ventas_May_Ago_2025", "Ventas_Sep_Dic_2025"]
    before = [
        _analyze_cached(STRESS_PATH.name, content, None, True, sheet=name, eliminar_duplicados=False)
        for name in names
    ]
    results = [
        _analyze_cached(STRESS_PATH.name, content, None, True, sheet=name, eliminar_duplicados=True)
        for name in names
    ]
    assert sum(result["resumen"]["filas_antes"] for result in before) == 5505
    assert sum(result["problemas"]["duplicados"] for result in results) == 75
    assert sum(result["resumen"]["filas_despues"] for result in results) == 5430
    from app.engine.standardize import parse_number
    assert sum(result["_df_limpio"][result["mapeo"]["monto"]].map(parse_number).notna().sum() for result in before) == 5302
    assert sum(result["_df_limpio"][result["mapeo"]["monto"]].map(parse_number).notna().sum() for result in results) == 5233


@pytest.mark.skipif(
    STRESS_PATH is None or not STRESS_PATH.is_file(),
    reason="Define ADSVERIS_STRESS_XLSX para ejecutar la regresion del libro de estres",
)
def test_stress_relationship_allow_and_block_matrix():
    from app.engine.multi_sheet import detect_relationships
    from app.routes.pipeline import _analyze_cached

    content = STRESS_PATH.read_bytes()
    names = [
        "Ventas_Ene_Abr_2025",
        "Productos",
        "Clientes",
        "Sucursales",
        "Inventario_Prod_Sucursal",
        "Promociones",
    ]
    results = {
        name: _analyze_cached(STRESS_PATH.name, content, None, True, sheet=name)
        for name in names
    }
    candidates = detect_relationships(
        {name: result["_df_limpio"] for name, result in results.items()},
        {name: result["mapeo"] for name, result in results.items()},
    )
    safe = {
        (item["left_sheet"], item["right_sheet"], tuple(item["left_keys"]))
        for item in candidates
        if item["safe"]
    }
    assert ("Ventas_Ene_Abr_2025", "Productos", ("ID_Producto",)) in safe
    assert ("Ventas_Ene_Abr_2025", "Clientes", ("ID_Cliente",)) in safe
    assert ("Ventas_Ene_Abr_2025", "Sucursales", ("ID_Sucursal",)) in safe
    assert (
        "Ventas_Ene_Abr_2025",
        "Inventario_Prod_Sucursal",
        ("ID_Producto", "ID_Sucursal"),
    ) in safe
    promotions = [
        item
        for item in candidates
        if {item["left_sheet"], item["right_sheet"]}
        == {"Ventas_Ene_Abr_2025", "Promociones"}
    ]
    assert promotions and not any(item["safe"] for item in promotions)


@pytest.mark.skipif(
    STRESS_PATH is None or not STRESS_PATH.is_file(),
    reason="Define ADSVERIS_STRESS_XLSX para ejecutar la regresion del libro de estres",
)
@pytest.mark.xfail(
    strict=True,
    reason="86 ambiguous Monto='1,234' cells replaced their originals; the control total cannot be reconstructed without inventing data",
)
def test_stress_control_amount_after_duplicates_is_reconstructible():
    from app.engine.standardize import parse_number
    from app.routes.pipeline import _analyze_cached

    content = STRESS_PATH.read_bytes()
    names = ["Ventas_Ene_Abr_2025", "Ventas_May_Ago_2025", "Ventas_Sep_Dic_2025"]
    before_total = 0.0
    after_total = 0.0
    for name in names:
        before = _analyze_cached(STRESS_PATH.name, content, None, True, sheet=name, eliminar_duplicados=False)
        result = _analyze_cached(STRESS_PATH.name, content, None, True, sheet=name, eliminar_duplicados=True)
        before_total += float(before["_df_limpio"][before["mapeo"]["monto"]].map(parse_number).dropna().sum())
        after_total += float(result["_df_limpio"][result["mapeo"]["monto"]].map(parse_number).dropna().sum())
    assert before_total == 3_278_490_880
    assert after_total == 3_243_120_100
