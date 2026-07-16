"""Pruebas de la Fase 7: planes, limpieza dirigida y motor profesional."""

import io


# ── Capacidades y enforcement ─────────────────────────────────────────────────


def test_enforcement_apagado_no_consulta_la_red(monkeypatch):
    """Con PLAN_ENFORCEMENT off (default Fase 7) la puerta deja pasar sin
    tocar Supabase — aunque get_plan explote."""
    from app import capabilities
    from app.capabilities import Capability, require_capability_for_user
    from app.config import Settings

    settings = Settings(plan_enforcement=False)

    def _boom(user_id, s):
        raise AssertionError("No debe consultar el plan con enforcement off")

    monkeypatch.setattr(capabilities, "get_plan", _boom)
    result = require_capability_for_user("user-x", Capability.AI_CLEANING, settings)
    assert result == "sin_enforcement"


def _enforced_settings():
    from app.config import Settings

    # Con Supabase "configurado": sin credenciales la puerta hace fail-open (dev).
    return Settings(
        plan_enforcement=True,
        supabase_url="https://proyecto-test.supabase.co",
        supabase_service_role_key="service-key-de-prueba",
    )


def test_enforcement_encendido_bloquea_basico(monkeypatch):
    from fastapi import HTTPException

    from app import capabilities
    from app.capabilities import Capability, require_capability_for_user

    settings = _enforced_settings()
    monkeypatch.setattr(capabilities, "get_profile_flags", lambda user_id, s: ("basico", False))
    try:
        require_capability_for_user("user-x", Capability.AI_CLEANING, settings)
        raise AssertionError("Debió lanzar 403")
    except HTTPException as exc:
        assert exc.status_code == 403
        assert "Planes" in exc.detail

    monkeypatch.setattr(capabilities, "get_profile_flags", lambda user_id, s: ("analista", False))
    assert require_capability_for_user("user-x", Capability.AI_CLEANING, settings) == "analista"


def test_enforcement_sin_supabase_fail_open():
    """Sin Supabase configurado (dev local) la puerta no bloquea a nadie."""
    from app.capabilities import Capability, require_capability_for_user
    from app.config import Settings

    settings = Settings(plan_enforcement=True)
    result = require_capability_for_user("user-x", Capability.AI_CLEANING, settings)
    assert result == "sin_supabase"


def test_admin_pasa_todas_las_puertas(monkeypatch):
    """Fase 8: la cuenta administradora accede a todo sin depender del plan."""
    from app import capabilities
    from app.capabilities import Capability, require_capability_for_user

    settings = _enforced_settings()
    monkeypatch.setattr(capabilities, "get_profile_flags", lambda user_id, s: ("basico", True))
    plan = require_capability_for_user("admin-x", Capability.DOWNLOAD_CLEAN_DATASET, settings)
    assert plan == "basico"  # el plan no importa: is_admin manda


def test_reportes_disponibles_para_basico():
    """Fase 8: el reporte PDF del negocio es para todos los planes; lo que
    exige Analista es descargar la base LIMPIA."""
    from app.capabilities import Capability, plan_allows

    assert plan_allows("basico", Capability.DOWNLOAD_REPORTS) is True
    assert plan_allows("basico", Capability.DOWNLOAD_CLEAN_DATASET) is False
    assert plan_allows("analista", Capability.DOWNLOAD_CLEAN_DATASET) is True


# ── Cuota de limpieza dirigida (10 Analista / 25 Gold + addons) ─────────────


def _quota_settings():
    from app.config import Settings

    return Settings(
        supabase_url="https://proyecto-test.supabase.co",
        supabase_service_role_key="service-key-de-prueba",
        ai_cleaning_monthly_limit=10,
        ai_cleaning_monthly_limit_gold=25,
    )


def test_cuota_limpieza_agotada_sin_addons_429(monkeypatch):
    from fastapi import HTTPException

    from app import quota

    settings = _quota_settings()
    monkeypatch.setattr(quota, "get_profile_flags", lambda user_id, s: ("analista", False))
    monkeypatch.setattr(quota, "count_month_usage", lambda user_id, s, kinds=None: 10)
    monkeypatch.setattr(quota, "addons_balance", lambda user_id, s: 0)
    try:
        quota.check_cleaning_quota("user-x", settings)
        raise AssertionError("Debió lanzar 429")
    except HTTPException as exc:
        assert exc.status_code == 429
        assert "Planes" in exc.detail


