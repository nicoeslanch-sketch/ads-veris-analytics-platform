"""Pruebas de la Fase 9: diccionario universal de roles y biblioteca de prompts."""


# ── Diccionario y matching ────────────────────────────────────────────────────


def test_diccionario_carga_completo():
    from app.engine.dictionary import dictionary_size

    assert dictionary_size() > 10_000  # ≈15.600 claves normalizadas únicas


def test_match_exacto_y_rol_motor():
    from app.engine.dictionary import match_column

    match = match_column("Ventas")
    assert match is not None
    assert match.rol == "monto" and match.rol_motor == "monto"
    assert match.metodo == "exacto" and match.confianza == 1.0

    ingles = match_column("Qty Shipped")
    assert ingles is not None and ingles.rol_motor == "cantidad"


def test_match_contencion_por_tokens():
    from app.engine.dictionary import match_column

    match = match_column("Fecha de Emisión DTE 2026")
    assert match is not None
    assert match.rol == "fecha" and match.metodo in {"exacto", "contencion"}


def test_contencion_no_produce_falsos_positivos_por_substring():
    """'salida' contiene 'id' como substring, pero NO como token: no debe
    clasificarse como identificador."""
    from app.engine.dictionary import match_column

    match = match_column("Salida")
    assert match is None or match.rol != "id"


def test_match_prefijo_sin_separadores():
    from app.engine.dictionary import match_column

    match = match_column("FechaVenta2026")
    assert match is not None and match.rol == "fecha"
    assert match.metodo in {"prefijo", "contencion", "exacto"}


def test_match_fuzzy_corrige_typos():
    from app.engine.dictionary import match_column

    match = match_column("Montto")
    assert match is not None
    assert match.rol == "monto" and match.metodo == "fuzzy"
    assert match.confianza < 1.0


def test_roles_extendidos_sin_motor():
    """RUT, email y precio unitario se reconocen como roles extendidos y NO
    contaminan los roles del motor (un precio unitario sumado como ingreso
    corrompería el dashboard)."""
    from app.engine.dictionary import match_column

    rut = match_column("RUT Cliente")
    assert rut is not None and rut.rol == "rut" and not rut.rol_motor
    email = match_column("Email Contacto")
    assert email is not None and email.rol == "email"
    precio = match_column("Precio Unitario")
    assert precio is not None and precio.rol == "precio_unitario" and not precio.rol_motor


# ── detect_column_roles: diccionario + compatibilidad legacy ─────────────────


def test_motor_prefiere_diccionario_sobre_legacy():
    """Con 'Total Neto' presente, monto va ahí y NO a 'Precio Unitario'
    (el legacy habría tomado 'precio' como monto)."""
    from app.engine.mapping import detect_column_roles

    roles = detect_column_roles(["Precio Unitario", "Total Neto", "Producto"])
    assert roles["monto"] == "Total Neto"
    assert roles["producto"] == "Producto"


def test_compatibilidad_legacy_cuando_no_hay_mejor_columna():
    """Un archivo cuyo único campo de dinero es 'Precio' sigue alimentando
    monto (pasada 2, comportamiento histórico preservado)."""
    from app.engine.mapping import detect_column_roles

    roles = detect_column_roles(["Fecha", "Precio", "Producto"])
    assert roles.get("monto") == "Precio"
    # Y 'Región' sigue cayendo en sucursal si no hay una sucursal real
    roles2 = detect_column_roles(["Fecha", "Ventas", "Región"])
    assert roles2.get("sucursal") == "Región"


def test_columnas_sample_historicas_siguen_mapeando_igual():
    from app.engine.mapping import detect_column_roles

    roles = detect_column_roles(["Fecha", "Cliente", "Producto", "Ventas", "Cantidad", "Sucursal"])
    assert roles == {
        "fecha": "Fecha",
        "cliente": "Cliente",
        "producto": "Producto",
        "monto": "Ventas",
        "cantidad": "Cantidad",
        "sucursal": "Sucursal",
    }


def test_una_columna_no_ocupa_dos_roles():
    from app.engine.mapping import detect_column_roles

    roles = detect_column_roles(["Total Venta"])
    ocupadas = list(roles.values())
    assert len(ocupadas) == len(set(ocupadas)) == 1


# ── Integración en la API ─────────────────────────────────────────────────────


def test_standardize_expone_mapeo_extendido(client, auth_headers):
    csv = "Fecha;RUT Cliente;Total Neto;Precio Unitario\n01/05/2026;76.123.456-7;1000;500\n"
    response = client.post(
        "/standardize",
        files={"file": ("ext.csv", csv.encode("utf-8"), "text/csv")},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    ext = body["mapeo_extendido"]
    assert ext["RUT Cliente"]["rol"] == "rut"
    assert ext["Total Neto"]["rol"] == "monto"
    assert ext["Precio Unitario"]["rol"] == "precio_unitario"
    assert ext["Fecha"]["metodo"] == "exacto"
    assert body["mapeo"]["monto"] == "Total Neto"


def test_reporte_calidad_incluye_rol_extendido(client, auth_headers):
    csv = "Fecha;Email Contacto;Ventas\n01/05/2026;ana@pyme.cl;1000\n02/05/2026;luis@pyme.cl;2000\n"
    response = client.post(
        "/clean",
        files={"file": ("ext2.csv", csv.encode("utf-8"), "text/csv")},
        headers=auth_headers,
    )
    assert response.status_code == 200
    reporte = response.json()["reporte_calidad"]
    assert reporte["Email Contacto"]["rol_extendido"] == "email"
    assert reporte["Email Contacto"]["grupo_rol"] == "contacto"
    assert reporte["Ventas"]["match_diccionario"]["metodo"] == "exacto"


# ── Biblioteca de prompts y costura del clasificador ─────────────────────────


def test_prompt_library_parsea_todas_las_secciones():
    from app.engine.prompt_library import available_sections, classifier_prompt, refine_prompt, system_prompt

    secciones = available_sections()
    assert "PROMPT A" in secciones and "PROMPT B" in secciones and "PROMPT C" in secciones
    assert sum(1 for s in secciones if s.startswith("GRUPO")) == 12
    assert "NUNCA inventes un valor" in system_prompt()
    assert "Clasifica esta columna" in classifier_prompt()
    assert "hallazgos" in refine_prompt()


def test_prompt_for_role_resuelve_grupo():
    from app.engine.prompt_library import fill, prompt_for_role

    dinero = prompt_for_role("monto")
    assert "Imputar 0" in dinero  # regla dura del grupo dinero
    assert prompt_for_role("rut") != "" and "módulo 11" in prompt_for_role("rut")
    relleno = fill("Columna: {COLUMNA}", columna="Ventas")
    assert relleno == "Columna: Ventas"


def test_clasificador_ia_apagado_devuelve_vacio():
    import pandas as pd

    from app.engine.ai_classifier import classify_columns_with_ai

    df = pd.DataFrame({"ColumnaRara": ["a", "b"]})
    assert classify_columns_with_ai(["ColumnaRara"], df) == {}


def test_diccionario_no_rompe_metricas(client, auth_headers):
    """El flujo completo /metrics sigue funcionando con el nuevo mapeo."""
    csv = "Fecha de Emisión;Total Neto;Qty Shipped;Producto\n01/05/2026;1000;2;A\n02/05/2026;2000;3;B\n"
    response = client.post(
        "/metrics",
        files={"file": ("m9.csv", csv.encode("utf-8"), "text/csv")},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mapeo"]["monto"] == "Total Neto"
    assert body["kpis"]["ingresos_totales"]["valor"] == 3000.0
