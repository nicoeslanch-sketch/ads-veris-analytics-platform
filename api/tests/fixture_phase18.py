"""Fixture sintética multihoja con las trampas del archivo de estrés Fase 18."""
import io
import random

import openpyxl


def build_stress_book() -> bytes:
    rng = random.Random(18)
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    def add_sheet(name, headers, rows):
        ws = wb.create_sheet(name)
        ws.append(headers)
        for row in rows:
            ws.append(row)

    ventas_headers = [
        "ID_Venta", "Fecha", "ID_Producto", "ID_Sucursal", "Canal",
        "Cantidad", "Monto", "TipoCliente", "Region",
    ]

    def ventas_rows(prefix, tipo_variants, n=60):
        rows = []
        canales = ["Tienda", "ONLINE", "market place", "Tda."]
        for i in range(n):
            monto = str(rng.randrange(20, 900) * 1000)
            rows.append([
                f"{prefix}-{i:03d}",
                f"2025-0{1 + (i % 4)}-{1 + (i % 27):02d}",
                f"P-{1 + (i % 5):03d}",
                f"S-{1 + (i % 3):02d}",
                canales[i % 4],
                str(1 + (i % 5)),
                monto,
                tipo_variants[i % len(tipo_variants)],
                ["Norte", "Centro", "Sur"][i % 3],
            ])
        # Trampas: ambiguo "1,234", vacío, negativo, duplicado exacto
        rows.append([f"{prefix}-amb", "2025-02-10", "P-001", "S-01", "Tienda", "1", "1,234", tipo_variants[0], "Norte"])
        rows.append([f"{prefix}-vac", "2025-02-11", "P-002", "S-02", "Online", "2", "", tipo_variants[0], "Centro"])
        rows.append([f"{prefix}-neg", "2025-02-12", "P-003", "S-03", "Online", "1", "-45000", tipo_variants[0], "Sur"])
        rows.append(rows[0])
        return rows

    # La variante más FRECUENTE difiere por hoja (PERSONA en A, persona en B):
    # el canónico por frecuencia quedaba distinto entre hojas; el estable por
    # estilo Título debe elegir "Persona" en ambas.
    add_sheet("Ventas_A", ventas_headers, ventas_rows("A", ["Persona", "PERSONA", "PERSONA", "Empresa"]))
    add_sheet("Ventas_B", ventas_headers, ventas_rows("B", ["persona", "persona", "Persona", "Empresa"]))
    add_sheet(
        "Productos",
        ["ID_Producto", "Producto", "Categoria", "Costo_Unitario", "Precio_Lista", "Estado"],
        [
            [f"P-{i:03d}", f"Producto {i}", ["Hogar", "Oficina"][i % 2], str(20000 + i * 1000), str(40000 + i * 1500), "Activo"]
            for i in range(1, 6)
        ],
    )
    add_sheet(
        "Sucursales",
        ["ID_Sucursal", "Sucursal", "Comuna", "Region", "Estado"],
        [
            ["S-01", "Sucursal Santiago", "Santiago", "Metropolitana", "Activa"],
            ["S-02", "Sucursal Talca", "Talca", "Maule", "Activa"],
            ["S-03", "Sucursal Concepción", "Concepción", "Biobío", "En mantención"],
        ],
    )
    add_sheet(
        "Inventario",
        ["ID_Producto", "ID_Sucursal", "Stock", "Stock_Minimo", "Ultima_Actualizacion"],
        [
            [f"P-{p:03d}", f"S-{s:02d}", str(rng.randrange(-5, 300)), "40", "2025-06-01"]
            for p in range(1, 6)
            for s in range(1, 4)
        ],
    )
    add_sheet(
        "Meta_Campanas",
        ["ID_Campana", "Plataforma", "Fecha_Inicio", "Inversion", "Impresiones", "Clics", "Estado"],
        [
            ["C-001", "Meta Ads", "2025-01-10", "1200000", "300000", "12000", "Activa"],
            ["C-002", "Google Ads", "2025-02-10", "900000", "250000", "9000", "Pausada"],
            ["C-003", "TikTok Ads", "2025-03-10", "500000", "1000", "2500", "Activa"],
            ["C-004", "Meta Ads", "2025-04-10", "700000", "150000", "6000", "Finalizada"],
        ],
    )
    add_sheet(
        "Trabajadores",
        ["ID_Empleado", "Nombre", "Cargo", "Sueldo", "Sucursal"],
        [
            [f"E-{i:02d}", f"Persona {i}", ["Vendedor", "Cajero", "Supervisor"][i % 3], str(600000 + i * 25000), f"S-{1 + (i % 3):02d}"]
            for i in range(1, 16)
        ],
    )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


if __name__ == "__main__":
    import pathlib
    pathlib.Path("/tmp/claude-0/-home-user-ads-veris-analytics-platform/3e9e0e35-6fcb-55fb-a8d9-65961401861f/scratchpad/stress18.xlsx").write_bytes(build_stress_book())
    print("ok")