def test_cuota_limpieza_agotada_con_addons_consume_token(monkeypatch):
    from app import quota

    settings = _quota_settings()
    monkeypatch.setattr(quota, "get_profile_flags", lambda user_id, s: ("analista", False))
    monkeypatch.setattr(quota, "count_month_usage", lambda user_id, s, kinds=None: 10)
    monkeypatch.setattr(quota, "addons_balance", lambda user_id, s: 3)
    info = quota.check_cleaning_quota("user-x", settings)
    assert info["consume_addon"] is True
    assert info["addons"] == 3


def test_cuota_limpieza_con_base_disponible_no_consume_addon(monkeypatch):
    from app import quota

    settings = _quota_settings()
    monkeypatch.setattr(quota, "get_profile_flags", lambda user_id, s: ("basico", False))
    monkeypatch.setattr(quota, "count_month_usage", lambda user_id, s, kinds=None: 1)
    monkeypatch.setattr(quota, "addons_balance", lambda user_id, s: 0)
    info = quota.check_cleaning_quota("user-x", settings)
    assert info["consume_addon"] is False
    assert info["usadas_mes"] == 1 and info["base"] == 10


def test_cuota_limpieza_gold_tiene_base_mayor(monkeypatch):
    """Fase 8: la base mensual depende del plan (10 Analista / 25 Gold)."""
    from app import quota

    settings = _quota_settings()
    monkeypatch.setattr(quota, "get_profile_flags", lambda user_id, s: ("gold", False))
    monkeypatch.setattr(quota, "count_month_usage", lambda user_id, s, kinds=None: 12)
    monkeypatch.setattr(quota, "addons_balance", lambda user_id, s: 0)
    info = quota.check_cleaning_quota("user-x", settings)
    assert info["base"] == 25
    assert info["consume_addon"] is False  # 12 < 25: aún dentro de la base


def test_cuota_limpieza_admin_nunca_se_agota(monkeypatch):
    """Fase 8: el administrador no consume addons ni recibe 429."""
    from app import quota

    settings = _quota_settings()
    monkeypatch.setattr(quota, "get_profile_flags", lambda user_id, s: ("basico", True))
    monkeypatch.setattr(quota, "count_month_usage", lambda user_id, s, kinds=None: 999)
    monkeypatch.setattr(quota, "addons_balance", lambda user_id, s: 0)
    info = quota.check_cleaning_quota("admin-x", settings)
    assert info["consume_addon"] is False


def test_cuota_insights_no_cuenta_limpieza(monkeypatch):
    """El cupo de insights filtra por kind: los intentos de limpieza no lo gastan."""
    from app import quota

    captured = {}

    def fake_count(user_id, s, kinds=quota.INSIGHT_KINDS):
        captured["kinds"] = kinds
        return 0

    settings = _quota_settings()
    monkeypatch.setattr(
        quota, "get_profile_flags", lambda user_id, s: ("basico", False)
    )
    monkeypatch.setattr(quota, "count_month_usage", fake_count)
    quota.check_quota("user-x", settings)
    assert captured["kinds"] == quota.INSIGHT_KINDS
    assert "cleaning" not in captured["kinds"]


def test_cuota_insights_admin_es_ilimitada(monkeypatch):
    """El administrador conserva IA aunque su plan comercial sea Basico."""
    from app import quota

    settings = _quota_settings()
    monkeypatch.setattr(
        quota, "get_profile_flags", lambda user_id, s: ("basico", True)
    )
    monkeypatch.setattr(
        quota, "count_month_usage", lambda user_id, s, kinds=None: 999
    )
    info = quota.check_quota("admin-x", settings)
    assert info["ilimitado"] is True
    assert info["limite"] == 0

    visible = quota.usage_info("admin-x", settings)
    assert visible["disponible"] is True
    assert visible["ilimitado"] is True


# ── POST /clean/assisted ──────────────────────────────────────────────────────


