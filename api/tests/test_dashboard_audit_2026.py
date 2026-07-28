import json

import pandas as pd

from app.engine.clean import analyze_and_clean
from app.engine.business import analyze_business_workbook
from app.engine.loader import _classify_sheet_sample, _detect_header_row
from app.engine.mapping import detect_column_roles
from app.engine.metrics import compute_metrics
from app.engine.quality import line_sales_evidence
from app.engine.relationships import detect_relationship_catalog
from app.engine.standardize import parse_date, parse_number


def _metrics(frame: pd.DataFrame) -> dict:
    cleaned = analyze_and_clean(frame, None, apply=True)["_df_limpio"]
    return compute_metrics(cleaned)


def test_excel_servicios_no_inventa_ventas_en_hojas_operacionales():
    fixtures = [
        (
            "detalle_ot",
            pd.DataFrame(
                {
                    "N° OT": ["OT-00001", "OT-00002"],
                    "Fecha": ["2025-01-01", "2025-01-02"],
                    "Tipo de Línea": ["Material", "Subcontrato"],
                    "Cod Item": ["I-1", ""],
                    "Cantidad": [2, 1],
                    "Precio Unitario": [4_000, 7_000],
                    "MONTO": [8_000, 7_000],
                }
            ),
            "Monto total de líneas OT",
        ),
        (
            "horas_tecnicos",
            pd.DataFrame(
                {
                    "N° OT": ["OT-1", "OT-2"],
                    "Fecha": ["2025-01-01", "2025-01-02"],
                    "Cod Tecnico": ["T-1", "T-2"],
                    "Horas": [8, 3],
                    "Tipo": ["Normal", "Extra"],
                    "¿Factura?": ["Sí", "No"],
                }
            ),
            "Horas registradas",
        ),
        (
            "tarifas_tecnicos",
            pd.DataFrame(
                {
                    "Cod Tecnico": ["T-1", "T-2"],
                    "Vigente Desde": ["2025-01-01", "2025-01-01"],
                    "Vigente Hasta": ["2025-06-30", "2025-06-30"],
                    "Valor Hora Venta": [20_000, 25_000],
                    "Costo Hora": [12_000, 15_000],
                }
            ),
            "Tarifa de venta promedio",
        ),
        (
            "contratos",
            pd.DataFrame(
                {
                    "Cod Contrato": ["C-1", "C-2"],
                    "Cod Cliente": ["CL-1", "CL-2"],
                    "Vigencia Desde": ["2025-01-01", "2025-02-01"],
                    "Vigencia Hasta": ["2025-12-31", "2025-12-31"],
                    "Monto Mensual": [10, 500_000],
                    "Moneda": ["UF", "CLP"],
                }
            ),
            "Valor contractual mensual",
        ),
        (
            "valor_uf",
            pd.DataFrame(
                {
                    "Periodo": ["2025-01", "2025-02"],
                    "Valor UF (CLP)": [38_400, 38_600],
                }
            ),
            "Valor UF de referencia",
        ),
    ]
    for subtype, frame, expected_label in fixtures:
        metrics = _metrics(frame)
        assert metrics.get("tipo_analisis") == "generico", subtype
        assert metrics["analisis_generico"]["subtipo"] == subtype
        assert metrics["kpis"]["ingresos_totales"] is None
        labels = {
            item.get("etiqueta")
            for item in metrics["analisis_generico"]["numericas"]
        }
        assert expected_label in labels


def _detalle_ot_sales_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "N° OT": [f"OT-{index:03d}" for index in range(1, 11)],
            "Fecha": [f"2025-01-{index:02d}T00:00:00" for index in range(1, 10)]
            + ["fecha inválida"],
            "Tipo de Línea": ["Material", "Subcontrato"] * 5,
            "Cod Item": [f"ITEM-{index:03d}" for index in range(1, 11)],
            "CANTIDAD": [2, 3, 1, 4, 5, 2, 1, 3, 2, 4],
            "PRECIO UNITARIO": [
                "2.935600E+05",
                100_000,
                50_000,
                25_000,
                80_000,
                40_000,
                120_000,
                30_000,
                55_000,
                10_000,
            ],
            "DESCUENTO": ["10%", "10", 0.10, 0, 0.05, 5, 0, 0.20, 20, 0],
            # La última línea no cuadra a propósito. Se informa, pero la fuente
            # sigue confirmada porque las otras nueve validan la fórmula.
            "MONTO": [
                "5.284080E+05",
                270_000,
                45_000,
                100_000,
                380_000,
                76_000,
                120_000,
                72_000,
                88_000,
                90_000,
            ],
        }
    )


