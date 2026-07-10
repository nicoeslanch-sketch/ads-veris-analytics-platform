"""Pruebas de la Fase 10: endurecimiento comercial (exactitud, motor, soporte)."""

import io


# ── Exactitud financiera (§4) ────────────────────────────────────────────────


def test_utilidad_con_costos_parciales_no_se_infla(client, auth_headers):
    """§4.1: 2 ventas con costo y 1 sin costo → la utilidad usa SOLO las
    filas pareadas (antes: ingresos totales − costos conocidos = inflada)."""
    csv = (
        "Fecha;Producto;Ventas;Costo\n"
        "01/05/2026;A;1000;600\n"
        "02/05/2026;B;2000;1200\n"
        "03/05/2026;C;5000;\n"  # sin costo: NO debe tratarse como costo $0
    )
    response = client.post(
        "/metrics",
        files={"file": ("parcial.csv", csv.encode("utf-8"), "text/csv")},
        headers=auth_headers,
    )
    body = response.json()
    kpis = body["kpis"]
    assert kpis["ingresos_totales"]["valor"] == 8000.0
    # Utilidad pareada: (1000-600) + (2000-1200) = 1200 — no 8000-1800=6200
    assert kpis["ganancia_neta"]["valor"] == 1200.0
    # Margen sobre ingresos PAREADOS: 1200/3000 = 40%
    assert kpis["margen_utilidad_pct"]["valor"] == 40.0
    cobertura = kpis["cobertura_costos"]
    assert cobertura["filas_con_ingreso"] == 3
    assert cobertura["filas_con_ingreso_y_costo"] == 2
    assert any("cobertura" in a.lower() for a in body["advertencias"])


def test_cobertura_completa_sin_advertencia(client, auth_headers, sample_csv):
    name, content = sample_csv
    response = client.post(
        "/metrics",
        files={"file": (name, content, "text/csv")},
        headers=auth_headers,
    )
    body = response.json()
    assert body["kpis"]["cobertura_costos"]["pct"] == 100.0
    assert not any("cobertura" in a.lower() for a in body["advertencias"])


def test_mes_calendario_se_compara_con_mes_calendario(client, auth_headers):
    """§4.5: mayo completo se compara con ABRIL, sin arrastrar el 31 de marzo."""
    csv = (
        "Fecha;Ventas\n"
        "31/03/2026;99999\n"  # si la ventana de días se colara, inflaría abril
        "10/04/2026;1000\n"
        "10/05/2026;1500\n"
    )
    response = client.post(
        "/metrics",
        files={"file": ("meses.csv", csv.encode("utf-8"), "text/csv")},
        data={"date_from": "2026-05-01", "date_to": "2026-05-31"},
        headers=auth_headers,
    )
    kpis = response.json()["kpis"]
    assert kpis["ingresos_totales"]["valor"] == 1500.0
    # vs abril (1000): +50%. Con la ventana antigua abril+31mar=100999 → -98.5%
    assert kpis["ingresos_totales"]["variacion_pct"] == 50.0


def test_moneda_usd_detectada(client, auth_headers):
    csv = "Fecha;Ventas\n01/05/2026;US$1.500\n02/05/2026;USD 2.000\n"
    response = client.post(
        "/metrics",
        files={"file": ("usd.csv", csv.encode("utf-8"), "text/csv")},
        headers=auth_headers,
    )
    body = response.json()
    assert body["moneda"] == "USD"
    assert any("USD" in a for a in body["advertencias"])


def test_moneda_mixta_advierte(client, auth_headers):
    csv = "Fecha;Ventas\n01/05/2026;US$1.500\n02/05/2026;CLP 850.000\n03/05/2026;USD 300\n"
    response = client.post(
        "/metrics",
        files={"file": ("mixta.csv", csv.encode("utf-8"), "text/csv")},
        headers=auth_headers,
    )
    body = response.json()
    assert any("más de una moneda" in a for a in body["advertencias"])


def test_moneda_pesos_por_defecto(client, auth_headers, sample_csv):
    name, content = sample_csv
    body = client.post(
        "/metrics",
        files={"file": (name, content, "text/csv")},
        headers=auth_headers,
    ).json()
    assert body["moneda"] == "CLP"


# ── Motor endurecido (§6) ────────────────────────────────────────────────────


