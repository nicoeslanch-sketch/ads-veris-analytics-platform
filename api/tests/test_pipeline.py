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
    assert body["filas"] == 33
    assert body["cambios"]["textos_normalizados"] > 0
    assert body["cambios"]["fechas_estandarizadas"] > 0
    assert body["cambios"]["numeros_estandarizados"] > 0
    # Mapeo automático de columnas al esquema del negocio
    assert body["mapeo"]["fecha"] == "Fecha"
    assert body["mapeo"]["monto"] == "Ventas"
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


def test_metrics_calcula_indicadores(client, auth_headers, sample_csv):
    name, content = sample_csv
    response = client.post(
        "/metrics",
        files={"file": (name, content, "text/csv")},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ingresos_totales"] > 0
    assert body["transacciones"] > 0
    assert len(body["evolucion_mensual"]) >= 1
    assert body["evolucion_mensual"][0]["mes"] == "2026-05"
    categorias = {c["nombre"] for c in body["por_categoria"]}
    assert "Servicios" in categorias
    assert len(body["top_productos"]) <= 5


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
