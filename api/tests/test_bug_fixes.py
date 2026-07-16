"""Regresiones de bugs detectados en pruebas manuales con datos reales.

Ver CHANGELOG.md [0.10.1] para el detalle de cada fix.
"""


def test_fecha_iso_no_se_invierte(client, auth_headers):
    """Regresión: '2026-03-08' es 8 de marzo, no 3 de agosto (Bug #1)."""
    csv = "Fecha;Ventas\n2026-03-08;1000\n2026-11-25;2000\n"
    response = client.post(
        "/standardize",
        files={"file": ("iso.csv", csv.encode("utf-8"), "text/csv")},
        headers=auth_headers,
    )
    assert response.status_code == 200
    fechas = [row[0] for row in response.json()["preview"]["despues"]]
    assert "08/03/2026" in fechas
    assert "25/11/2026" in fechas


def test_metrics_expone_costo_cuando_existe(client, auth_headers):
    """Regresión: con columna Costo mapeada y filas pareadas, /metrics debe
    reportar el mapeo y la utilidad — no el banner de "sin costos" (Bug #3,
    cascada del Bug #2: un rango de fechas por defecto fuera del dataset
    dejaba la selección sin filas pareadas y ganancia_neta caía a None)."""
    csv = "Fecha;Ventas;Costo\n01/05/2026;1000;400\n02/05/2026;2000;800\n"
    response = client.post(
        "/metrics",
        files={"file": ("costo.csv", csv.encode("utf-8"), "text/csv")},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mapeo"].get("costo") == "Costo"
    # KPIs de utilidad deben existir cuando hay costo
    assert body["kpis"].get("ganancia_neta") is not None


def test_fuzzy_unifica_pagado_pagada(client, auth_headers):
    """Regresión: 'pagada' (rara relativa a 'pagado', aunque tenga ≥ 3
    apariciones en términos absolutos) debe fusionarse con 'pagado' (Bug #4).

    El preview de /clean solo muestra las primeras filas (PREVIEW_ROWS=8), así
    que con 50 filas la fusión no sería visible ahí — se verifica en
    `fusiones_texto`, el conteo que hace el propio motor de estandarización
    (igual que test_fuzzy_unifica_typos en test_phase7.py)."""
    filas = "\n".join(f"0{i % 9 + 1}/05/2026;Pagado" for i in range(38))
    csv = f"Fecha;Estado\n{filas}\n" + "\n".join(
        f"1{i % 9 + 1}/06/2026;pagada" for i in range(12)
    )
    response = client.post(
        "/clean",
        files={"file": ("estado.csv", csv.encode("utf-8"), "text/csv")},
        data={"apply": "true"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["fusiones_texto"]["total"] >= 1
    ejemplos = [tuple(par) for par in body["fusiones_texto"]["ejemplos"]]
    assert any(
        rare.lower() == "pagada" and canon.lower() == "pagado" for rare, canon in ejemplos
    ), f"Esperaba fusión pagada→pagado, encontré: {ejemplos}"


def test_negativo_contable_exporta_como_numero(client, auth_headers):
    """Regresión: '(12.990)' debe quedar como número -12990, no como texto
    '-12990 (Bug #5)."""
    csv = "Fecha;Movimiento\n01/05/2026;1000\n02/05/2026;(12.990)\n"
    response = client.post(
        "/clean/download",
        files={"file": ("neg.csv", csv.encode("utf-8"), "text/csv")},
        data={"apply": "true", "fmt": "xlsx"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    import io

    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(response.content))
    ws = wb.active
    for row in ws.iter_rows(min_row=2, values_only=False):
        for cell in row:
            if cell.value in (-12990, "-12990"):
                assert isinstance(cell.value, (int, float)), (
                    f"Esperaba número, encontré {type(cell.value).__name__}: {cell.value!r}"
                )
                return
    raise AssertionError("No se encontró la celda -12990 en el archivo exportado")
