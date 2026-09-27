"""Regression checks for document headers and line-item monetary semantics."""

import pytest
import pandas as pd

from app.engine.mapping import detect_column_roles, resolve_mapping
from app.engine.document_model import MATCH_COLUMN, prepare_document_lines
from app.engine.business import analyze_business_workbook


@pytest.mark.parametrize("column", [
    "IDVenta", "id_venta", "IDCompra", "CodigoVenta", "NumeroVenta",
    "EstadoCompra", "EstadoVenta", "TipoGasto", "FechaIngreso", "MedioVenta",
])
def test_document_attributes_never_become_money(column):
    mapping = detect_column_roles([column])
    assert "monto" not in mapping
    assert "costo" not in mapping


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("net", ["NetoLinea_CLP", "Neto_Linea_UF", "Line Net Amount"])
def test_line_net_wins_over_tax_inclusive_total(net, reverse):
    columns = ["IDVenta", "Linea", "IDProducto", "Cantidad", "PrecioUnitarioNeto_CLP",
               "TotalLinea_CLP", "IVA_CLP", net]
    mapping = detect_column_roles(columns[::-1] if reverse else columns)
    assert mapping["monto"] == net
    assert "categoria" not in mapping


def test_category_line_and_explicit_user_overrides_remain_supported():
    assert detect_column_roles(["Linea", "Monto"])["categoria"] == "Linea"
    assert resolve_mapping(["IDVenta"], {"monto": "IDVenta"}) == {"monto": "IDVenta"}


def _frames():
    return {
        "Ventas_T1": pd.DataFrame({
            "IDVenta": [" V1 ", "v1", "V2"],
            "FechaVenta": ["2026-01-02", "2026-01-02", "2026-01-03"],
            "IDCliente": ["C1", "C1", "C2"], "EstadoVenta": ["Pagada", "Pagada", "Anulada"],
        }),
        "Ventas_T2": pd.DataFrame({"IDVenta": ["V3"], "FechaVenta": ["2026-04-02"],
            "IDCliente": ["C2"], "EstadoVenta": ["Pagada"]}),
        "Detalle_T1": pd.DataFrame({"IDVenta": ["V1", "v1", "V2", "NO-EXISTE"],
            "Linea": [1, 2, 1, 1], "IDProducto": ["P1"] * 4, "Cantidad": [2, 3, 1, 10],
            "PrecioUnitarioNeto_CLP": [100] * 4, "DescuentoPct": [0] * 4,
            "NetoLinea_CLP": [200, 300, 100, 1000], "IVA_CLP": [38, 57, 19, 190],
            "TotalLinea_CLP": [238, 357, 119, 1190]}),
        "Detalle_T2": pd.DataFrame({"IDVenta": ["V3"], "Linea": [1], "IDProducto": ["P1"],
            "Cantidad": [4], "PrecioUnitarioNeto_CLP": [100], "DescuentoPct": [0],
            "NetoLinea_CLP": [400], "IVA_CLP": [76], "TotalLinea_CLP": [476]}),
        "Productos": pd.DataFrame({"IDProducto": ["P1"], "Producto": ["Producto"],
            "CostoUnitario_CLP": [50]}),
        "Clientes": pd.DataFrame({"IDCliente": ["C1", "C2"], "NombreCliente": ["Uno", "Dos"]}),
    }


def _analyze(frames, **kwargs):
    mappings = {name: resolve_mapping(list(frame.columns), None) for name, frame in frames.items()}
    return analyze_business_workbook(frames, mappings, {}, **kwargs)