def test_clean_assisted_requiere_token(client, sample_csv):
    name, content = sample_csv
    response = client.post(
        "/clean/assisted",
        files={"file": (name, content, "text/csv")},
        data={"instructions": "limpia Ventas"},
    )
    assert response.status_code == 401


def test_clean_assisted_dirigida_por_columnas(client, auth_headers, sample_csv):
    """Sin Supabase (dev) el gating y la cuota quedan en fail-open: el flujo
    dirigido corre completo y devuelve el plan interpretado."""
    name, content = sample_csv
    response = client.post(
        "/clean/assisted",
        files={"file": (name, content, "text/csv")},
        data={"instructions": "Limpia las columnas Fecha y Ventas, elimina duplicados"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["resumen"]["aplicado"] is True
    dirigida = body["dirigida"]
    assert dirigida["reconocido"] is True
    assert "Fecha" in dirigida["columnas_incluir"]
    assert "Ventas" in dirigida["columnas_incluir"]
    assert dirigida["reglas_forzadas"].get("duplicados") is True
    assert dirigida["cupo"]["disponible"] is False  # sin Supabase en tests
    # El alcance se refleja en el motor: hay columnas fuera del alcance avisadas
    assert any("dirigida" in a.lower() for a in body["avisos"])


def test_clean_assisted_excluye_columnas_negadas(client, auth_headers, sample_csv):
    name, content = sample_csv
    response = client.post(
        "/clean/assisted",
        files={"file": (name, content, "text/csv")},
        data={"instructions": "Corrige los nulos pero no toques la columna Cliente"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    dirigida = response.json()["dirigida"]
    assert "Cliente" in dirigida["columnas_excluir"]
    assert dirigida["reglas_forzadas"].get("nulos") is True


def test_clean_assisted_instrucciones_no_reconocidas_422_sin_consumo(
    client, auth_headers, sample_csv, monkeypatch
):
    from app.routes import pipeline as pipeline_module

    def _no_consumir(*args, **kwargs):
        raise AssertionError("No debe registrar consumo si la instrucción no se reconoce")

    monkeypatch.setattr(pipeline_module.quota, "record_cleaning_usage", _no_consumir)
    name, content = sample_csv
    response = client.post(
        "/clean/assisted",
        files={"file": (name, content, "text/csv")},
        data={"instructions": "hola qué tal"},
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert "NO se descontó" in response.json()["detail"]


def test_clean_assisted_cupo_agotado_429(client, auth_headers, sample_csv, monkeypatch):
    from fastapi import HTTPException

    from app.routes import pipeline as pipeline_module

    def _sin_cupo(user_id, settings):
        raise HTTPException(status_code=429, detail="Usaste tus 2 intentos. Planes.")

    monkeypatch.setattr(pipeline_module.quota, "check_cleaning_quota", _sin_cupo)
    name, content = sample_csv
    response = client.post(
        "/clean/assisted",
        files={"file": (name, content, "text/csv")},
        data={"instructions": "limpia Ventas"},
        headers=auth_headers,
    )
    assert response.status_code == 429


# ── /plans/usage, /addons/request y /admin/grant-credits ────────────────────


def test_plans_usage_sin_supabase(client, auth_headers):
    assert client.get("/plans/usage").status_code == 401
    response = client.get("/plans/usage", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["disponible"] is False
    assert body["limpieza"]["base"] == 10  # Fase 8: base Analista
    assert body["enforcement"] is True  # Fase 8: gating encendido por defecto


def test_addons_request_sin_supabase_503(client, auth_headers):
    assert client.post("/addons/request", json={}).status_code == 401
    response = client.post(
        "/addons/request",
        json={"tipo": "tokens_limpieza", "mensaje": "Necesito 5 más"},
        headers=auth_headers,
    )
    assert response.status_code == 503
    assert "migraciones" in response.json()["detail"]


def test_admin_grant_credits_requiere_admin(client, auth_headers, monkeypatch):
    from app.config import get_settings
    from app.routes import plans as plans_module

    settings = get_settings()
    monkeypatch.setattr(settings, "supabase_url", "https://proyecto-test.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "service-key")
    monkeypatch.setattr(plans_module, "get_is_admin", lambda user_id, s: False)
    response = client.post(
        "/admin/grant-credits",
        json={"user_id": "11111111-1111-1111-1111-111111111111", "credits": 5},
        headers=auth_headers,
    )
    assert response.status_code == 403


# ── Motor profesional (§5) ────────────────────────────────────────────────────


def _clean_apply(client, auth_headers, name, csv_text, extra=None):
    data = {"apply": "true"}
    if extra:
        data.update(extra)
    return client.post(
        "/clean",
        files={"file": (name, csv_text.encode("utf-8"), "text/csv")},
        data=data,
        headers=auth_headers,
    )


def test_nulos_monetarios_no_se_imputan_con_cero(client, auth_headers):
    """§5.1: una venta faltante jamás se vuelve $0 (sesga sumas y márgenes)."""
    csv = "Fecha;Producto;Ventas\n01/05/2026;A;1000\n02/05/2026;B;\n03/05/2026;C;2000\n"
    response = _clean_apply(client, auth_headers, "nulos.csv", csv)
    assert response.status_code == 200
    body = response.json()
    ventas_idx = body["preview"]["columnas"].index("Ventas")
    valores = [fila[ventas_idx] for fila in body["preview"]["filas"]]
    assert "0" not in valores  # el nulo quedó vacío, no imputado
    assert body["reporte_calidad"]["Ventas"]["politica_nulos"].startswith("preservados")
    # Y las métricas lo tratan como NaN: el total no cambia
    metrics = client.post(
        "/metrics",
        files={"file": ("nulos.csv", csv.encode("utf-8"), "text/csv")},
        headers=auth_headers,
    ).json()
    assert metrics["kpis"]["ingresos_totales"]["valor"] == 3000.0


def test_outliers_solo_en_roles_metricos(client, auth_headers):
    """§5.3: el IQR no marca outliers en columnas ID/año, solo en montos."""
    filas = "\n".join(
        f"01/05/2026;{i};P{i};{900 + i * 55}" for i in range(1, 10)
    )
    csv = f"Fecha;ID Boleta;Producto;Ventas\n{filas}\n02/05/2026;999999;PX;99000000\n"
    response = _clean_apply(client, auth_headers, "outliers.csv", csv)
    body = response.json()
    assert body["problemas"]["valores_fuera_de_rango"] >= 1  # la venta de 99M
    assert "outliers" not in body["reporte_calidad"]["ID Boleta"]
    assert body["reporte_calidad"]["Ventas"].get("outliers", 0) >= 1


def test_fecha_con_mes_en_texto(client, auth_headers):
    """§5.6: '01 mayo 2026' y '1 de junio de 2026' se estandarizan a DD/MM/YYYY."""
    csv = "Fecha;Ventas\n01 mayo 2026;1000\n1 de junio de 2026;2000\n03/05/2026;500\n"
    response = client.post(
        "/standardize",
        files={"file": ("meses.csv", csv.encode("utf-8"), "text/csv")},
        headers=auth_headers,
    )
    body = response.json()
    despues = [fila[0] for fila in body["preview"]["despues"]]
    assert "01/05/2026" in despues
    assert "01/06/2026" in despues


def test_convencion_decimal_por_columna(client, auth_headers):
    """§5.5: en una columna con decimales consistentes, '3.125' es 3.125 —
    no tres mil ciento veinticinco."""
    csv = "Producto;Margen\nA;8.5\nB;12.75\nC;3.125\n"
    response = client.post(
        "/standardize",
        files={"file": ("decimales.csv", csv.encode("utf-8"), "text/csv")},
        headers=auth_headers,
    )
    despues = [fila[1] for fila in response.json()["preview"]["despues"]]
    # Fase 13 (P0.6): la precisión se CONSERVA — antes se truncaba a 2 decimales
    assert "3.125" in despues
    assert "3125" not in despues


def test_convencion_miles_se_mantiene(client, auth_headers):
    """La convención es-CL sigue: '850.000' en una columna de montos son miles."""
    csv = "Producto;Ventas\nA;850.000\nB;1.200.000\nC;500\n"
    response = client.post(
        "/standardize",
        files={"file": ("miles.csv", csv.encode("utf-8"), "text/csv")},
        headers=auth_headers,
    )
    despues = [fila[1] for fila in response.json()["preview"]["despues"]]
    assert "850000" in despues


def test_fuzzy_unifica_typos(client, auth_headers):
    """§5.11: 'Santigo' (typo raro) se fusiona con 'Santiago' (frecuente)."""
    filas = "\n".join(f"0{i}/05/2026;Santiago;100" for i in range(1, 6))
    csv = f"Fecha;Ciudad;Ventas\n{filas}\n06/05/2026;Santigo;100\n"
    response = client.post(
        "/standardize",
        files={"file": ("typos.csv", csv.encode("utf-8"), "text/csv")},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = _clean_apply(client, auth_headers, "typos.csv", csv).json()
    ciudad_idx = body["preview"]["columnas"].index("Ciudad")
    valores = {fila[ciudad_idx] for fila in body["preview"]["filas"]}
    assert "Santigo" not in valores
    assert body["fusiones_texto"]["total"] >= 1


def test_excel_multihoja_y_fila_de_titulo(client, auth_headers):
    """§5.12: se elige la hoja con datos y se omite la fila de título."""
    import openpyxl

    wb = openpyxl.Workbook()
    portada = wb.active
    portada.title = "Portada"
    portada["A1"] = "Notas"
    datos = wb.create_sheet("Datos")
    datos.append(["REPORTE DE VENTAS 2026"])  # fila de título a omitir
    datos.append(["Fecha", "Producto", "Ventas"])
    datos.append(["01/05/2026", "A", 1000])
    datos.append(["02/05/2026", "B", 2000])
    buf = io.BytesIO()
    wb.save(buf)
    response = client.post(
        "/standardize",
        files={
            "file": (
                "multihoja.xlsx",
                buf.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["carga"]["hoja_usada"] == "Datos"
    assert body["carga"]["filas_titulo_omitidas"] == 1
    assert body["filas"] == 2
    assert body["preview"]["columnas"][:3] == ["Fecha", "Producto", "Ventas"]
    assert any("hojas" in a for a in body["avisos"])


def test_dedup_sin_columna_id_advierte(client, auth_headers, sample_csv):
    """Fase 12: filas idénticas se detectan y exigen confirmación explícita."""
    name, content = sample_csv
    response = client.post(
        "/clean",
        files={"file": (name, content, "text/csv")},
        headers=auth_headers,
    )
    body = response.json()
    # Los campos heredados conservan sus nombres, con semántica estable.
    assert body["problemas"]["duplicados"] + body["problemas"].get("duplicados_probables", 0) >= 1
    assert body["duplicados_criterio"] == "fila_exacta_original_con_confirmacion"
    assert body["correcciones"]["filas_duplicadas_a_eliminar"] == 0
    assert any("confirmes explícitamente" in a for a in body["avisos"])


def test_mapping_corregido_por_el_usuario(client, auth_headers):
    """§5.10: el usuario puede reasignar el rol de una columna y el motor lo respeta."""
    csv = "Fecha;Total Factura;Detalle\n01/05/2026;1000;A\n02/05/2026;2000;B\n"
    mapping = '{"monto": "Total Factura", "producto": "Detalle"}'
    response = client.post(
        "/metrics",
        files={"file": ("map.csv", csv.encode("utf-8"), "text/csv")},
        data={"mapping": mapping},
        headers=auth_headers,
    )
    body = response.json()
    assert body["mapeo"]["monto"] == "Total Factura"
    assert body["kpis"]["ingresos_totales"]["valor"] == 3000.0


def test_cache_del_pipeline_evita_recalculo(client, auth_headers, monkeypatch):
    """§5.7: dos llamadas a /metrics con el mismo archivo corren el motor UNA vez."""
    from app.routes import pipeline as pipeline_module

    calls = {"n": 0}
    original = pipeline_module.analyze_and_clean

    def counting(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(pipeline_module, "analyze_and_clean", counting)
    csv = "Fecha;Ventas\n01/05/2026;1000\n02/06/2026;2000\n".encode("utf-8")
    for date_from in (None, "2026-05-01"):
        data = {"date_from": date_from} if date_from else {}
        response = client.post(
            "/metrics",
            files={"file": ("cache.csv", csv, "text/csv")},
            data=data,
            headers=auth_headers,
        )
        assert response.status_code == 200
    assert calls["n"] == 1
