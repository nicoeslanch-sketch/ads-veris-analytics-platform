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


def test_estandarizacion_unifica_abreviacion_chilena_conocida(client, auth_headers):
    """Regresión: 'Stgo Centro' no se unificaba con 'Santiago Centro' — la
    distancia de edición entre ambas claves es demasiado grande para el
    fuzzy clásico de typos. Es una abreviación chilena conocida (diccionario
    curado): confianza alta, fusión directa (Bug QA-admin #5)."""
    filas = "\n".join(f"0{i % 9 + 1}/05/2026;Santiago Centro;1000" for i in range(20))
    csv = f"Fecha;Sucursal;Ventas\n{filas}\n" + "\n".join(
        f"1{i % 9 + 1}/06/2026;Stgo Centro;500" for i in range(5)
    )
    response = client.post(
        "/clean",
        files={"file": ("sucursales.csv", csv.encode("utf-8"), "text/csv")},
        data={"apply": "true"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["fusiones_texto"]["total"] >= 1
    ejemplos = [tuple(par) for par in body["fusiones_texto"]["ejemplos"]]
    assert any(
        rare.lower() == "stgo centro" and canon.lower() == "santiago centro"
        for rare, canon in ejemplos
    ), f"Esperaba fusión Stgo Centro→Santiago Centro, encontré: {ejemplos}"


def test_estandarizacion_sugiere_truncamiento_desconocido_sin_fusionar(client, auth_headers):
    """Regresión: un truncamiento que NO es una abreviación conocida (ej.
    'distri' de 'Distribucion Norte') no debe fusionarse solo — podría ser
    una categoría real distinta. Se avisa para revisión manual, ni se
    fusiona a ciegas ni se deja pasar callado (Bug QA-admin #5)."""
    # "distri" primero para que quede dentro del preview (PREVIEW_ROWS=5).
    filas_distri = "\n".join(f"0{i % 9 + 1}/06/2026;distri;500" for i in range(5))
    filas_norte = "\n".join(f"0{i % 9 + 1}/05/2026;Distribucion Norte;1000" for i in range(20))
    csv = f"Fecha;Canal;Ventas\n{filas_distri}\n{filas_norte}\n"
    response = client.post(
        "/standardize",
        files={"file": ("canales.csv", csv.encode("utf-8"), "text/csv")},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    despues = [row[1] for row in body["preview"]["despues"]]
    # No se fusiona sola: "distri" debe seguir apareciendo tal cual.
    assert any(v.lower() == "distri" for v in despues)
    avisos = " ".join(body["avisos"])
    assert "distri" in avisos.lower() and "distribucion norte" in avisos.lower()