def test_header_detail_join_preserves_grain_periods_and_input_frames():
    frames = _frames()
    originals = {name: frame.copy(deep=True) for name, frame in frames.items()}
    result = _analyze(frames)
    assert result["estado_resultados"]["ventas_observadas"] == 900
    assert result["estado_resultados"]["costo_venta_conocido"] == 450
    assert result["alcance"]["filas_ventas_fisicas"] == 5
    assert result["alcance"]["filas_indicadores"] == 3
    assert result["alcance"]["filas_sin_cabecera_valida"] == 1
    assert result["alcance"]["documentos_repetidos"] == 0
    assert "Ventas_T1" in result["alcance"]["hojas_utilizadas"]
    indicators = {i["id"]: i for c in result["catalogo_indicadores"]["categorias"] for i in c["indicadores"]}
    assert indicators["ticket_promedio_documento"]["valor"] == 450
    assert _analyze(frames, date_from="2026-04-01")["estado_resultados"]["ventas_observadas"] == 400
    assert any(r["id_inexistente"] == 1 for r in result["calidad"]["integridad_referencial"] if "id_inexistente" in r)
    for name, original in originals.items():
        pd.testing.assert_frame_equal(frames[name], original)


def test_conflicting_headers_and_line_attributes_are_not_arbitrarily_linked():
    frames = _frames()
    frames["Ventas_T1"].loc[1, "EstadoVenta"] = "Anulada"
    model = prepare_document_lines(frames, {})
    assert list(model.frames["Detalle_T1"][MATCH_COLUMN]) == [0, 0, 1, 0]
    assert _analyze(frames)["estado_resultados"]["ventas_observadas"] == 400
    frames = _frames()
    frames["Detalle_T2"]["IDCliente"] = "CLIENTE-DISTINTO"
    model = prepare_document_lines(frames, {})
    assert model.frames["Detalle_T2"][MATCH_COLUMN].tolist() == [0]
    assert model.frames["Detalle_T2"]["IDCliente"].tolist() == ["CLIENTE-DISTINTO"]


def test_document_keys_do_not_fuzzy_match_or_drop_leading_zeroes():
    frames = _frames()
    frames["Ventas_T2"]["IDVenta"] = "V03"
    model = prepare_document_lines(frames, {})
    assert model.frames["Detalle_T2"][MATCH_COLUMN].tolist() == [0]


def test_repeated_line_is_flagged_but_never_deleted_without_confirmation():
    frames = _frames()
    frames["Detalle_T2"] = pd.concat([frames["Detalle_T2"]] * 2, ignore_index=True)
    result = _analyze(frames)
    assert result["alcance"]["documentos_repetidos"] == 1
    assert result["alcance"]["filas_adicionales_documento"] == 1
    assert result["estado_resultados"]["ventas_observadas"] == 1300
    assert result["estado_certificacion"] == "blocked"


def test_line_recorded_cost_takes_precedence_over_current_catalogue():
    frames = _frames()
    frames["Detalle_T1"]["CostoUnitario_CLP"] = [20] * 4
    frames["Detalle_T2"]["CostoUnitario_CLP"] = 30
    result = _analyze(frames)
    assert result["estado_resultados"]["costo_venta_conocido"] == 220
    assert result["estado_resultados"]["utilidad_bruta"] == 680
    assert result["calidad"]["costos"]["metodo"] == "documento"
    frames["Detalle_T2"]["CostoUnitario_CLP"] = -10
    result = _analyze(frames)
    assert result["estado_resultados"]["costo_venta_conocido"] == 100
    assert result["estado_resultados"]["ventas_pareadas"] == 500
    assert result["estado_certificacion"] == "blocked"


def test_native_nulls_do_not_make_a_date_column_look_like_text():
    from app.engine.standardize import detect_value_type_confidence
    values = pd.Series([None, float("nan"), pd.NA, "2026-01-03"])
    assert detect_value_type_confidence(values, "FechaVenta")[0] == "fecha"


def test_completely_unmatched_period_does_not_prevent_other_period_analysis():
    frames = _frames()
    frames["Ventas_T1"]["IDVenta"] = ["X1", "X1", "X2"]
    result = _analyze(frames)
    assert result["estado_resultados"]["ventas_observadas"] == 400
    assert result["alcance"]["filas_sin_cabecera_valida"] == 4
    assert result["alcance"]["filas_fecha_invalida"] == 0


