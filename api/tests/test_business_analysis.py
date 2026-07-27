"""Regression tests for the safe multi-sheet business model."""

import pandas as pd
import pytest
from fastapi import HTTPException
from types import SimpleNamespace

from app.engine.business import analyze_business_workbook, classify_business_sheets
from app.routes.pipeline import _validate_business_filters


def _sales_mapping() -> dict[str, dict[str, str]]:
    return {
        "Ventas_2026": {
            "fecha": "Fecha Venta",
            "monto": "Monto Venta",
            "cantidad": "Cantidad",
            "producto": "SKU Producto",
            "cliente": "ID Cliente",
        }
    }


def test_business_analysis_excludes_totals_and_cancelled_rows_and_uses_asof_cost():
    frames = {
        "Ventas_2026": pd.DataFrame(
            [
                {
                    "Fecha Venta": "01/01/2026",
                    "ID Documento": "D1",
                    "SKU Producto": "A",
                    "Cantidad": "2",
                    "Monto Venta": "200",
                    "Estado": "Vigente",
                    "ID Cliente": "C1",
                },
                {
                    "Fecha Venta": "02/01/2026",
                    "ID Documento": "D2",
                    "SKU Producto": "B",
                    "Cantidad": "1",
                    "Monto Venta": "150",
                    "Estado": "Anulado",
                    "ID Cliente": "C2",
                },
                {
                    "Fecha Venta": "",
                    "ID Documento": "TOTAL",
                    "SKU Producto": "",
                    "Cantidad": "3",
                    "Monto Venta": "350",
                    "Estado": "",
                    "ID Cliente": "",
                },
            ]
        ),
        "Historial_Costos": pd.DataFrame(
            [
                {"SKU Producto": "A", "Fecha Vigencia": "01/01/2025", "Costo Unitario": "40"},
                {"SKU Producto": "A", "Fecha Vigencia": "01/02/2026", "Costo Unitario": "70"},
            ]
        ),
        "Costos_Productos": pd.DataFrame(
            [{"SKU Producto": "A", "Costo Unitario": "90"}]
        ),
        "Gastos_Operacionales": pd.DataFrame(
            [{"Fecha Gasto": "15/01/2026", "Monto Neto": "30", "Tipo Gasto": "Fijo", "Estado": "Pagado"}]
        ),
        "Inventario": pd.DataFrame(
            [{"SKU Producto": "A", "Valor Inventario": "500"}]
        ),
        "Parametros": pd.DataFrame([{"Clave": "IVA", "Valor": "19"}]),
    }

    result = analyze_business_workbook(frames, _sales_mapping(), {})

    assert result is not None
    assert result["alcance"]["filas_ventas_fisicas"] == 3
    assert result["alcance"]["filas_totales_estructurales"] == 1
    assert result["alcance"]["filas_anuladas"] == 1
    assert result["alcance"]["filas_indicadores"] == 1
    assert result["estado_resultados"]["ventas_observadas"] == 200
    # 2 unidades × costo histórico vigente de 40; nunca el costo actual de 90.
    assert result["estado_resultados"]["costo_venta_conocido"] == 80
    assert result["estado_resultados"]["utilidad_bruta"] == 120
    assert result["estado_resultados"]["resultado_operacional"] == 90
    assert "Parametros" not in result["alcance"]["hojas_utilizadas"]


def test_business_analysis_detects_total_footer_with_native_null_cells():
    frames = {
        "Ventas_2026": pd.DataFrame(
            [
                {
                    "Fecha Venta": "01/01/2026",
                    "ID Venta": "V1",
                    "Monto Venta": 200,
                    "Estado": "Vigente",
                },
                {
                    "Fecha Venta": pd.NA,
                    "ID Venta": "TOTAL",
                    "Monto Venta": 200,
                    "Estado": pd.NA,
                },
            ]
        )
    }

    result = analyze_business_workbook(frames, _sales_mapping(), {})

    assert result is not None
    assert result["alcance"]["filas_totales_estructurales"] == 1
    assert result["estado_resultados"]["ventas_observadas"] == 200