def test_detalle_ot_confirma_ventas_por_formula_sin_relaciones():
    source = _detalle_ot_sales_frame()
    cleaned = analyze_and_clean(source, None, apply=True)
    evidence = cleaned["evidencia_venta_linea"]
    assert evidence["confirmada"] is True
    assert evidence["columna_monto"] == "MONTO"
    assert evidence["filas_evaluadas"] == 10
    assert evidence["filas_inconsistentes"] == 1
    assert evidence["coincidencia_formula_pct"] == 90.0

    metrics = compute_metrics(cleaned["_df_limpio"], cleaned["mapeo"])
    assert metrics["tipo_analisis"] == "ventas"
    assert metrics["semantica_ventas"] == {
        "granularidad": "linea",
        "etiqueta_total": "Ventas netas",
        "etiqueta_promedio": "Venta promedio por línea",
    }
    assert metrics["kpis"]["ingresos_totales"]["valor"] == 1_161_408
    assert metrics["kpis"]["transacciones"] == 5
    assert metrics["kpis"]["unidades_totales"] == 11
    assert metrics["kpis"]["gastos_totales"] is None
    assert metrics["kpis"]["ganancia_neta"] is None
    assert metrics["trazabilidad_ventas"]["columna"] == "MONTO"
    assert metrics["trazabilidad_ventas"]["fechas_validas"] == 5
    assert metrics["trazabilidad_ventas"]["fechas_invalidas"] == 0
    assert metrics["trazabilidad_ventas"]["relaciones_utilizadas"] == []
    assert any("1 línea(s) no coinciden" in warning for warning in metrics["advertencias"])
    assert any("Subcontrato" in warning for warning in metrics["advertencias"])

    business = analyze_business_workbook(
        {"Detalle_OT": cleaned["_df_limpio"]},
        {"Detalle_OT": cleaned["mapeo"]},
        {"Detalle_OT": cleaned},
    )
    # Analizar una hoja sí reconoce las ventas de Material. La Visión del
    # negocio se reserva para la red completa (horas, tarifas, contratos,
    # gastos e Items), por lo que no inventa un estado de resultados parcial.
    assert business is None


def test_monto_generico_sin_evidencia_comercial_no_es_venta():
    frame = pd.DataFrame(
        {
            "Periodo": ["2025-01", "2025-02", "2025-03"],
            "Descripción": ["Cuota A", "Cuota B", "Cuota C"],
            "MONTO": [100_000, 120_000, 90_000],
        }
    )
    evidence = line_sales_evidence(frame)
    metrics = _metrics(frame)
    assert evidence.confirmed is False
    assert metrics.get("tipo_analisis") != "ventas"
    assert metrics["kpis"]["ingresos_totales"] is None


def test_parser_admite_cientificos_iso_t_y_encabezado_inferior_multinivel():
    assert parse_number("8.520000E+03") == 8_520
    assert parse_number("2.935600E+05") == 293_560
    assert parse_number("1.059000E+06") == 1_059_000
    assert parse_date("2025-01-01T00:00:00") == pd.Timestamp("2025-01-01")
    assert parse_date("2025-08-28T00:00:00") == pd.Timestamp("2025-08-28")
    raw = pd.DataFrame(
        [
            ["OT", "OT", "Costos", "Costos"],
            ["N° OT", "Fecha", "Cantidad", "MONTO"],
            ["OT-1", "2025-01-01T00:00:00", "2", "8.520000E+03"],
        ]
    )
    assert _detect_header_row(raw) == 1


def test_red_operacional_detecta_relaciones_reales_y_bloquea_maestra_duplicada():
    frames = {
        "Ordenes_Trabajo": pd.DataFrame(
            {
                "N° OT": ["OT-00001", "OT-00002"],
                "Cod. Cliente": ["CL-1", "CL-2"],
                "Estado": ["Abierta", "Cerrada"],
            }
        ),
        "Detalle_OT": pd.DataFrame(
            {
                "N° OT": ["OT-00001", "OT-00001", "OT-00002"],
                "Tipo de Línea": ["Material", "Subcontrato", "Material"],
                "Cod Item": ["I-1", "", "I-2"],
                "Cantidad": [1, 1, 2],
                "MONTO": [100, 200, 300],
            }
        ),
        "Clientes": pd.DataFrame(
            {
                "Cod Cliente": ["CL-1", "CL-1", "CL-2"],
                "Cliente": ["Uno", "Uno duplicado", "Dos"],
            }
        ),
    }
    catalog = detect_relationship_catalog(frames)
    pairs = {
        (item["left_sheet"], item["right_sheet"])
        for item in catalog["relationships"]
    }
    assert ("Detalle_OT", "Ordenes_Trabajo") in pairs
    # La referencia Clientes repite CL-1: nunca se publica como conexión
    # ejecutable porque multiplicaría la orden correspondiente.
    assert ("Ordenes_Trabajo", "Clientes") not in pairs
    assert catalog["discarded_count"] >= 1


