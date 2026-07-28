import pandas as pd

from app.engine.service_model import analyze_service_business, transform_service_sheet
from app.engine.metrics import compute_metrics
from app.engine.mapping import resolve_mapping
from app.routes.pipeline import _metrics_multi_from_processed


def test_service_structural_cleaning_fill_down_subtotals_hours_and_unpivot():
    detail = pd.DataFrame(
        {
            "ID Linea": ["L-1", None, None],
            "N° OT": ["OT-1", None, None],
            "Tipo de Linea": ["Material", "Subcontrato", None],
            "MONTO": [100, 20, 120],
            "Etiqueta": ["", "", "Subtotal OT-1"],
        }
    )
    detail_result = transform_service_sheet(
        "Detalle_OT", detail, [10, 11, 12]
    )
    assert len(detail_result.frame) == 2
    assert detail_result.frame["N° OT"].tolist() == ["OT-00001", "OT-00001"]
    assert detail_result.frame["Rol financiero de la línea"].tolist() == [
        "Ingreso por material",
        "Costo de subcontrato",
    ]
    assert detail_result.removed_rows[0]["fila_origen"] == 12
    assert detail_result.removed_rows[0]["confirmacion"] == "automatica_regla_determinista"

    hours = pd.DataFrame(
        {
            "N° OT": ["OT-1", "OT-00002"],
            "Horas": ["8 hrs", "4,5 h"],
            "¿Factura?": ["X", "-"],
        }
    )
    hour_result = transform_service_sheet("Horas_Tecnicos", hours, [2, 3])
    assert hour_result.frame["N° OT"].tolist() == ["OT-00001", "OT-00002"]
    assert hour_result.frame["Horas"].tolist() == [8.0, 4.5]
    assert hour_result.frame["¿Factura?"].tolist() == ["Sí", "No"]

    expenses = pd.DataFrame(
        {
            "ID_Area": ["A-1"],
            "Concepto_Gasto": ["Arriendo"],
            "Tipo_Gasto": ["Fijo"],
            "Ene-25": [10],
            "Feb-25": [20],
        }
    )
    expense_result = transform_service_sheet("Gastos_Estructura", expenses, [5])
    assert expense_result.frame[["Periodo", "Monto"]].to_dict("records") == [
        {"Periodo": "2025-01", "Monto": 10.0},
        {"Periodo": "2025-02", "Monto": 20.0},
    ]
    expense_metrics = compute_metrics(
        expense_result.frame,
        resolve_mapping(list(expense_result.frame.columns), None),
    )
    assert expense_metrics["kpis"]["ingresos_totales"] is None
    assert expense_metrics["analisis_generico"]["subtipo"] == "gastos_estructura"
    assert expense_metrics["analisis_generico"]["numericas"][0]["total"] == 30.0


