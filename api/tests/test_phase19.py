"""Fase 19 — auditoría del libro PYME Desafiante 2026 y rentabilidad para decidir.

Cubre: filas TOTAL estructurales excluidas de indicadores, 'Total Documento'
numérico (los tokens de documento ceden ante marcadores monetarios),
validaciones IVA/total por fila, costos peligrosos, duplicados
posnormalización en Observaciones, columnas de texto libre sin ruido,
Manifest honesto y el análisis de rentabilidad (portafolio por cuadrantes).
"""

import io

import openpyxl
import pandas as pd
import pytest

from app.engine.metrics import compute_metrics
from app.engine.standardize import is_identifier_column, structural_total_mask
from app.routes.pipeline import _clean_download_book_uncached_sync


def _ventas_frame() -> pd.DataFrame:
    filas = []
    for indice in range(40):
        filas.append({
            "ID_Documento": f"FV-{indice:04d}",
            "Fecha Venta": f"2026-0{1 + indice % 4}-{1 + indice % 27:02d}",
            "SKU_Producto": f"SKU-{indice % 8:03d}",
            "Cantidad": "2",
            "Monto Venta": str(100000 + indice * 5000),
            "IVA": str(round((100000 + indice * 5000) * 0.19)),
            "Total Documento": str(round((100000 + indice * 5000) * 1.19)),
            "Estado": "Completada",
            "Observación": "",
        })
    filas.append({  # anulada: se conserva pero no suma
        "ID_Documento": "FV-ANU", "Fecha Venta": "2026-02-10", "SKU_Producto": "SKU-001",
        "Cantidad": "1", "Monto Venta": "999999", "IVA": "189999", "Total Documento": "1189998",
        "Estado": "Anulada", "Observación": "",
    })
    filas.append({  # fila TOTAL estructural
        "ID_Documento": "TOTAL 2026", "Fecha Venta": "", "SKU_Producto": "",
        "Cantidad": "", "Monto Venta": "99999999", "IVA": "18999999", "Total Documento": "118999998",
        "Estado": "", "Observación": "Total exportado",
    })
    return pd.DataFrame(filas)


# ── Detección de totales estructurales ───────────────────────────────────────

def test_structural_total_mask_detecta_solo_la_fila_total():
    df = _ventas_frame()
    mask = structural_total_mask(df, "Fecha Venta")
    assert int(mask.sum()) == 1
    assert df.loc[mask, "ID_Documento"].iloc[0] == "TOTAL 2026"


def test_structural_total_no_confunde_productos_llamados_total():
    df = pd.DataFrame({
        "ID": ["V-1", "V-2"],
        "Fecha": ["2026-01-05", "2026-01-06"],
        "Producto": ["Total Look Espejo", "Silla"],
        "Monto": ["10000", "20000"],
    })
    assert int(structural_total_mask(df, "Fecha").sum()) == 0


def test_metrics_excluye_totales_y_anuladas_de_los_indicadores():
    df = _ventas_frame()
    resultado = compute_metrics(
        df, {"fecha": "Fecha Venta", "monto": "Monto Venta", "producto": "SKU_Producto", "cantidad": "Cantidad"}
    )
    esperado = sum(100000 + indice * 5000 for indice in range(40))
    assert resultado["kpis"]["ingresos_totales"]["valor"] == esperado
    exclusiones = resultado["exclusiones_indicadores"]
    assert exclusiones["filas_anuladas"] == 1
    assert exclusiones["filas_totales_estructurales"] == 1
    assert any("totales estructurales" in aviso for aviso in resultado["advertencias"])


# ── Identificadores vs montos de documento ───────────────────────────────────

@pytest.mark.parametrize(
    ("encabezado", "esperado"),
    [
        ("Total Documento", False),
        ("Total Factura", False),
        ("ID_Documento", True),
        ("Nro Documento", True),
        ("ID Pago", True),
        ("Codigo Documento", True),
        ("Monto Venta", False),
    ],
)
def test_tokens_monetarios_vencen_a_tokens_debiles_de_documento(encabezado, esperado):
    assert is_identifier_column(encabezado) is esperado


# ── Rentabilidad para decidir ────────────────────────────────────────────────