def test_operating_expenses_use_net_amount_and_exclude_invalid_dates():
    frames = {
        "Ventas_2026": pd.DataFrame(
            [
                {
                    "Fecha Venta": "01/01/2026",
                    "ID Documento": "D1",
                    "SKU Producto": "A",
                    "Cantidad": "1",
                    "Monto Venta": "200",
                    "Estado": "Vigente",
                },
                {
                    "Fecha Venta": "31/02/2026",
                    "ID Documento": "D2",
                    "SKU Producto": "A",
                    "Cantidad": "1",
                    "Monto Venta": "100",
                    "Estado": "Vigente",
                },
            ]
        ),
        "Costos_Productos": pd.DataFrame(
            [{"SKU Producto": "A", "Costo Unitario": "40"}]
        ),
        "Gastos_Operacionales": pd.DataFrame(
            [
                {
                    "Fecha Gasto": "15/01/2026",
                    "Monto Neto": "50",
                    "IVA": "9.5",
                    "Total Gasto": "59.5",
                    "Tipo Gasto": "Fijo",
                    "Estado": "Pagado",
                },
                {
                    "Fecha Gasto": "31/02/2026",
                    "Monto Neto": "100",
                    "IVA": "19",
                    "Total Gasto": "119",
                    "Tipo Gasto": "Fijo",
                    "Estado": "Pagado",
                },
            ]
        ),
    }

    result = analyze_business_workbook(frames, _sales_mapping(), {})

    assert result is not None
    statement = result["estado_resultados"]
    # Both sales remain in the global observed result, including the sale whose
    # date needs correction. The invalid-dated expense cannot be assigned to a
    # month and therefore stays out of the operating result.
    assert statement["utilidad_bruta"] == 220
    assert statement["gastos_operacionales"] == 50
    assert statement["base_gastos_operacionales"] == "monto_neto"
    assert statement["iva_gastos_excluido"] == 9.5
    assert statement["filas_gastos"] == 1
    assert statement["resultado_operacional"] == 170


def test_declared_sales_period_excludes_invalid_and_out_of_period_rows():
    frames = {
        "Parametros": pd.DataFrame(
            [
                {
                    "Parámetro": "Periodo ventas",
                    "Valor": "01-01-2026 a 30-06-2026",
                }
            ]
        ),
        "Ventas_2026": pd.DataFrame(
            [
                {
                    "Fecha Venta": "15/06/2026",
                    "ID Documento": "D1",
                    "SKU Producto": "A",
                    "Cantidad": "1",
                    "Monto Venta": "200",
                    "Estado": "Vigente",
                },
                {
                    "Fecha Venta": "15/08/2026",
                    "ID Documento": "D2",
                    "SKU Producto": "A",
                    "Cantidad": "1",
                    "Monto Venta": "300",
                    "Estado": "Vigente",
                },
                {
                    "Fecha Venta": "31/02/2026",
                    "ID Documento": "D3",
                    "SKU Producto": "A",
                    "Cantidad": "1",
                    "Monto Venta": "400",
                    "Estado": "Vigente",
                },
            ]
        ),
        "Costos_Productos": pd.DataFrame(
            [{"SKU Producto": "A", "Costo Unitario": "40"}]
        ),
        "Gastos_Operacionales": pd.DataFrame(
            [
                {
                    "Fecha Gasto": "20/06/2026",
                    "Monto Neto": "50",
                    "IVA": "9.5",
                    "Total Gasto": "59.5",
                    "Estado": "Pagado",
                },
                {
                    "Fecha Gasto": "20/08/2026",
                    "Monto Neto": "70",
                    "IVA": "13.3",
                    "Total Gasto": "83.3",
                    "Estado": "Pagado",
                },
            ]
        ),
    }

    result = analyze_business_workbook(frames, _sales_mapping(), {})

    assert result is not None
    assert result["alcance"]["periodo_declarado"] == {
        "desde": "2026-01-01",
        "hasta": "2026-06-30",
    }
    # La fila sin fecha permanece en el total global, pero no se asigna a un
    # mes ni a un costo por vigencia. La fila válida fuera del periodo sí sale.
    assert result["alcance"]["filas_indicadores"] == 2
    assert result["alcance"]["filas_fecha_invalida"] == 1
    assert result["alcance"]["filas_fuera_periodo_declarado"] == 1
    assert result["estado_resultados"]["ventas_observadas"] == 600
    assert result["estado_resultados"]["gastos_operacionales"] == 50
    assert [row["mes"] for row in result["evolucion"]] == ["2026-06"]