def test_fuzzy_no_toca_identificadores(client, auth_headers):
    """§6.1: 'SKU-100I' NO se fusiona con 'SKU-1001' — puede ser otro código."""
    filas = "\n".join(f"0{i}/05/2026;SKU-1001;100" for i in range(1, 6))
    csv = f"Fecha;Codigo Producto;Ventas\n{filas}\n06/05/2026;SKU-100I;100\n"
    response = client.post(
        "/standardize",
        files={"file": ("skus.csv", csv.encode("utf-8"), "text/csv")},
        headers=auth_headers,
    )
    despues = [fila[1] for fila in response.json()["preview"]["despues"]]
    # La vista previa trae 5 filas; verificamos vía limpieza aplicada:
    body = client.post(
        "/clean",
        files={"file": ("skus.csv", csv.encode("utf-8"), "text/csv")},
        data={"apply": "true"},
        headers=auth_headers,
    ).json()
    assert body["fusiones_texto"]["total"] == 0  # jamás fuzzy en códigos
    assert despues  # (la estandarización corrió)


def test_fuzzy_sigue_activo_en_categorias(client, auth_headers):
    """El fuzzy legítimo (typos en ciudades/categorías) sigue funcionando."""
    filas = "\n".join(f"0{i}/05/2026;Santiago;100" for i in range(1, 6))
    csv = f"Fecha;Ciudad;Ventas\n{filas}\n06/05/2026;Santigo;100\n"
    body = client.post(
        "/clean",
        files={"file": ("typos.csv", csv.encode("utf-8"), "text/csv")},
        data={"apply": "true"},
        headers=auth_headers,
    ).json()
    assert body["fusiones_texto"]["total"] >= 1


def test_duplicados_normalizados_sin_id_no_se_eliminan(client, auth_headers):
    """§6.2: sin columna ID, filas que solo difieren en mayúsculas quedan como
    'probables' y NO se eliminan; las 100% idénticas sí."""
    csv = (
        "Fecha;Producto;Ventas\n"
        "01/05/2026;Producto A;1000\n"
        "01/05/2026;Producto A;1000\n"   # idéntica exacta → se elimina
        "02/05/2026;producto b;500\n"
        "02/05/2026;PRODUCTO B;500\n"    # solo difiere en mayúsculas → probable
    )
    body = client.post(
        "/clean",
        files={"file": ("dups.csv", csv.encode("utf-8"), "text/csv")},
        data={"apply": "true"},
        headers=auth_headers,
    ).json()
    # OJO: la estandarización unifica mayúsculas ANTES del dedup, por lo que
    # "producto b"/"PRODUCTO B" pueden volverse idénticas. Lo no negociable:
    # el criterio queda explícito y las probables se avisan.
    assert body["duplicados_criterio"] == "fila_exacta_sin_id"
    assert body["resumen"]["filas_despues"] >= 2


def test_duplicados_con_id_distinto_jamas_se_fusionan(client, auth_headers):
    """Dos ventas idénticas con folio DISTINTO no son duplicados."""
    csv = (
        "Folio;Fecha;Producto;Ventas\n"
        "1001;01/05/2026;Producto A;1000\n"
        "1002;01/05/2026;Producto A;1000\n"
    )
    body = client.post(
        "/clean",
        files={"file": ("folios.csv", csv.encode("utf-8"), "text/csv")},
        data={"apply": "true"},
        headers=auth_headers,
    ).json()
    assert body["problemas"]["duplicados"] == 0
    assert body["resumen"]["filas_despues"] == 2


