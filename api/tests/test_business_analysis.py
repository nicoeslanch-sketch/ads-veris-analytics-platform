"""Regression tests for the safe multi-sheet business model."""

import pandas as pd

from app.engine.business import analyze_business_workbook, classify_business_sheets


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
    assert result["estado_resultados"]["cobertura_costos_pct"] == 100
    assert result["estado_resultados"]["costo_venta_conocido"] == 100
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
    assert result["estado_resultados"]["ventas_certificables"] == 100
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