def test_products_sheet_without_costo_in_its_name_is_still_used_as_cost_source():
    """Regresión QA: una PyME chica suele tener un solo "Productos" con ID,
    categoria y Costo_Unitario en la misma hoja, sin nombrarla "Costos_...".
    classify_business_sheets la clasificaba como "productos" (por el nombre
    de la hoja) y el motor nunca la usaba como fuente de costo, aunque traía
    un costo unitario real por SKU -- la cobertura de costos quedaba en 0%
    pese a que el cruce por ID_Producto era perfecto."""
    frames = {
        "Ventas": pd.DataFrame(
            [
                {"ID_Producto": "P-001", "Cantidad": "2", "Monto": "200", "Fecha": "01/01/2026"},
                {"ID_Producto": "P-002", "Cantidad": "1", "Monto": "150", "Fecha": "02/01/2026"},
            ]
        ),
        "Productos": pd.DataFrame(
            [
                {"ID_Producto": "P-001", "Producto": "Audifonos", "Costo_Unitario": "40"},
                {"ID_Producto": "P-002", "Producto": "Mouse", "Costo_Unitario": "70"},
            ]
        ),
    }
    mapping = {
        "Ventas": {
            "fecha": "Fecha",
            "monto": "Monto",
            "cantidad": "Cantidad",
            "producto": "ID_Producto",
        }
    }

    result = analyze_business_workbook(frames, mapping, {})

    assert result is not None
    assert result["alcance"]["hoja_costos"] == "Productos"
    assert result["estado_resultados"]["cobertura_costos_pct"] == 100
    # 2×40 + 1×70
    assert result["estado_resultados"]["costo_venta_conocido"] == 150
    assert result["estado_resultados"]["utilidad_bruta"] == 200


