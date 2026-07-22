import json

import pandas as pd

from app.engine.clean import analyze_and_clean
from app.engine.loader import _classify_sheet_sample
from app.engine.mapping import detect_column_roles
from app.engine.metrics import compute_metrics


def _metrics(frame: pd.DataFrame) -> dict:
    cleaned = analyze_and_clean(frame, None, apply=True)["_df_limpio"]
    return compute_metrics(cleaned)


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
