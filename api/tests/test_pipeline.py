"""Pruebas del pipeline Fase 1: salud, protección JWT y motor de datos."""

import asyncio
import io
import zipfile
from types import SimpleNamespace

import pandas as pd


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
    for path in ("/standardize", "/clean", "/clean/download", "/metrics"):
        response = client.post(path, files={"file": (name, content, "text/csv")})
        assert response.status_code == 401, path


def test_preload_estandarizacion_prepara_varias_hojas_sin_snapshots(
    client, auth_headers
):
    source = io.BytesIO()
    with pd.ExcelWriter(source, engine="openpyxl") as writer:
        pd.DataFrame({"Monto": ["1.000"], "Fecha": ["01/01/2026"]}).to_excel(
            writer, sheet_name="Enero", index=False
        )
        pd.DataFrame({"Monto": ["2.000"], "Fecha": ["01/02/2026"]}).to_excel(
            writer, sheet_name="Febrero", index=False
        )

    response = client.post(
        "/standardize/preload",
        files={"file": ("ventas.xlsx", source.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"sheets": '["Enero", "Febrero"]'},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["hojas_preparadas"] == ["Enero", "Febrero"]
    assert "revision" not in response.json()


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
    # Fase 12: limpiar ya no elimina filas sin una decisión separada.
    assert resumen["filas_despues"] == resumen["filas_antes"]
    assert body["correcciones"]["filas_duplicadas_a_eliminar"] == 0
    # Fase 12b §9: la columna vacía se DETECTA pero no se elimina por defecto
    assert resumen["columnas_despues"] == resumen["columnas_antes"]
    assert resumen["calidad_despues"] >= resumen["calidad_antes"]


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


def test_clean_download_basico_devuelve_403(client, auth_headers, sample_csv, monkeypatch):
    # Fase 8: enforcement encendido por defecto. Con Supabase configurado y
    # plan básico (sin is_admin), descargar la base limpia responde 403 con
    # CTA a Planes. Sin Supabase la puerta hace fail-open (dev local).
    from app import capabilities
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "supabase_url", "https://proyecto-test.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "service-key")
    monkeypatch.setattr(
        capabilities, "get_profile_flags", lambda user_id, s: ("basico", False)
    )
    name, content = sample_csv
    response = client.post(
        "/clean/download",
        files={"file": (name, content, "text/csv")},
        headers=auth_headers,
    )
    assert response.status_code == 403
    assert "Plan Analista" in response.json()["detail"]


def test_clean_download_analista_exporta_csv_seguro(client, auth_headers, monkeypatch):
    from app.routes import pipeline as pipeline_module

    monkeypatch.setattr(
        pipeline_module,
        "require_capability_for_user",
        lambda user_id, capability, settings: "gold",
    )
    content = "Fecha;Cliente;Ventas\n01/05/2026;=2+2;1000\n".encode("utf-8")
    response = client.post(
        "/clean/download",
        files={"file": ("formulas.csv", content, "text/csv")},
        data={"format": "csv"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.headers["content-disposition"].endswith(
        'filename="formulas_limpio_con_auditoria.zip"'
    )
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert b"'=2+2" in archive.read("formulas_limpio.csv")
        assert "formulas_auditoria.csv" in archive.namelist()


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
    # Fase 12b §24: hasta 12 productos (el Resumen muestra 5; Explorar, más)
    assert len(body["top_productos"]) <= 12
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


# ── Seguridad multiusuario: storage_path ajeno se rechaza ──


def test_storage_path_de_otro_usuario_devuelve_403(client, auth_headers):
    """La API descarga de Storage con service_role (salta RLS): la propiedad
    del archivo se valida contra el user_id del JWT antes de descargar."""
    for path in ("/standardize", "/clean", "/metrics"):
        response = client.post(
            path,
            data={"storage_path": "otro-usuario-999/archivo.csv"},
            headers=auth_headers,
        )
        assert response.status_code == 403, path


def test_storage_path_rechaza_traversal_y_codificados(client, auth_headers):
    """service_role no debe descargar una ruta distinta a la validada."""
    dangerous_paths = [
        "user-test-123/../otro-usuario-999/archivo.csv",
        "user-test-123/%2e%2e/otro-usuario-999/archivo.csv",
        "user-test-123/.%2e/otro-usuario-999/archivo.csv",
        "user-test-123/%252e%252e/otro-usuario-999/archivo.csv",
        "user-test-123/%2F/otro-usuario-999/archivo.csv",
        "user-test-123\\archivo.csv",
    ]
    for storage_path in dangerous_paths:
        response = client.post(
            "/standardize",
            data={"storage_path": storage_path},
            headers=auth_headers,
        )
        assert response.status_code == 403, storage_path


def test_storage_path_propio_pasa_validacion_de_propiedad(client, auth_headers):
    # El path pertenece al usuario del token (user-test-123). Sin Supabase
    # configurado en tests, el siguiente paso (descarga) responde 503 — lo que
    # prueba que la validación de propiedad se superó (no 403).
    response = client.post(
        "/standardize",
        data={"storage_path": "user-test-123/ventas.csv"},
        headers=auth_headers,
    )
    assert response.status_code == 503


def test_storage_reutiliza_bytes_del_mismo_archivo_multihoja(monkeypatch):
    """Cada hoja reutiliza el XLSX ya descargado sin saltarse la validación."""
    from app.routes import pipeline as pipeline_module

    calls: list[str] = []
    content = b"archivo-xlsx-simulado"

    def fake_download(storage_path: str) -> bytes:
        calls.append(storage_path)
        return content

    pipeline_module._storage_content_cache_clear()
    monkeypatch.setattr(pipeline_module, "download_from_storage", fake_download)
    user = SimpleNamespace(id="user-test-123")
    storage_path = "user-test-123/prueba-multihoja.xlsx"

    try:
        first = asyncio.run(pipeline_module._read_input(None, storage_path, user))
        second = asyncio.run(pipeline_module._read_input(None, storage_path, user))
    finally:
        pipeline_module._storage_content_cache_clear()

    assert first == ("prueba-multihoja.xlsx", content)
    assert second == first
    assert calls == [storage_path]


# ── CORS: preflight del navegador ──


def test_cors_preflight_origen_permitido(client):
    response = client.options(
        "/standardize",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_preflight_deployment_vercel_permitido(client):
    origin = "https://ads-veris-analytics-platform-bbk6xfq20.vercel.app"
    response = client.options(
        "/standardize",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_cors_preflight_origen_no_permitido_sin_header_cors(client):
    response = client.options(
        "/standardize",
        headers={
            "Origin": "https://sitio-malicioso.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in response.headers


# ── Asistente IA: protección y configuración ──


def test_ai_summary_requiere_token(client):
    response = client.post("/ai/summary", json={"metrics": {}})
    assert response.status_code == 401


def test_ai_summary_sin_api_key_devuelve_503(client, auth_headers):
    # En tests no hay ANTHROPIC_API_KEY: el endpoint debe fallar con un
    # mensaje claro, nunca con un 500 opaco ni con detalles internos del
    # servidor (el nombre de la variable de entorno no es asunto del usuario).
    response = client.post("/ai/summary", json={"metrics": {}}, headers=auth_headers)
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "ANTHROPIC_API_KEY" not in detail
    assert detail == "El asistente no está disponible en este momento. Intenta de nuevo más tarde."


def test_ai_summary_error_del_proveedor_no_expone_detalle_crudo(monkeypatch, client, auth_headers):
    """Regresión: un fallo de Anthropic (ej. sin saldo) devolvía el texto
    crudo del proveedor (tipo de error, mensaje, request_id) directo al
    usuario. Debe verse un mensaje genérico; el detalle real solo va a logs."""
    import httpx
    from anthropic import APIStatusError

    from app.routes import ai as ai_routes

    class _FakeMessages:
        async def create(self, **kwargs):
            request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
            response = httpx.Response(
                400,
                request=request,
                json={"error": {"type": "invalid_request_error", "message": "secret detail"}},
            )
            raise APIStatusError(
                "Your credit balance is too low to access the Anthropic API. "
                "request_id req_super_secreto_12345",
                response=response,
                body=None,
            )

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(ai_routes, "_client", lambda settings: _FakeClient())
    monkeypatch.setattr(ai_routes.quota, "check_quota", lambda user_id, settings: None)
    monkeypatch.setattr(
        ai_routes, "require_capability_for_user", lambda user_id, cap, settings: "basico"
    )

    response = client.post("/ai/summary", json={"metrics": {}}, headers=auth_headers)
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "credit balance" not in detail
    assert "request_id" not in detail
    assert "req_super_secreto_12345" not in detail
    assert detail == "El asistente no está disponible en este momento. Intenta de nuevo más tarde."


# ── Conector Google Sheets (Fase 6) ──


def test_connector_sheets_requiere_token(client):
    response = client.post("/connectors/sheets", json={"url": "https://docs.google.com/spreadsheets/d/abc"})
    assert response.status_code == 401


def test_connector_sheets_rechaza_url_que_no_es_google_sheets(client, auth_headers):
    for url in ("https://ejemplo.com/archivo.csv", "http://localhost/interno", "no-es-url"):
        response = client.post("/connectors/sheets", json={"url": url}, headers=auth_headers)
        assert response.status_code == 400, url
        assert "Google Sheets" in response.json()["detail"]


def test_connector_sheets_rechaza_url_demasiado_larga(client, auth_headers):
    response = client.post(
        "/connectors/sheets",
        json={"url": "https://docs.google.com/spreadsheets/d/" + "a" * 2500},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_connector_sheets_importa_csv(client, auth_headers, monkeypatch):
    from app.routes import connectors as connectors_module

    def fake_download(sheet_id: str, gid: str) -> tuple[str, bytes]:
        assert sheet_id == "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcd"
        assert gid == "42"
        return "Ventas 2026 - Hoja1.csv", "Fecha;Ventas\n01/05/2026;1000\n".encode("utf-8")

    monkeypatch.setattr(connectors_module, "_download_sheet_csv", fake_download)
    response = client.post(
        "/connectors/sheets",
        json={
            "url": "https://docs.google.com/spreadsheets/d/"
            "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcd/edit#gid=42"
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["filename"].endswith(".csv")
    assert "Fecha;Ventas" in body["csv"]


def test_connector_sheets_sanitiza_filename(client, auth_headers, monkeypatch):
    from app.routes import connectors as connectors_module

    def fake_download(sheet_id: str, gid: str) -> tuple[str, bytes]:
        return "../Ventas<script>2026</script>" + ("x" * 120) + ".csv", b"Fecha,Ventas\n01/05/2026,1000\n"

    monkeypatch.setattr(connectors_module, "_download_sheet_csv", fake_download)
    response = client.post(
        "/connectors/sheets",
        json={"url": "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz01234567/edit"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    filename = response.json()["filename"]
    assert filename.endswith(".csv")
    assert "/" not in filename
    assert "<" not in filename
    assert len(filename) <= 84


def test_connector_sheets_hoja_privada_da_400(client, auth_headers, monkeypatch):
    from fastapi import HTTPException

    from app.routes import connectors as connectors_module

    def fake_download(sheet_id: str, gid: str):
        raise HTTPException(status_code=400, detail="La hoja no es pública. ...")

    monkeypatch.setattr(connectors_module, "_download_sheet_csv", fake_download)
    response = client.post(
        "/connectors/sheets",
        json={"url": "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz01234567/edit"},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "pública" in response.json()["detail"]


# ── Guard de tamaño del contexto de métricas en /ai/* ──


def test_ai_metrics_gigante_devuelve_413(client, auth_headers):
    gigante = {"basura": ["x" * 1000] * 300}  # ~300 KB
    response = client.post("/ai/summary", json={"metrics": gigante}, headers=auth_headers)
    assert response.status_code == 413


def test_ai_recommendation_requiere_token_y_api_key(client, auth_headers):
    assert client.post("/ai/recommendation", json={"metrics": {}}).status_code == 401
    response = client.post(
        "/ai/recommendation",
        json={"metrics": {}, "hallazgos": ["Ingresos subieron 12%"], "analisis": "prueba"},
        headers=auth_headers,
    )
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "ANTHROPIC_API_KEY" not in detail
    assert detail == "El asistente no está disponible en este momento. Intenta de nuevo más tarde."


# ── Límite de tamaño también para archivos que vienen de Storage ──


def test_storage_descarga_grande_devuelve_413(client, auth_headers, monkeypatch):
    """La API descarga de Storage sin límite del navegador: el tope de 15 MB
    debe aplicarse igual que en multipart para proteger la memoria del server."""
    from app import storage as storage_module
    from app.routes import pipeline as pipeline_module

    def fake_download(storage_path: str) -> bytes:
        raise storage_module._too_large()

    monkeypatch.setattr(pipeline_module, "download_from_storage", fake_download)
    response = client.post(
        "/standardize",
        data={"storage_path": "user-test-123/enorme.xlsx"},
        headers=auth_headers,
    )
    assert response.status_code == 413
    assert "15 MB" in response.json()["detail"]


# ── Cuotas de IA por plan (SPEC §9) ──


def test_capabilities_basico_vs_analista():
    from app.capabilities import Capability, normalize_plan, plan_allows

    # Fase 7: 'gold' ya es el tercer plan; el ex-gold vive migrado a 'analista'.
    assert normalize_plan("analista") == "analista"
    assert normalize_plan("gold") == "gold"
    assert normalize_plan(None) == "basico"
    assert plan_allows("basico", Capability.ASK_DATA_AI) is True
    assert plan_allows("basico", Capability.DOWNLOAD_CLEAN_DATASET) is False
    assert plan_allows("basico", Capability.AI_CLEANING) is False
    assert plan_allows("analista", Capability.DOWNLOAD_CLEAN_DATASET) is True
    assert plan_allows("analista", Capability.AI_CLEANING) is True
    assert plan_allows("analista", Capability.CONNECT_SQL) is False
    # Gold hereda todo Analista + lo en construcción
    assert plan_allows("gold", Capability.AI_CLEANING) is True
    assert plan_allows("gold", Capability.CONNECT_SQL) is True
    assert plan_allows("gold", Capability.COMMUNITY_ACCESS) is True


def test_cuota_ia_agotada_devuelve_429(monkeypatch):
    from fastapi import HTTPException

    from app import quota
    from app.config import Settings

    settings = Settings(
        supabase_url="https://proyecto-test.supabase.co",
        supabase_service_role_key="service-key-de-prueba",
        ai_monthly_limit_basico=5,
    )
    monkeypatch.setattr(
        quota, "get_profile_flags", lambda user_id, s: ("basico", False)
    )
    monkeypatch.setattr(quota, "count_month_usage", lambda user_id, s, kinds=None: 5)
    try:
        quota.check_quota("user-x", settings)
        raise AssertionError("Debió lanzar 429")
    except HTTPException as exc:
        assert exc.status_code == 429
        assert "límite mensual" in exc.detail

    # Con cupo disponible devuelve el estado
    monkeypatch.setattr(quota, "count_month_usage", lambda user_id, s, kinds=None: 4)
    info = quota.check_quota("user-x", settings)
    assert info == {
        "plan": "basico",
        "usadas": 4,
        "limite": 5,
        "ilimitado": False,
    }


def test_cuota_ia_sin_supabase_no_bloquea(client, auth_headers):
    # En dev sin Supabase el gating se desactiva y /ai/usage lo declara.
    response = client.get("/ai/usage", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["disponible"] is False
    assert client.get("/ai/usage").status_code == 401


# ── JWT ES256 (Supabase moderno) validado vía JWKS ──


def test_jwt_es256_valido_via_jwks(client, sample_csv, monkeypatch):
    """Simula el flujo real de Supabase con claves ECC/P-256: se firma un token
    con una clave EC y se sirve la pública por un JWKS client falso."""
    import time

    import jwt as pyjwt
    from cryptography.hazmat.primitives.asymmetric import ec

    from app import auth as auth_module
    from app.config import get_settings

    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    class FakeSigningKey:
        key = public_key

    class FakeJWKSClient:
        def get_signing_key_from_jwt(self, token):
            return FakeSigningKey()

    monkeypatch.setattr(auth_module, "_jwks_client", lambda url: FakeJWKSClient())
    # El modo JWKS exige SUPABASE_URL configurada (Settings está cacheado)
    settings = get_settings()
    monkeypatch.setattr(settings, "supabase_url", "https://proyecto-test.supabase.co")

    token = pyjwt.encode(
        {
            "sub": "user-es256",
            "email": "es256@adsveris.cl",
            "aud": "authenticated",
            "exp": int(time.time()) + 3600,
        },
        private_key,
        algorithm="ES256",
    )
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["id"] == "user-es256"

    # Un token ES256 firmado con OTRA clave debe rechazarse
    other_key = ec.generate_private_key(ec.SECP256R1())
    bad_token = pyjwt.encode(
        {"sub": "x", "aud": "authenticated", "exp": int(time.time()) + 3600},
        other_key,
        algorithm="ES256",
    )
    assert client.get("/me", headers={"Authorization": f"Bearer {bad_token}"}).status_code == 401


def test_display_filename_quita_prefijo_de_storage():
    """El path de Storage antepone Date.now()_ (lib/datasets.ts) para evitar
    colisiones; el nombre visible al usuario debe ser el original, sin ese
    prefijo técnico (bug reportado en pruebas manuales del flujo de Reportes)."""
    from app.routes.pipeline import _display_filename

    assert (
        _display_filename("1784231134931_base3_distribuidora_grande.xlsx")
        == "base3_distribuidora_grande.xlsx"
    )
    # Nombres legítimos que empiezan con números cortos no se tocan.
    assert _display_filename("2026_ventas.csv") == "2026_ventas.csv"
    assert _display_filename("ventas.csv") == "ventas.csv"