def test_business_filters_recalculate_sales_cost_and_groups_without_allocating_expenses():
    frames = {
        "Ventas_2026": pd.DataFrame(
            [
                {
                    "Fecha Venta": "01/01/2026", "ID Documento": "D1",
                    "SKU Producto": "A", "Cantidad": "1", "Monto Venta": "100",
                    "ID Sucursal": "S1", "ID Vendedor": "V1",
                    "Canal": "Online", "Estado": "Completada",
                },
                {
                    "Fecha Venta": "02/01/2026", "ID Documento": "D2",
                    "SKU Producto": "B", "Cantidad": "2", "Monto Venta": "300",
                    "ID Sucursal": "S2", "ID Vendedor": "V2",
                    "Canal": "Tienda", "Estado": "Completada",
                },
            ]
        ),
        "Productos": pd.DataFrame(
            [
                {"SKU Producto": "A", "Producto": "Arroz", "Categoria": "Alimentos"},
                {"SKU Producto": "B", "Producto": "Mouse", "Categoria": "Tecnología"},
            ]
        ),
        "Costos_Productos": pd.DataFrame(
            [
                {"SKU Producto": "A", "Costo Unitario": "40"},
                {"SKU Producto": "B", "Costo Unitario": "60"},
            ]
        ),
        "Sucursales": pd.DataFrame(
            [
                {"ID Sucursal": "S1", "Nombre Sucursal": "Centro", "Comuna": "Santiago"},
                {"ID Sucursal": "S2", "Nombre Sucursal": "Norte", "Comuna": "Renca"},
            ]
        ),
        "Vendedores": pd.DataFrame(
            [
                {"ID Vendedor": "V1", "Nombre Vendedor": "Ana"},
                {"ID Vendedor": "V2", "Nombre Vendedor": "Luis"},
            ]
        ),
        "Gastos_Operacionales": pd.DataFrame(
            [{"Fecha Gasto": "02/01/2026", "Monto Neto": "50", "Tipo Gasto": "Fijo"}]
        ),
    }
    mappings = {
        "Ventas_2026": {
            "fecha": "Fecha Venta", "monto": "Monto Venta",
            "cantidad": "Cantidad", "producto": "SKU Producto",
            "sucursal": "ID Sucursal", "vendedor": "ID Vendedor", "canal": "Canal",
        }
    }

    full = analyze_business_workbook(frames, mappings, {})
    filtered = analyze_business_workbook(
        frames,
        mappings,
        {},
        filters={"sucursal": "Centro", "categoria": "Alimentos", "vendedor": "Ana"},
    )

    assert full is not None and filtered is not None
    assert full["filtros"]["disponibles"]["sucursal"] == ["Centro", "Norte"]
    assert full["filtros"]["disponibles"]["categoria"] == ["Alimentos", "Tecnología"]
    assert full["filtros"]["disponibles"]["producto"] == ["Arroz", "Mouse"]
    assert filtered["filtros"]["aplicados"] == {
        "sucursal": "Centro", "categoria": "Alimentos", "vendedor": "Ana",
    }
    assert filtered["alcance"]["filas_ventas_sin_filtros"] == 2
    assert filtered["alcance"]["filas_ventas_fisicas"] == 1
    assert filtered["estado_resultados"]["ventas_observadas"] == 100
    assert filtered["estado_resultados"]["costo_venta_conocido"] == 40
    assert filtered["estado_resultados"]["utilidad_bruta"] == 60
    # El gasto no trae sucursal/categoría/vendedor y no se distribuye a ojo.
    assert filtered["estado_resultados"]["gastos_operacionales"] is None
    assert filtered["estado_resultados"]["resultado_operacional"] is None
    assert [row["nombre"] for row in filtered["agrupaciones"]["productos"]] == ["Arroz"]


def test_business_filter_payload_is_bounded_and_rejects_unknown_dimensions():
    assert _validate_business_filters({"sucursal": " Centro ", "canal": ""}) == {
        "sucursal": "Centro",
    }
    with pytest.raises(HTTPException) as invalid_shape:
        _validate_business_filters(["Centro"])  # type: ignore[arg-type]
    assert invalid_shape.value.status_code == 422
    with pytest.raises(HTTPException) as unknown:
        _validate_business_filters({"cuenta_bancaria": "Principal"})
    assert unknown.value.status_code == 422


def test_document_duplicates_split_into_identical_conflict_and_observation_only():
    """Regresión QA (auditoría externa): un ID de documento repetido debe
    clasificarse en exactamente una de tres categorías -- conflicto real de
    negocio, copia idéntica, o solo difiere en una columna Observación.* --
    expuestas por separado. Antes solo se exponía el total agregado de
    repetidos y de conflictivos, mezclando copias idénticas con diferencias
    de Observación dentro del mismo resto sin desglosar."""
    frames = {
        "Ventas": pd.DataFrame(
            [
                # D1: copia idéntica exacta (incluye Observación.1 igual).
                {"ID Documento": "D1", "Fecha": "01/01/2026", "Monto": "100", "Observación.1": "nota"},
                {"ID Documento": "D1", "Fecha": "01/01/2026", "Monto": "100", "Observación.1": "nota"},
                # D2: solo difiere en Observación.1 -- no es conflicto real.
                {"ID Documento": "D2", "Fecha": "02/01/2026", "Monto": "200", "Observación.1": "nota A"},
                {"ID Documento": "D2", "Fecha": "02/01/2026", "Monto": "200", "Observación.1": "nota B"},
                # D3: conflicto real -- el Monto difiere.
                {"ID Documento": "D3", "Fecha": "03/01/2026", "Monto": "300", "Observación.1": "nota"},
                {"ID Documento": "D3", "Fecha": "03/01/2026", "Monto": "999", "Observación.1": "nota"},
            ]
        )
    }
    mapping = {"Ventas": {"fecha": "Fecha", "monto": "Monto"}}

    result = analyze_business_workbook(frames, mapping, {})

    assert result is not None
    alcance = result["alcance"]
    assert alcance["documentos_repetidos"] == 3
    assert alcance["documentos_conflictivos"] == 1
    assert alcance["documentos_identicos"] == 1
    assert alcance["documentos_solo_observacion_distinta"] == 1
    details = result["calidad"]["documentos"]
    assert {item["id"]: item["tipo"] for item in details} == {
        "D1": "idéntico",
        "D2": "solo_observación",
        "D3": "conflicto",
    }
    assert details[0]["ubicaciones"][0] == {"hoja": "Ventas", "fila": 2}


