"""Pruebas de la Fase 8: panel admin, soporte, retención y adaptividad."""


# ── Panel de administración ───────────────────────────────────────────────────


def test_admin_accounts_requiere_token(client):
    assert client.get("/admin/accounts").status_code == 401


def test_admin_accounts_sin_supabase_503(client, auth_headers):
    response = client.get("/admin/accounts", headers=auth_headers)
    assert response.status_code == 503
    assert "administración" in response.json()["detail"]


def test_admin_accounts_no_admin_403(client, auth_headers, monkeypatch):
    from app.config import get_settings
    from app.routes import admin as admin_module

    settings = get_settings()
    monkeypatch.setattr(settings, "supabase_url", "https://proyecto-test.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "service-key")
    monkeypatch.setattr(admin_module, "get_is_admin", lambda user_id, s: False)
    response = client.get("/admin/accounts", headers=auth_headers)
    assert response.status_code == 403
    assert "administradora" in response.json()["detail"]


def test_admin_set_plan_valida_el_plan(client, auth_headers, monkeypatch):
    from app.config import get_settings
    from app.routes import admin as admin_module

    settings = get_settings()
    monkeypatch.setattr(settings, "supabase_url", "https://proyecto-test.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "service-key")
    monkeypatch.setattr(admin_module, "get_is_admin", lambda user_id, s: True)
    response = client.post(
        "/admin/accounts/11111111-1111-1111-1111-111111111111/plan",
        json={"plan": "premium"},  # plan inexistente
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert "Plan desconocido" in response.json()["detail"]


def test_admin_set_plan_actualiza_y_audita(client, auth_headers, monkeypatch):
    import httpx

    from app.config import get_settings
    from app.routes import admin as admin_module

    settings = get_settings()
    monkeypatch.setattr(settings, "supabase_url", "https://proyecto-test.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "service-key")
    monkeypatch.setattr(admin_module, "get_is_admin", lambda user_id, s: True)

    calls: list[tuple[str, str]] = []

    def fake_patch(url, params=None, json=None, headers=None, timeout=None):
        calls.append(("PATCH", url))
        assert json == {"plan": "analista"}
        return httpx.Response(200, json=[{"id": "target-1", "plan": "analista"}])

    def fake_post(url, params=None, json=None, headers=None, timeout=None):
        calls.append(("POST", url))
        return httpx.Response(201, json=[])

    monkeypatch.setattr(admin_module.httpx, "patch", fake_patch)
    monkeypatch.setattr(admin_module.httpx, "post", fake_post)
    response = client.post(
        "/admin/accounts/target-1/plan",
        json={"plan": "Analista"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True, "user_id": "target-1", "plan": "analista"}
    assert any(m == "PATCH" and "profiles" in u for m, u in calls)
    assert any(m == "POST" and "admin_audit" in u for m, u in calls)  # auditoría


# ── Soporte (botón "¿Necesitas ayuda?") ──────────────────────────────────────


def test_support_request_requiere_token(client):
    assert client.post("/support/request", json={"mensaje": "hola"}).status_code == 401


def test_support_request_sin_supabase_503(client, auth_headers):
    response = client.post(
        "/support/request",
        json={"mensaje": "Necesito ayuda con mi archivo"},
        headers=auth_headers,
    )
    assert response.status_code == 503


def test_support_request_mensaje_vacio_422(client, auth_headers, monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "supabase_url", "https://proyecto-test.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "service-key")
    response = client.post(
        "/support/request",
        json={"mensaje": "   "},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_support_mine_sin_supabase_no_falla(client, auth_headers):
    response = client.get("/support/mine", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"disponible": False, "solicitudes": []}


# ── Retención de archivos en Storage ─────────────────────────────────────────


def test_retention_sin_supabase_no_op(client, auth_headers):
    """La retención jamás rompe el flujo de carga: sin Supabase es un no-op."""
    response = client.post("/storage/retention", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["eliminados"] == 0


def test_retention_poda_excedente_y_antiguos(monkeypatch):
    """Poda: respeta keep_last, borra el excedente del tope y lo viejo."""
    from datetime import datetime, timedelta, timezone

    from app.config import Settings
    from app.routes import retention as retention_module

    settings = Settings(
        supabase_url="https://proyecto-test.supabase.co",
        supabase_service_role_key="service-key",
        storage_max_files_basico=4,
        storage_retention_days=60,
        storage_keep_last=2,
    )

    now = datetime.now(timezone.utc)

    def iso(days_ago: int) -> str:
        return (now - timedelta(days=days_ago)).isoformat()

    # 6 archivos: índices 0-1 protegidos (keep_last=2), 2-3 dentro del tope
    # (el 3 es viejo → se borra por edad), 4-5 exceden el tope de 4 → se borran.
    files = [
        {"id": "a", "name": "f0.csv", "created_at": iso(1)},
        {"id": "b", "name": "f1.csv", "created_at": iso(2)},
        {"id": "c", "name": "f2.csv", "created_at": iso(3)},
        {"id": "d", "name": "f3.csv", "created_at": iso(90)},   # viejo
        {"id": "e", "name": "f4.csv", "created_at": iso(100)},  # excedente
        {"id": "f", "name": "f5.csv", "created_at": iso(120)},  # excedente
    ]

    deleted: list[list[str]] = []
    monkeypatch.setattr(
        retention_module, "get_profile_flags", lambda uid, s: ("basico", False)
    )
    monkeypatch.setattr(
        retention_module, "_list_user_files", lambda uid, s: list(files)
    )
    monkeypatch.setattr(
        retention_module,
        "_delete_files",
        lambda uid, names, s: deleted.append(names),
    )
    monkeypatch.setattr(
        retention_module, "_unlink_datasets", lambda uid, names, s: None
    )

    result = retention_module._retention_sync("user-1", settings)
    assert result["eliminados"] == 3
    assert deleted[0] == ["f3.csv", "f4.csv", "f5.csv"]
    assert result["conservados"] == 3
    assert result["limite"] == 4


def test_retention_keep_last_es_intocable(monkeypatch):
    """Aunque todo sea viejísimo, los últimos N archivos no se tocan."""
    from datetime import datetime, timedelta, timezone

    from app.config import Settings
    from app.routes import retention as retention_module

    settings = Settings(
        supabase_url="https://proyecto-test.supabase.co",
        supabase_service_role_key="service-key",
        storage_keep_last=5,
    )
    old = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    files = [{"id": str(i), "name": f"f{i}.csv", "created_at": old} for i in range(3)]

    monkeypatch.setattr(
        retention_module, "get_profile_flags", lambda uid, s: ("basico", False)
    )
    monkeypatch.setattr(retention_module, "_list_user_files", lambda uid, s: list(files))
    monkeypatch.setattr(
        retention_module,
        "_delete_files",
        lambda uid, names, s: (_ for _ in ()).throw(AssertionError("no debe borrar")),
    )
    monkeypatch.setattr(retention_module, "_unlink_datasets", lambda uid, names, s: None)

    result = retention_module._retention_sync("user-1", settings)
    assert result["eliminados"] == 0
    assert result["conservados"] == 3


# ── Motor: robustez extra Fase 8 (§5.14) ─────────────────────────────────────


def test_parse_number_con_moneda_y_porcentaje():
    from app.engine.standardize import parse_number

    assert parse_number("$ 1.200.000") == 1_200_000
    assert parse_number("CLP 850.000") == 850_000
    assert parse_number("US$1.500") == 1500
    assert parse_number("1.200 USD") == 1200
    assert parse_number("€200") == 200
    assert parse_number("12%") == 12
    assert parse_number("12,5%") == 12.5


def test_parse_number_negativo_contable():
    """'(1.500)' es un negativo en formato contable, no texto."""
    from app.engine.standardize import parse_number

    assert parse_number("(1.500)") == -1500
    assert parse_number("($ 2.000)") == -2000
    assert parse_number("-500") == -500


def test_columna_con_moneda_se_detecta_como_numero(client, auth_headers):
    csv = "Producto;Precio\nA;$ 12.000\nB;CLP 8.500\nC;$ 4.990\n"
    response = client.post(
        "/standardize",
        files={"file": ("moneda.csv", csv.encode("utf-8"), "text/csv")},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["column_types"]["Precio"] == "numero"


def test_fila_de_totales_al_final_se_omite(client, auth_headers):
    """Una fila 'Total' al final duplicaría los ingresos: se omite con aviso."""
    csv = (
        "Fecha;Producto;Ventas\n"
        "01/05/2026;A;1000\n"
        "02/05/2026;B;2000\n"
        "Total;;3000\n"
    )
    response = client.post(
        "/standardize",
        files={"file": ("totales.csv", csv.encode("utf-8"), "text/csv")},
        headers=auth_headers,
    )
    body = response.json()
    assert body["filas"] == 2  # la fila Total no es un dato
    assert any("totales" in a.lower() for a in body["avisos"])

    metrics = client.post(
        "/metrics",
        files={"file": ("totales.csv", csv.encode("utf-8"), "text/csv")},
        headers=auth_headers,
    ).json()
    assert metrics["kpis"]["ingresos_totales"]["valor"] == 3000.0  # no 6000


def test_filas_de_datos_normales_no_se_confunden_con_totales(client, auth_headers):
    """Un producto llamado 'Tornillo total' NO es una fila de totales."""
    csv = "Producto;Ventas\nTornillo;1000\nMartillo;2000\n"
    response = client.post(
        "/standardize",
        files={"file": ("normal.csv", csv.encode("utf-8"), "text/csv")},
        headers=auth_headers,
    )
    assert response.json()["filas"] == 2


# ── /metrics informa las dimensiones reales del dataset ──────────────────────


def test_metrics_expone_dimensiones_disponibles(client, auth_headers):
    """Fase 8: el frontend adapta Explorar/Resumen a lo que trae el archivo."""
    csv = "Fecha;Producto;Ventas\n01/05/2026;A;1000\n02/05/2026;B;2000\n"
    response = client.post(
        "/metrics",
        files={"file": ("dims.csv", csv.encode("utf-8"), "text/csv")},
        headers=auth_headers,
    )
    assert response.status_code == 200
    dims = response.json()["dimensiones"]
    assert dims["fecha"] is True
    assert dims["monto"] is True
    assert dims["producto"] is True
    assert dims["canal"] is False
    assert dims["sucursal"] is False
    assert dims["costo"] is False
    assert dims["categoria"] is False