def test_service_business_requires_relations_and_separates_revenue_from_cost():
    frames = {
        "Ordenes_Trabajo": pd.DataFrame(
            {
                "N° OT": ["OT-00001"],
                "Fecha Apertura": ["2025-01-05"],
                "ESTADO": ["Cerrada"],
                "TIPO": ["Preventiva"],
                "Cod. Cliente": ["CL-1"],
                "Cod Contrato": ["CT-1"],
            }
        ),
        "Detalle_OT": pd.DataFrame(
            {
                "N° OT": ["OT-00001", "OT-00001"],
                "Tipo de Linea": ["Material", "Subcontrato"],
                "Cod Item": ["I-1", ""],
                "Cant.": [2, 1],
                "MONTO": [100, 20],
                "Fecha": ["2025-01-05", "2025-01-05"],
            }
        ),
        "Horas_Tecnicos": pd.DataFrame(
            {
                "N° OT": ["OT-00001"],
                "Cod Tecnico": ["TEC-1"],
                "Fecha": ["2025-01-05"],
                "Horas": [10],
                "Tipo": ["Normal"],
                "¿Factura?": ["Sí"],
            }
        ),
        "Tarifas_Tecnicos": pd.DataFrame(
            {
                "Cod Tecnico": ["TEC-1"],
                "Vigente Desde": ["2025-01-01"],
                "Vigente Hasta": ["2025-12-31"],
                "COSTO HORA": [8],
                "Valor Hora Venta": [15],
            }
        ),
        "Tecnicos": pd.DataFrame({"Cod Tecnico": ["TEC-1"]}),
        "Items": pd.DataFrame(
            {"Cod Item": ["I-1"], "Costo Estandar": [30], "FAMILIA": ["Mecánico"]}
        ),
        "Clientes": pd.DataFrame(
            {"Cod Cliente": ["CL-1"], "SEGMENTO": ["Industrial"]}
        ),
        "Contratos": pd.DataFrame(
            {"Cod Contrato": ["CT-1"], "Cod Cliente": ["CL-1"], "MONEDA": ["CLP"]}
        ),
        "Cuotas_Contrato": pd.DataFrame(
            {
                "Cod Contrato": ["CT-1"],
                "Periodo": ["2025-01"],
                "Monto": [100],
                "MONEDA": ["CLP"],
                "estado": ["Pagada"],
            }
        ),
        "Valor_UF": pd.DataFrame(
            {"Periodo": ["2025-01"], "Valor UF (CLP)": [38_000]}
        ),
        "Gastos_Estructura": pd.DataFrame(
            {
                "Periodo": ["2025-01"],
                "Monto": [50],
                "Tipo_Gasto": ["Fijo"],
                "Concepto_Gasto": ["Administración"],
            }
        ),
    }

    analysis = analyze_service_business(frames)

    assert analysis is not None
    assert analysis["perfil"] == "servicios_tecnicos"
    assert analysis["servicios"]["kpis"] == {
        "ventas_netas": 350.0,
        "costo_directo": 160.0,
        "utilidad_bruta": 190.0,
        "margen_bruto_pct": 54.29,
        "gastos_estructura": 50.0,
        "utilidad_operacional": 140.0,
        "margen_operacional_pct": 40.0,
        "ebitda": 140.0,
        "margen_ebitda_pct": 40.0,
        "utilizacion_pct": 100.0,
        "costo_horas_no_facturables": 0.0,
        "backlog": 0.0,
        "ot_perdida": 0,
        "ingreso_recurrente": 100.0,
        "ingreso_recurrente_pct": 28.57,
        "ot_total": 1,
        "ot_abiertas": 0,
        "ot_perdida_pct": 0.0,
        "cumplimiento_sla_pct": None,
        "punto_equilibrio": 92.0,
        "punto_equilibrio_ot": 0,
    }
    assert len(analysis["servicios"]["relaciones"]) == 12
    assert analysis["servicios"]["composicion_ingresos"] == [
        {"nombre": "Materiales", "valor": 100.0},
        {"nombre": "Horas facturables", "valor": 150.0},
        {"nombre": "Contratos", "valor": 100.0},
    ]
    assert len(analysis["servicios"]["cascada"]) == 8
    assert analysis["servicios"]["evolucion"][0]["margen_ot_pct"] == 36.0
    assert analysis["servicios"]["por_tecnico"][0]["utilidad_hora"] == 7.0

    scope = {
        "mode": "append_join",
        "sheets": list(frames),
        "append_sheets": ["Detalle_OT"],
        "active_sheet": "Detalle_OT",
        "join": {
            "left_sheet": "Detalle_OT",
            "right_sheet": "Items",
            "left_keys": ["Cod Item"],
            "right_keys": ["Cod Item"],
            "type": "left",
        },
    }
    metrics = _metrics_multi_from_processed(
        "servicios.xlsx",
        frames,
        {name: {} for name in frames},
        {
            name: {
                "resumen": {"calidad_despues": 100.0},
                "_moneda": None,
            }
            for name in frames
        },
        scope,
        None,
        None,
    )
    assert metrics["analysis_provenance"]["mode"] == "service_network"
    assert metrics["analisis_negocio"]["perfil"] == "servicios_tecnicos"
    assert metrics["analisis_negocio"]["servicios"]["kpis"]["ventas_netas"] == 350.0