def test_business_quality_reports_negative_cost_sheet_and_row_without_modifying_it():
    costs = pd.DataFrame(
        [
            {"SKU Producto": "A", "Costo Unitario": "-40"},
            {"SKU Producto": "B", "Costo Unitario": "70"},
        ]
    )
    costs.attrs["adsveris_source_rows"] = [7, 8]
    frames = {
        "Ventas": pd.DataFrame(
            [{"Fecha": "01/01/2026", "SKU Producto": "A", "Cantidad": "1", "Monto": "100"}]
        ),
        "Costos_Productos": costs,
    }
    mapping = {
        "Ventas": {
            "fecha": "Fecha",
            "monto": "Monto",
            "cantidad": "Cantidad",
            "producto": "SKU Producto",
        }
    }

    result = analyze_business_workbook(frames, mapping, {})

    assert result is not None
    assert result["calidad"]["costos"]["negativos"] == 1
    assert result["calidad"]["costos_detalle"]["negativos"] == [
        {
            "hoja": "Costos_Productos",
            "fila": 7,
            "valor": -40.0,
            "clave": "A",
        }
    ]


def test_current_catalogue_fills_history_gaps_without_certifying_the_estimate():
    frames = {
        "Ventas_2024": pd.DataFrame(
            [
                {
                    "Fecha Venta": "01/01/2024",
                    "ID Documento": "D1",
                    "SKU Producto": "A",
                    "Cantidad": "2",
                    "Monto Venta": "200",
                    "Estado": "Vigente",
                }
            ]
        ),
        "Historial_Costos": pd.DataFrame(
            [
                {
                    "SKU Producto": "A",
                    "Fecha Vigencia": "01/01/2025",
                    "Costo Unitario": "40",
                }
            ]
        ),
        "Costos_Productos": pd.DataFrame(
            [{"SKU Producto": "A", "Costo Unitario": "50"}]
        ),
    }

    result = analyze_business_workbook(frames, _sales_mapping(), {})

    assert result is not None
    assert result["estado_resultados"]["cobertura_costos_pct"] == 0
    assert result["estado_resultados"]["cobertura_costos_estimada_pct"] == 100
    assert result["estado_resultados"]["costo_venta_conocido"] == 0
    assert result["estado_resultados"]["costo_venta_estimado_catalogo"] == 100
    assert result["estado_resultados"]["cobertura_costos_certificable_pct"] == 0
    assert result["estado_resultados"]["utilidad_certificable"] is None
    assert result["calidad"]["costos"]["filas_costo_actual_estimado"] == 1


