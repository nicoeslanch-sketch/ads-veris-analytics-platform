"""Pruebas del pipeline Fase 1: salud, protección JWT y motor de datos."""


def _upload(sample_csv, extra: dict | None = None) -> dict:
    name, content = sample_csv
    data = {"files": {"file": (name, content, "text/csv")}}
    if extra:
        data["data"] = extra
    return data


def test_health_es_publico(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_endpoints_protegidos_rechazan_sin_token(client, sample_csv):
    name, content = sample_csv
    for path in ("/standardize", "/clean", "/metrics"):
        response = client.post(path, files={"file": (name, content, "text/csv")})
        assert response.status_code == 401, path


def test_token_invalido_rechazado(client, sample_csv):
    name, content = sample_csv
    response = client.post(
        "/standardize",
        files={"file": (name, content, "text/csv")},
        headers={"Authorization": "Bearer token-falso"},
    )
    assert response.status_code == 401


def test_standardize_normaliza_texto_fechas_y_numeros(client, auth_headers, sample_csv):
    name, content = sample_csv
    response = client.post(
        "/standardize",
        files={"file": (name, content, "text/csv")},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["filas"] == 92
    assert body["cambios"]["textos_normalizados"] > 0
    assert body["cambios"]["fechas_estandarizadas"] > 0
    assert body["cambios"]["numeros_estandarizados"] > 0
    # Mapeo automático de columnas al esquema del negocio
    assert body["mapeo"]["fecha"] == "Fecha"
    assert body["mapeo"]["monto"] == "Ventas"
    assert body["mapeo"]["costo"] == "Costo"
    assert body["mapeo"]["categoria"] == "Categoría"
    # Fila 2 ("1/5/26", "santiago limitada", "1.200.000") queda unificada
    despues = body["preview"]["despues"][1]
    assert despues[0] == "01/05/2026"
    assert despues[1] == "Santiago Limitada"
    assert despues[4] == "1200000"


def test_clean_detecta_problemas_sin_aplicar(client, auth_headers, sample_csv):
    name, content = sample_csv
    response = client.post(
        "/clean",
        files={"file": (name, content, "text/csv")},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    problems = body["problemas"]
    assert body["resumen"]["aplicado"] is False
    assert problems["duplicados"] >= 1          # fila repetida de Ferretería El Clavo
    assert problems["valores_nulos"] >= 3       # Ventas/Cantidad vacías, fecha "-", N/A
    assert problems["fechas_invalidas"] >= 1    # 31/02/2026
    assert problems["tipos_incorrectos"] >= 1   # Ventas = "abc"
    assert problems["columnas_vacias"] == 1     # columna Notas
    assert problems["valores_fuera_de_rango"] >= 1  # venta de 99.000.000
    assert any(issue["tipo"] == "nulo" for issue in body["preview"]["issues"])
    # Sin aplicar, las filas no cambian
    assert body["resumen"]["filas_antes"] == body["resumen"]["filas_despues"]


def test_clean_aplica_correcciones(client, auth_headers, sample_csv):
    name, content = sample_csv
    response = client.post(
        "/clean",
        files={"file": (name, content, "text/csv")},
        data={"apply": "true", "rules": "{}"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    resumen = body["resumen"]
    assert resumen["aplicado"] is True
    assert resumen["filas_despues"] < resumen["filas_antes"]        # duplicados fuera
    assert resumen["columnas_despues"] == resumen["columnas_antes"] - 1  # Notas eliminada
    assert resumen["calidad_despues"] > resumen["calidad_antes"]


def test_clean_respeta_reglas_desactivadas(client, auth_headers, sample_csv):
    name, content = sample_csv
    response = client.post(
        "/clean",
        files={"file": (name, content, "text/csv")},
        data={"apply": "true", "rules": '{"duplicados": false, "columnas_vacias": false}'},
        headers=auth_headers,
    )
    assert response.status_code == 200
    resumen = response.json()["resumen"]
    assert resumen["filas_despues"] == resumen["filas_antes"]
    assert resumen["columnas_despues"] == resumen["columnas_antes"]


def test_metrics_calcula_kpis_y_evolucion(client, auth_headers, sample_csv):
    name, content = sample_csv
    response = client.post(
        "/metrics",
        files={"file": (name, content, "text/csv")},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    kpis = body["kpis"]
    assert kpis["ingresos_totales"]["valor"] > 0
    assert kpis["transacciones"] > 0
    # Con columna de costo: gastos, utilidad, margen y flujo de caja disponibles
    assert kpis["gastos_totales"]["valor"] > 0
    assert kpis["ganancia_neta"]["valor"] > 0
    assert 0 < kpis["margen_utilidad_pct"]["valor"] < 100
    # Sin rango seleccionado no hay periodo anterior comparable
    assert kpis["ingresos_totales"]["variacion_pct"] is None
    # Evolución abril → mayo → junio con las tres series
    meses = [m["mes"] for m in body["evolucion_mensual"]]
    assert meses == ["2026-04", "2026-05", "2026-06"]
    assert all("gastos" in m and "utilidad" in m for m in body["evolucion_mensual"])
    categorias = {c["nombre"] for c in body["por_categoria"]}
    assert "Servicios" in categorias
    assert all("margen_pct" in c for c in body["por_categoria"])
    assert len(body["top_productos"]) <= 5
    assert body["agrupado_por_canal"] == "sucursal"
    # Proyección a 3 meses a partir de la evolución
    assert len(body["proyeccion"]["meses"]) == 3
    assert body["proyeccion"]["meses"][0]["mes"] == "2026-07"
    # Ratios de balance declarados pero no disponibles todavía
    assert body["indicadores_financieros"]["disponible"] is False
    assert "roa" in body["indicadores_financieros"]["items"]


def test_metrics_filtra_por_periodo(client, auth_headers, sample_csv):
    name, content = sample_csv
    response = client.post(
        "/metrics",
        files={"file": (name, content, "text/csv")},
        data={"date_from": "2026-05-01", "date_to": "2026-05-31"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    total = client.post(
        "/metrics", files={"file": (name, content, "text/csv")}, headers=auth_headers
    ).json()
    # El periodo filtrado tiene menos transacciones que el total
    assert body["kpis"]["transacciones"] < total["kpis"]["transacciones"]
    # Variación calculada contra el periodo anterior equivalente (abril)
    assert body["kpis"]["ingresos_totales"]["variacion_pct"] is not None
    # La evolución mensual sigue mostrando el periodo completo (contexto del gráfico)
    assert len(body["evolucion_mensual"]) == 3
    assert body["periodo"]["desde"] == "2026-05-01"


def test_archivo_invalido_devuelve_400(client, auth_headers):
    response = client.post(
        "/standardize",
        files={"file": ("datos.txt", b"hola", "text/plain")},
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_sin_archivo_ni_storage_path_devuelve_422(client, auth_headers):
    response = client.post("/standardize", headers=auth_headers)
    assert response.status_code == 422