def test_append_accepts_missing_values_but_not_incompatible_informed_values():
    from app.engine.multi_sheet import append_compatible_frames
    empty = pd.DataFrame({"Fecha": [None], "Ventas": [100]})
    populated = pd.DataFrame({"Fecha": ["2026-04-01"], "Ventas": [200]})
    combined, _, _ = append_compatible_frames({"A": empty, "B": populated}, {})
    assert len(combined) == 2
    empty["Fecha"] = "not a date"
    with pytest.raises(ValueError, match="tipos incompatibles"):
        append_compatible_frames({"A": empty, "B": populated}, {})


def test_pipeline_generic_graphs_use_header_dates_and_exclude_unmatched_sales():
    from app.routes.pipeline import _metrics_multi_from_processed
    frames = _frames()
    for name in ("Detalle_T1", "Detalle_T2"):
        frames[name]["CostoUnitario_CLP"] = 20
    mappings = {name: resolve_mapping(list(frame.columns), None) for name, frame in frames.items()}
    results = {name: {"resumen": {"calidad_despues": 100}} for name in frames}
    scope = {"mode": "append_join", "sheets": ["Detalle_T1", "Detalle_T2", "Productos"],
        "append_sheets": ["Detalle_T1", "Detalle_T2"], "active_sheet": "Detalle_T1",
        "join": {"left_sheet": "Detalle_T1", "right_sheet": "Productos",
                 "left_keys": ["IDProducto"], "right_keys": ["IDProducto"], "type": "left"}}
    result = _metrics_multi_from_processed("fixture.xlsx", frames, mappings, results, scope, None, None)
    assert result["kpis"]["ingresos_totales"]["valor"] == 900
    assert sum(row["ingresos"] for row in result["evolucion_mensual"]) == 900
    assert result["analisis_negocio"]["estado_resultados"]["ventas_observadas"] == 900
    assert result["analysis_provenance"]["filas_sin_cabecera_valida"] == 1


@pytest.mark.parametrize("currency_mismatch,partial_selection", [(False, False), (True, False), (False, True)])
def test_relationship_detection_retains_document_periods_without_unsafe_catalog_join(
    monkeypatch, currency_mismatch, partial_selection,
):
    from app.routes import pipeline
    from app.engine.metrics import detect_currency

    frames = _frames()
    for name in ("Detalle_T1", "Detalle_T2"):
        frames[name]["CostoUnitario_CLP"] = 20
    frames["Productos"] = pd.concat([frames["Productos"], frames["Productos"].assign(CostoUnitario_CLP=999)], ignore_index=True)
    if currency_mismatch:
        frames["Productos"].rename(columns={"CostoUnitario_CLP": "CostoUnitario_USD"}, inplace=True)
    mappings = {name: resolve_mapping(list(frame.columns), None) for name, frame in frames.items()}
    results = {name: {"resumen": {"calidad_despues": 100}, "_moneda": detect_currency(None, header_hints=tuple(frame.columns))} for name, frame in frames.items()}
    manifest = {"hojas": [{"nombre": name, "procesar": True, "mapping": mappings[name]} for name in frames]}
    monkeypatch.setattr(pipeline, "_processed_manifest_frames", lambda *args: (frames, mappings, results))
    selected = ["Detalle_T1"] if partial_selection else ["Detalle_T1", "Detalle_T2"]
    result = pipeline._relationships_sync("documents.xlsx", b"synthetic", manifest, focus={"sheets": selected})
    if currency_mismatch or partial_selection:
        assert not result.get("business_without_catalog_join")
        return
    assert result["business_without_catalog_join"] is True
    assert result["analysis_scope"]["append_sheets"] == selected
    assert not any(candidate["safe"] for candidate in result["candidates"])
    metrics = result["metrics"]
    assert metrics["analysis_provenance"]["join"]["materializada_en_resumen_generico"] is False
    assert metrics["kpis"]["ingresos_totales"]["valor"] == 900
    assert metrics["analisis_negocio"]["estado_resultados"]["ventas_observadas"] == 900
    assert metrics["analisis_negocio"]["estado_resultados"]["costo_venta_conocido"] == 180
    assert metrics["analisis_negocio"]["alcance"]["filas_indicadores"] == 3
    assert len(frames["Productos"]) == 2