def test_certifiable_sales_keep_one_exact_copy_and_exclude_conflicting_ids():
    base = {
        "Fecha Venta": "01/01/2026",
        "SKU Producto": "A",
        "Cantidad": "1",
        "Monto Venta": "100",
        "Estado": "Vigente",
    }
    frames = {
        "Ventas_2026": pd.DataFrame(
            [
                {**base, "ID Documento": "EXACTO"},
                {**base, "ID Documento": "EXACTO"},
                {**base, "ID Documento": "CONFLICTO"},
                {**base, "ID Documento": "CONFLICTO", "Monto Venta": "150"},
            ]
        ),
        "Costos_Productos": pd.DataFrame(
            [{"SKU Producto": "A", "Costo Unitario": "40"}]
        ),
    }

    result = analyze_business_workbook(frames, _sales_mapping(), {})

    assert result is not None
    assert result["estado_resultados"]["ventas_observadas"] == 450
    # Los hallazgos no eliminan filas en silencio: toda corrección requiere una
    # acción confirmada en Limpieza.
    assert result["estado_resultados"]["ventas_certificables"] == 450
    assert result["alcance"]["documentos_repetidos"] == 2
    assert result["alcance"]["filas_adicionales_documento"] == 2
    assert result["alcance"]["documentos_conflictivos"] == 1


def test_business_analysis_preaggregates_collections_and_excludes_exact_payment_duplicates():
    frames = {
        "Ventas_2026": pd.DataFrame(
            [
                {
                    "Fecha Venta": "01/01/2026",
                    "ID Documento": "D1",
                    "SKU Producto": "A",
                    "Cantidad": "1",
                    "Monto Venta": "100",
                    "Total Documento": "119",
                    "Estado": "Vigente",
                    "ID Cliente": "C1",
                }
            ]
        ),
        "Costos_Productos": pd.DataFrame(
            [{"SKU Producto": "A", "Costo Unitario": "50"}]
        ),
        "Cobranzas": pd.DataFrame(
            [
                {"ID Pago": "P1", "ID Documento": "D1", "Monto Pago": "60", "Estado Pago": "Aplicado", "Fecha Pago": "02/01/2026"},
                {"ID Pago": "P1", "ID Documento": "D1", "Monto Pago": "60", "Estado Pago": "Aplicado", "Fecha Pago": "02/01/2026"},
                {"ID Pago": "P2", "ID Documento": "D1", "Monto Pago": "59", "Estado Pago": "Aplicado", "Fecha Pago": "03/01/2026"},
            ]
        ),
    }

    result = analyze_business_workbook(frames, _sales_mapping(), {})

    assert result is not None
    assert result["operacion"]["cobrado_aplicado"] == 119
    assert result["operacion"]["pagos_duplicados_excluidos"] == 1
    assert result["operacion"]["documentos_sobrepagados"] == 0
    assert result["operacion"]["cobranza_sobre_documentos_pct"] == 100


def test_business_analysis_does_not_treat_credit_notes_as_overpaid_receivables():
    frames = {
        "Ventas_2026": pd.DataFrame(
            [
                {
                    "Fecha Venta": "01/01/2026",
                    "ID Documento": "F1",
                    "Tipo Documento": "Factura",
                    "SKU Producto": "A",
                    "Cantidad": "1",
                    "Monto Venta": "100",
                    "Total Documento": "119",
                    "Estado": "Vigente",
                },
                {
                    "Fecha Venta": "02/01/2026",
                    "ID Documento": "NC1",
                    "Tipo Documento": "Nota de Credito",
                    "SKU Producto": "A",
                    "Cantidad": "-1",
                    "Monto Venta": "-100",
                    "Total Documento": "-119",
                    "Estado": "Vigente",
                },
            ]
        ),
        "Costos_Productos": pd.DataFrame(
            [{"SKU Producto": "A", "Costo Unitario": "50"}]
        ),
        "Cobranzas": pd.DataFrame(
            [
                {
                    "ID Pago": "P1",
                    "ID Documento": "F1",
                    "Monto Pago": "119",
                    "Estado Pago": "Aplicado",
                    "Fecha Pago": "03/01/2026",
                }
            ]
        ),
    }

    result = analyze_business_workbook(frames, _sales_mapping(), {})

    assert result is not None
    assert result["operacion"]["documentos_sobrepagados"] == 0
    assert result["operacion"]["cobranza_sobre_documentos_pct"] == 100