def test_analisis_rentabilidad_clasifica_cuadrantes_y_bajo_costo():
    filas = []
    # 4 productos: margen alto/bajo × volumen alto/bajo + uno vendido bajo costo
    combinaciones = [
        ("P-ESTRELLA", 60, 100000, 40000),      # margen 60%, volumen alto
        ("P-VACA", 60, 100000, 90000),          # margen 10%, volumen alto
        ("P-OPORTUNIDAD", 4, 100000, 45000),    # margen 55%, volumen bajo
        ("P-PROBLEMA", 4, 100000, 92000),       # margen 8%, volumen bajo
        ("P-RELLENO", 30, 100000, 50000),       # separa las medianas
        ("P-PERDIDA", 6, 50000, 90000),         # vende bajo el costo
    ]
    contador = 0
    for nombre, repeticiones, precio, costo in combinaciones:
        for _ in range(repeticiones):
            contador += 1
            filas.append({
                "Fecha": f"2026-0{1 + contador % 3}-{1 + contador % 27:02d}",
                "Producto": nombre,
                "Monto": str(precio),
                "Costo": str(costo),
            })
    df = pd.DataFrame(filas)
    resultado = compute_metrics(
        df, {"fecha": "Fecha", "monto": "Monto", "producto": "Producto", "costo": "Costo"}
    )
    analisis = resultado["analisis_rentabilidad"]
    cuadrantes = {p["nombre"]: p["cuadrante"] for p in analisis["clasificacion_productos"]}
    assert cuadrantes["P-ESTRELLA"] == "estrella"
    assert cuadrantes["P-VACA"] == "vaca_lechera"
    assert cuadrantes["P-OPORTUNIDAD"] == "oportunidad"
    assert cuadrantes["P-PROBLEMA"] == "problema"
    assert analisis["ventas_bajo_costo"]["filas"] == 6
    assert analisis["ventas_bajo_costo"]["perdida"] == 6 * 40000
    negativos = {p["nombre"] for p in analisis["productos_margen_negativo"]}
    assert "P-PERDIDA" in negativos


# ── Exportación: Observaciones y Manifest ────────────────────────────────────

@pytest.fixture(scope="module")
def libro_pyme() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ventas"
    encabezados = [
        "ID_Documento", "Fecha Venta", "SKU_Producto", "Cantidad",
        "Monto Venta", "IVA", "Total Documento", "Estado", "Observación",
    ]
    ws.append(encabezados)
    for fila in _ventas_frame().itertuples(index=False):
        ws.append(list(fila))
    # descuadres sembrados: IVA imposible y total que no suma
    ws.append(["FV-MAL1", "2026-03-01", "SKU-001", "1", "100000", "50000", "150000", "Completada", ""])
    ws.append(["FV-MAL2", "2026-03-02", "SKU-002", "1", "100000", "19000", "500000", "Completada", ""])
    # duplicado posnormalización: mismo contenido con formato distinto
    ws.append(["FV-0001", "2026-02-02", "SKU-001", "2", "$ 105.000", str(round(105000 * .19)), str(round(105000 * 1.19)), "COMPLETADA", ""])
    costos = wb.create_sheet("Costos_Productos")
    costos.append(["SKU_Producto", "Costo Unitario", "Vigente"])
    for indice in range(8):
        costos.append([f"SKU-{indice:03d}", 30000 + indice * 1000, "Sí"])
    costos.append(["SKU-NEG", -4500, "Sí"])
    costos.append(["SKU-CERO", 0, "Sí"])
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


@pytest.fixture(scope="module")
def exportado(libro_pyme) -> bytes:
    manifiesto = {
        "hojas": [
            {"nombre": nombre, "procesar": True, "rules": {}, "mapping": {},
             "scope": {}, "eliminar_duplicados": False, "revision": 0}
            for nombre in ("Ventas", "Costos_Productos")
        ]
    }
    datos, _, _ = _clean_download_book_uncached_sync(
        "pyme19.xlsx", libro_pyme, manifiesto, "xlsx", None
    )
    return datos


def test_export_total_documento_es_numerico(exportado):
    hoja = pd.read_excel(io.BytesIO(exportado), sheet_name="Ventas")
    columna = hoja["Total Documento"].dropna()
    assert (pd.to_numeric(columna, errors="coerce").notna()).all()
    assert not columna.map(lambda v: isinstance(v, str)).any()


def test_export_observaciones_cubren_negocio_sin_ruido(exportado):
    obs = pd.read_excel(
        io.BytesIO(exportado), sheet_name="Observaciones", dtype=str,
        keep_default_na=False,
    )
    detalles = obs["Detalle"].str.cat(sep=" | ")
    assert "IVA no cuadra" in detalles
    assert "Total no cuadra" in detalles
    assert "Costo negativo" in detalles
    assert "Costo en cero" in detalles
    assert "totales estructurales" in detalles
    assert "duplicado_posnormalizacion" in set(obs["Tipo"])
    # La columna de texto libre no genera alertas de faltante.
    ruido = obs[(obs["Tipo"] == "faltante") & (obs["Columna"].str.contains("Observa", case=False))]
    assert len(ruido) == 0


def test_export_manifest_declara_el_alcance_en_el_libro(exportado):
    manifiesto = pd.read_excel(
        io.BytesIO(exportado), sheet_name="Manifest", dtype=str,
        keep_default_na=False,
    )
    assert "(libro completo)" in set(manifiesto["hoja"])
    hoja_ventas = manifiesto[manifiesto["hoja"] == "Ventas"]
    # Sin alcance analítico activo, la hoja no afirma pertenecer a uno.
    assert hoja_ventas["alcance_analisis"].iloc[0] in {"null", ""}