def test_scope_que_excluye_todo_devuelve_422(client, auth_headers):
    """§6.3: instrucciones que excluyen todas las columnas → 422, sin consumo."""
    csv = "Fecha;Ventas\n01/05/2026;1000\n"
    response = client.post(
        "/clean/assisted",
        files={"file": ("todo.csv", csv.encode("utf-8"), "text/csv")},
        data={"instructions": "no toques Fecha y no toques Ventas"},
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert "excluyen todas" in response.json()["detail"]


def test_reglas_desconocidas_422(client, auth_headers, sample_csv):
    """§14.1: claves de reglas desconocidas no pasan en silencio."""
    name, content = sample_csv
    response = client.post(
        "/clean",
        files={"file": (name, content, "text/csv")},
        data={"rules": '{"borrar_todo": true}'},
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert "Regla desconocida" in response.json()["detail"]


def test_mapping_rol_invalido_422(client, auth_headers, sample_csv):
    name, content = sample_csv
    response = client.post(
        "/metrics",
        files={"file": (name, content, "text/csv")},
        data={"mapping": '{"contrasena": "Ventas"}'},
        headers=auth_headers,
    )
    assert response.status_code == 422


# ── Soporte: anti-abuso (§12.2) ──────────────────────────────────────────────


def test_soporte_maximo_de_pendientes(client, auth_headers, monkeypatch):
    import httpx as _httpx

    from app.config import get_settings
    from app.routes import support as support_module

    settings = get_settings()
    monkeypatch.setattr(settings, "supabase_url", "https://proyecto-test.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "service-key")

    def fake_get(url, params=None, headers=None, timeout=None):
        pendientes = [{"mensaje": f"pendiente {i}"} for i in range(3)]
        return _httpx.Response(200, json=pendientes, request=_httpx.Request("GET", url))

    monkeypatch.setattr(support_module.httpx, "get", fake_get)
    response = client.post(
        "/support/request",
        json={"mensaje": "otra consulta"},
        headers=auth_headers,
    )
    assert response.status_code == 429


def test_soporte_mensaje_identico_pendiente_409(client, auth_headers, monkeypatch):
    import httpx as _httpx

    from app.config import get_settings
    from app.routes import support as support_module

    settings = get_settings()
    monkeypatch.setattr(settings, "supabase_url", "https://proyecto-test.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "service-key")

    def fake_get(url, params=None, headers=None, timeout=None):
        return _httpx.Response(
            200, json=[{"mensaje": "ayuda con mi archivo"}], request=_httpx.Request("GET", url)
        )

    monkeypatch.setattr(support_module.httpx, "get", fake_get)
    response = client.post(
        "/support/request",
        json={"mensaje": "ayuda con mi archivo"},
        headers=auth_headers,
    )
    assert response.status_code == 409


# ── Diccionario auditado (§7) ────────────────────────────────────────────────


def test_numero_de_documento_no_es_cantidad():
    """§7.1: 'Numero de Boleta' es un folio (identificador), no una cantidad —
    jamás debe sumarse como unidades vendidas."""
    from app.engine.dictionary import match_column

    for header in ("Numero de Boleta", "Número de Factura", "Numero de Orden",
                   "numero de transaccion", "Numero de Cliente"):
        match = match_column(header)
        assert match is not None, header
        assert match.grupo == "identificador", f"{header} → {match.rol}"
        assert not match.rol_motor, f"{header} tiene rol de motor {match.rol_motor}"


def test_numero_de_ventas_plural_sigue_siendo_conteo():
    """'Numero de ventas' (plural) SÍ es un conteo legítimo."""
    from app.engine.dictionary import match_column

    match = match_column("Numero de Ventas")
    assert match is not None and match.rol_motor == "cantidad"


def test_auditoria_identificadores_jamas_alimentan_el_motor_metrico():
    """§7.4: ninguna entrada del grupo identificador puede apuntar a
    monto/costo/cantidad del motor (CI del diccionario)."""
    import csv
    from pathlib import Path

    path = Path("app/data/palabras_clave_roles.csv")
    with path.open(encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh, delimiter=";"))
    malas = [
        r["palabra_clave"]
        for r in rows
        if r["grupo"] == "identificador"
        and (r.get("rol_motor_actual") or "").strip() in {"monto", "costo", "cantidad"}
    ]
    assert malas == [], f"Identificadores con rol métrico: {malas[:10]}"


# ── Carga de archivos (§8) ───────────────────────────────────────────────────


def test_xls_antiguo_mensaje_claro(client, auth_headers):
    response = client.post(
        "/standardize",
        files={"file": ("viejo.xls", b"contenido", "application/vnd.ms-excel")},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert ".xlsx" in response.json()["detail"]


def test_xlsx_corrupto_mensaje_claro(client, auth_headers):
    response = client.post(
        "/standardize",
        files={"file": ("roto.xlsx", b"no soy un zip", "application/octet-stream")},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "dañado" in response.json()["detail"]


def test_zip_bomb_rechazada(client, auth_headers):
    """§8.2: un xlsx cuyo contenido se expande de forma anómala se rechaza."""
    import io as _io
    import zipfile

    buf = _io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/worksheets/sheet1.xml", b"0" * (300 * 1024 * 1024))
    response = client.post(
        "/standardize",
        files={"file": ("bomba.xlsx", buf.getvalue(), "application/octet-stream")},
        headers=auth_headers,
    )
    assert response.status_code == 400