def test_conflicting_cost_master_never_multiplies_sales_or_invents_margin():
    frames = {
        "Ventas_2026": pd.DataFrame(
            [
                {
                    "Fecha Venta": "01/01/2026",
                    "ID Documento": "D1",
                    "SKU Producto": "A",
                    "Cantidad": "2",
                    "Monto Venta": "200",
                    "Estado": "Vigente",
                    "ID Cliente": "C1",
                }
            ]
        ),
        "Costos_Productos": pd.DataFrame(
            [
                {"SKU Producto": "A", "Costo Unitario": "40"},
                {"SKU Producto": "A", "Costo Unitario": "90"},
            ]
        ),
    }

    result = analyze_business_workbook(frames, _sales_mapping(), {})

    assert result is not None
    assert result["estado_resultados"]["ventas_observadas"] == 200
    assert result["estado_resultados"]["cobertura_costos_pct"] == 0
    assert result["estado_resultados"]["utilidad_bruta"] is None
    assert result["calidad"]["costos"]["conflictivas"] == 1
    assert result["estado_certificacion"] == "blocked"


def test_inventory_is_not_misclassified_as_sales_and_unsupported_ratios_stay_unavailable():
    frames = {
        "Ventas_2026": pd.DataFrame(
            [{"Fecha Venta": "01/01/2026", "ID Documento": "D1", "SKU Producto": "A", "Cantidad": "1", "Monto Venta": "100", "Estado": "Vigente"}]
        ),
        "Inventario": pd.DataFrame(
            [{"SKU Producto": "A", "Stock Sistema": "3", "Valor Inventario": "120"}]
        ),
    }

    kinds = classify_business_sheets(frames)
    result = analyze_business_workbook(frames, _sales_mapping(), {})

    assert kinds["ventas"] == ["Ventas_2026"]
    assert kinds["inventario"] == ["Inventario"]
    assert result is not None
    unavailable = {
        ratio["id"]: ratio["estado"]
        for ratio in result["ratios"]
        if ratio["id"] in {"liquidez_corriente", "prueba_acida", "roe", "roa", "ebitda"}
    }
    assert unavailable == {
        "liquidez_corriente": "unavailable",
        "prueba_acida": "unavailable",
        "roe": "unavailable",
        "roa": "unavailable",
        "ebitda": "unavailable",
    }


def test_business_analysis_enriches_category_by_id_and_marks_partial_month_pace():
    frames = {
        "Ventas_2025": pd.DataFrame(
            [
                {
                    "Fecha": "30/11/2025",
                    "ID Documento": "D1",
                    "ID_Producto": "P1",
                    "Cantidad": 1,
                    "Monto": 3000,
                    "Estado": "Vigente",
                },
                {
                    "Fecha": "18/12/2025",
                    "ID Documento": "D2",
                    "ID_Producto": "P1",
                    "Cantidad": 1,
                    "Monto": 1800,
                    "Estado": "Vigente",
                },
            ]
        ),
        "Productos": pd.DataFrame(
            [{
                "ID_Producto": "P1",
                "Nombre_Producto": "Producto Uno",
                "Categoria": "Aseo Industrial",
            }]
        ),
        "Historial_Costos": pd.DataFrame(
            [{
                "ID_Producto": "P1",
                "Fecha_Desde": "01/01/2025",
                "Fecha_Hasta": "31/12/2025",
                "Costo_Unitario": 500,
            }]
        ),
    }
    mappings = {
        "Ventas_2025": {
            "fecha": "Fecha",
            "monto": "Monto",
            "cantidad": "Cantidad",
            "producto": "ID_Producto",
        }
    }

    result = analyze_business_workbook(
        frames,
        mappings,
        {
            "Ventas_2026": {
                "_moneda": SimpleNamespace(
                    dominante="CLP",
                    detectadas=["CLP", "USD"],
                    mixta=True,
                )
            }
        },
    )

    assert result is not None
    assert result["agrupaciones"]["categorias"][0]["nombre"] == "Aseo Industrial"
    assert result["agrupaciones"]["productos"][0]["nombre"] == "Producto Uno"
    december = result["evolucion"][-1]
    assert december["parcial"] is True
    assert december["cobertura_hasta_dia"] == 18
    assert december["dias_del_mes"] == 31
    # Noviembre: 3.000 / 30 = 100 por día; diciembre: 1.800 / 18 = 100.
    assert december["variacion_ritmo_pct"] == pytest.approx(0.0)
    assert december["proyeccion_ritmo_mes_completo"] == pytest.approx(3100.0)