def test_parametros_se_recomienda_conservar_y_no_procesar_como_datos():
    sample = pd.DataFrame(
        [
            ["Comercial Altamar SpA — Parámetros del archivo", ""],
            ["Parámetro", "Valor"],
            ["Empresa", "Comercial Altamar SpA"],
            ["Moneda", "CLP"],
            ["IVA", "0.19"],
            ["Periodo ventas", "01-01-2024 a 30-06-2026"],
            ["Origen", "Base sintética"],
        ]
    )

    profile = _classify_sheet_sample("Parametros", sample)

    assert profile["clasificacion"] == "auxiliar"
    assert profile["recomendacion"] == "conservar_sin_procesar"


def test_unidad_venta_no_se_mapea_como_monto_y_catalogo_sin_costos_es_producto():
    frame = pd.DataFrame(
        {
            "SKU_Producto": ["A", "B"],
            "Producto": ["Uno", "Dos"],
            "Categoria": ["Aseo", "Oficina"],
            "Unidad Venta": ["Caja", "Unidad"],
            "Precio Lista Neto": [10_000, 20_000],
            "Fecha Alta": ["01/01/2025", "02/01/2025"],
            "Activo": ["Sí", "No"],
        }
    )

    mapping = detect_column_roles(list(frame.columns))
    assert mapping["monto"] == "Precio Lista Neto"
    metrics = _metrics(frame)
    assert metrics["tipo_analisis"] == "catalogo_productos"
    assert metrics["analisis_productos"]["precios_lista"]["promedio"] == 15_000
    assert metrics["kpis"]["ingresos_totales"] is None


def test_compras_gastos_y_cobranzas_no_se_presentan_como_ventas():
    fixtures = [
        (
            "compras",
            pd.DataFrame(
                {
                    "ID_Compra": ["OC-1", "OC-2"],
                    "Fecha Compra": ["01/01/2026", "02/01/2026"],
                    "ID_Proveedor": ["P-1", "P-2"],
                    "Cantidad Comprada": [2, 3],
                    "Costo Unitario Compra": [100, 200],
                    "Monto Neto Compra": [200, 600],
                    "IVA": [38, 114],
                    "Total Compra": [238, 714],
                    "Estado Recepción": ["Recibida", "Pendiente"],
                }
            ),
            "Total Compra",
            952,
        ),
        (
            "gastos",
            pd.DataFrame(
                {
                    "ID_Gasto": ["G-1", "G-2"],
                    "Fecha Gasto": ["01/01/2026", "02/01/2026"],
                    "Categoria Gasto": ["Arriendo", "Logística"],
                    "Monto Neto": [1_000, 2_000],
                    "IVA": [190, 380],
                    "Total Gasto": [1_190, 2_380],
                    "Tipo Gasto": ["Fijo", "Variable"],
                }
            ),
            "Total Gasto",
            3_570,
        ),
        (
            "cobranzas",
            pd.DataFrame(
                {
                    "ID_Pago": ["P-1", "P-2"],
                    "ID_Documento": ["F-1", "F-2"],
                    "Fecha Pago": ["01/01/2026", "02/01/2026"],
                    "Monto Pago": [400, 600],
                    "Medio Pago": ["Efectivo", "Transferencia"],
                    "Estado Pago": ["Aplicado", "Pendiente"],
                }
            ),
            "Monto Pago",
            1_000,
        ),
    ]

    for subtype, frame, total_column, expected in fixtures:
        metrics = _metrics(frame)
        assert metrics["tipo_analisis"] == "generico"
        assert metrics["analisis_generico"]["subtipo"] == subtype
        assert metrics["kpis"]["ingresos_totales"] is None
        numeric = {
            item["columna"]: item for item in metrics["analisis_generico"]["numericas"]
        }
        assert numeric[total_column]["total"] == expected