def test_adaptive_indicator_catalog_exposes_only_defensible_metrics():
    frames = {
        "Ventas_2026": pd.DataFrame([
            {
                "Fecha Venta": "31/01/2026",
                "ID Documento": "D1",
                "SKU Producto": "A",
                "Cantidad": 2,
                "Monto Venta": 200,
                "Estado": "Vigente",
            },
            {
                "Fecha Venta": "28/02/2026",
                "ID Documento": "D2",
                "SKU Producto": "A",
                "Cantidad": 1,
                "Monto Venta": 120,
                "Estado": "Vigente",
            },
        ]),
        "Costos_Productos": pd.DataFrame([
            {"SKU Producto": "A", "Costo Unitario": 40},
        ]),
        "Inventario": pd.DataFrame([
            {
                "Fecha Snapshot": "28/02/2026",
                "SKU Producto": "A",
                "Stock Disponible": 5,
                "Valor Inventario": 200,
            },
        ]),
    }

    result = analyze_business_workbook(frames, _sales_mapping(), {})

    assert result is not None
    catalog = result["catalogo_indicadores"]
    assert result["version"] == 2
    assert catalog["version"] == 1
    by_id = {
        indicator["id"]: indicator
        for category in catalog["categorias"]
        for indicator in category["indicadores"]
    }
    assert by_id["ventas_netas"]["valor"] == 320
    assert by_id["ventas_netas"]["estado"] == "available"
    assert by_id["ticket_promedio_documento"]["valor"] == 160
    assert by_id["costo_venta"]["valor"] == 120
    assert by_id["utilidad_bruta"]["valor"] == 200
    assert by_id["stock_valorizado"]["valor"] == 200
    # Cash flow and balance metrics are not inferred from sales or inventory.
    # Missing inputs stay null rather than becoming a fake zero.
    assert by_id["flujo_neto_caja"]["valor"] is None
    assert by_id["flujo_neto_caja"]["estado"] == "unavailable"
    assert by_id["liquidez_corriente"]["valor"] is None
    assert by_id["roe"]["valor"] is None
    assert by_id["costo_venta"]["formula"].startswith("Σ (cantidad")
    assert by_id["costo_venta"]["fuentes"]


def test_adaptive_indicator_catalog_blocks_unfiltered_mixed_currency_money():
    frames = {
        "Ventas_2026": pd.DataFrame([
            {
                "Fecha Venta": "31/01/2026",
                "ID Documento": "D1",
                "Monto Venta": 100,
                "Moneda": "CLP",
                "Estado": "Vigente",
            },
            {
                "Fecha Venta": "28/02/2026",
                "ID Documento": "D2",
                "Monto Venta": 20,
                "Moneda": "USD",
                "Estado": "Vigente",
            },
        ]),
    }
    mappings = _sales_mapping()
    mappings["Ventas_2026"]["moneda"] = "Moneda"

    result = analyze_business_workbook(frames, mappings, {})

    assert result is not None
    catalog = result["catalogo_indicadores"]
    assert catalog["moneda"] == "mixta"
    by_id = {
        indicator["id"]: indicator
        for category in catalog["categorias"]
        for indicator in category["indicadores"]
    }
    assert by_id["ventas_netas"]["valor"] is None
    assert by_id["ventas_netas"]["estado"] == "blocked"
    assert "monedas incompatibles" in by_id["ventas_netas"]["advertencias"][0]
    # Non-monetary metrics remain usable.
    assert by_id["unidades_vendidas"]["estado"] == "unavailable"