def test_proveedores_no_se_clasifican_como_clientes():
    metrics = _metrics(
        pd.DataFrame(
            {
                "ID_Proveedor": ["P-1", "P-2"],
                "Razón Social": ["Uno SpA", "Dos Ltda"],
                "Categoría Principal": ["Aseo", "Oficina"],
                "Región": ["Maule", "Biobío"],
                "Condición Pago Días": [30, 60],
                "Activo": ["Sí", "No"],
            }
        )
    )
    assert metrics["analisis_generico"]["subtipo"] == "proveedores"
    terms = next(
        item
        for item in metrics["analisis_generico"]["numericas"]
        if item["columna"] == "Condición Pago Días"
    )
    assert terms["total"] is None
    assert terms["promedio"] == 45


def test_ventas_con_cliente_pero_sin_id_venta_siguen_siendo_ventas():
    metrics = _metrics(
        pd.DataFrame(
            {
                "Fecha Venta": ["01/01/2026", "02/01/2026"],
                "ID_Cliente": ["C-1", "C-2"],
                "Producto": ["Uno", "Dos"],
                "Cantidad": [1, 2],
                "Monto Venta": [1_000, 2_000],
                "Tipo Movimiento": ["Venta", "Venta"],
            }
        )
    )
    assert metrics.get("tipo_analisis", "ventas") == "ventas"
    assert metrics["kpis"]["ingresos_totales"]["valor"] == 3_000


def test_inventario_usa_stock_disponible_y_no_inventa_utilidad():
    metrics = _metrics(
        pd.DataFrame(
            {
                "Fecha Corte": ["30/06/2026", "30/06/2026"],
                "SKU_Producto": ["A", "B"],
                "Stock Sistema": [10, 20],
                "Stock Físico": [9, 19],
                "Stock Disponible": [7, 15],
                "Stock Mínimo": [8, 10],
                "Unidades Comprometidas": [2, 4],
                "Costo Unitario Referencia": [100, 200],
                "Valor Inventario": [900, 3_800],
            }
        )
    )
    assert metrics["tipo_analisis"] == "inventario"
    assert metrics["analisis_inventario"]["stock_total"] == 22
    assert metrics["analisis_inventario"]["bajo_minimo"] == 1
    assert metrics["analisis_inventario"]["valor_inventario"] == 4_700
    assert metrics["kpis"]["ganancia_neta"] is None


def test_porcentajes_mixtos_se_llevan_a_puntos_sin_escalar_35_a_3500():
    metrics = _metrics(
        pd.DataFrame(
            {
                "Mes": ["01/01/2026", "01/02/2026", "01/03/2026"],
                "ID_Sucursal": ["S-1", "S-1", "S-1"],
                "Meta Venta Neta": [100, 110, 120],
                "Meta Margen Bruto %": [0.30, 35, -0.20],
                "Meta Nuevos Clientes": [5, 6, 7],
            }
        )
    )
    margin = next(
        item
        for item in metrics["analisis_generico"]["numericas"]
        if item["columna"] == "Meta Margen Bruto %"
    )
    assert margin["promedio"] == 15
    assert margin["minimo"] == -20
    assert margin["maximo"] == 35
    assert margin["fuera_rango"] == 1


def test_catalogo_señala_costos_extremos_sin_borrarlos():
    metrics = _metrics(
        pd.DataFrame(
            {
                "SKU_Producto": ["A", "B", "C", "D", "E", "F"],
                "Costo Unitario": [100, 110, 120, 130, -10, 9_999_999],
                "Costo Total Unitario": [120, 130, 140, 150, 0, 10_000_000],
            }
        )
    )
    analysis = metrics["analisis_productos"]
    assert analysis["costos"]["maximo"] == 9_999_999
    assert analysis["costos_a_revisar"]["registros"] == 2
    assert analysis["costos_a_revisar"]["no_positivos"] == 1
    assert analysis["costos_tipicos"]["maximo"] == 130


def test_catalogo_solo_costos_es_json_estricto_y_no_inventa_precio():
    metrics = _metrics(
        pd.DataFrame(
            {
                "SKU_Producto": ["A", "B", "C"],
                "Costo Unitario": [11_300, 32_370, 57_950],
                "Moneda": ["CLP", "CLP", "CLP"],
            }
        )
    )

    ranking = metrics["analisis_productos"]["ranking_costos"]
    assert ranking
    assert all(item["precio_lista"] is None for item in ranking)
    assert all(item["margen_potencial_pct"] is None for item in ranking)
    assert metrics["analisis_productos"]["precios_lista"]["promedio"] is None
    json.dumps(metrics, allow_nan=False)
