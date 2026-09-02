from pathlib import Path

import pytest


def _collection_metrics():
    return {
        "moneda": "CLP",
        "calidad_datos": 93.9,
        "duplicados": {"detectados": 593, "eliminados": 0, "conservados": 593},
        "advertencias": [
            "Esta hoja se interpreta como maestra de clientes.",
        ],
        "analisis_negocio": {
            "perfil": "cobranza_nominal",
            "filtros": {"aplicados": {}},
            "cobranza": {
                "moneda": "CLP",
                "grano_temporal": "semana",
                "periodo": {"desde": "2026-04-23", "hasta": "2026-05-25"},
                "kpis": {
                    "recaudacion_cobranza": 1120052069,
                    "recaudacion_total": 1335598867,
                    "diferencia": 215546798,
                    "diferencia_pct": 16.14,
                    "participacion_cobranza_pct": 83.86,
                    "registros": 14917,
                    "registros_cobranza": 10021,
                    "pagos_positivos": 14248,
                    "ticket_promedio_cobranza": 111770.49,
                },
                "comparacion": {
                    "recaudacion_actual": 1120052069,
                    "recaudacion_anterior": None,
                    "variacion_pct": None,
                    "base_comparable": False,
                },
                "evolucion": [
                    {
                        "periodo": "2026-04-28/2026-05-04",
                        "recaudacion_total": 221967569,
                        "recaudacion_cobranza": 221967569,
                    },
                    {
                        "periodo": "2026-05-05/2026-05-11",
                        "recaudacion_total": 565983745,
                        "recaudacion_cobranza": 397732370,
                    },
                ],
                "equipos": [
                    {
                        "equipo": "FLUJO",
                        "subgrupo": None,
                        "recaudacion_cobranza": 620006326,
                        "participacion_pct": 55.36,
                    },
                    {
                        "equipo": "STOCK",
                        "subgrupo": None,
                        "recaudacion_cobranza": 246573996,
                        "participacion_pct": 22.01,
                    },
                ],
                "agencias": [
                    {"nombre": "WEB", "valor": 553000000, "participacion_pct": 49.37},
                    {"nombre": "CONCEPCION", "valor": 120000000, "participacion_pct": 10.71},
                ],
                "formas_pago": [
                    {"nombre": "WebPay", "valor": 700000000, "participacion_pct": 62.50},
                    {"nombre": "Efectivo", "valor": 150000000, "participacion_pct": 13.39},
                ],
                "periodos_cotizados": [
                    {"periodo": "2025-12", "valor": 200000000},
                    {"periodo": "2026-03", "valor": 420000000},
                ],
            },
        },
    }


def _ask_collection(client, auth_headers, message):
    return client.post(
        "/assistant/bot",
        json={"message": message, "metrics": _collection_metrics()},
        headers=auth_headers,
    )


def test_quick_help_requires_auth(client):
    assert client.post("/assistant/bot", json={"message": "hola"}).status_code == 401


def test_quick_help_is_deterministic_and_free(client, auth_headers):
    response = client.post(
        "/assistant/bot",
        json={"message": "¿Cómo conecto y actualizo Google Sheets?"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "deterministic"
    assert body["coins_charged"] == 0
    assert body["confidence"] in {"medium", "high"}
    assert "Google" in body["answer"]
    assert body["knowledge_articles"] >= 40


def test_quick_help_unknown_question_has_safe_fallback(client, auth_headers):
    response = client.post(
        "/assistant/bot",
        json={"message": "zxqv qwerty plmokn"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["confidence"] == "low"
    assert "soporte humano" in response.json()["answer"]


def test_quick_help_reads_dashboard_metrics_in_uf(client, auth_headers):
    response = client.post(
        "/assistant/bot",
        json={
            "message": "¿Cuáles son mis ingresos totales?",
            "metrics": {
                "moneda": "UF",
                "moneda_mixta": False,
                "datos_monetarios_disponibles": True,
                "periodo": {"desde": "2026-01-01", "hasta": "2026-08-14", "mes_parcial": True},
                "kpis": {
                    "ingresos_totales": {"valor": 669700, "variacion_pct": 5.1},
                    "transacciones": 2670,
                    "ticket_promedio": 250.82,
                },
                "advertencias": ["No se encontró una columna de costos."],
            },
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["matched_key"] == "metric_income"
    assert "UF 669.700" in body["answer"]
    assert "no fue convertida a pesos" in body["answer"]
    assert "no hay costos" in body["answer"].lower()
    assert body["coins_charged"] == 0


def test_quick_help_explains_missing_profit_instead_of_inventing_it(client, auth_headers):
    response = client.post(
        "/assistant/bot",
        json={
            "message": "¿Cuánto gané?",
            "metrics": {
                "moneda": "CLP",
                "kpis": {"ingresos_totales": {"valor": 1000000}},
            },
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["matched_key"] == "metric_profit_unavailable"
    assert "Falta costo" in response.json()["answer"]


def test_quick_help_reads_flexible_dashboard_graphs(client, auth_headers):
    response = client.post(
        "/assistant/bot",
        json={
            "message": "¿Quién es mi mejor vendedor?",
            "metrics": {
                "moneda": "CLP",
                "kpis": {"ingresos_totales": {"valor": 300000}},
                "agrupaciones_flexibles": [
                    {
                        "columna": "Vendedor",
                        "grupos": [
                            {"nombre": "Ana", "ingresos": 180000, "porcentaje": 60},
                            {"nombre": "Luis", "ingresos": 120000, "porcentaje": 40},
                        ],
                    }
                ],
            },
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["matched_key"] == "metric_flexible_group"
    assert "Ana" in response.json()["answer"]
    assert "$180.000" in response.json()["answer"]


@pytest.mark.parametrize(
    ("question", "matched_key", "expected"),
    [
        ("¿Cuáles son mis ingresos totales?", "metric_collection_total", "$1.335.598.867"),
        ("¿Cuál es mi ticket promedio de cobranza?", "metric_collection_ticket", "$111.770"),
        ("¿Qué equipo aporta más a la cobranza?", "metric_collection_team", "FLUJO"),
        ("¿Cuál fue la semana con mayor recaudación?", "metric_collection_best_period", "$397.732.370"),
        ("¿Cuál fue la semana con mayor recaudación de cobranza?", "metric_collection_best_period", "$397.732.370"),
        ("¿Qué agencia lidera?", "metric_collection_agency", "WEB"),
        ("¿Cuántos pagos tengo?", "metric_collection_payments", "14.917"),
        ("¿Cuánto aporta STOCK?", "metric_collection_team", "$246.573.996"),
        ("¿Cuál es la principal forma de pago?", "metric_collection_payment_method", "WebPay"),
        ("¿Cuántos pagos están en cero?", "metric_collection_zero_payments", "669"),
        ("¿Cuál fue la peor semana?", "metric_collection_worst_period", "$221.967.569"),
        ("¿Qué periodo cotizado aporta más?", "metric_collection_quoted_period", "2026-03"),
    ],
)
def test_quick_help_reads_collection_kpis_and_graphs(
    question, matched_key, expected
):
    from app.metric_assistant import answer_metrics_question

    body = answer_metrics_question(question, _collection_metrics())

    assert body is not None
    assert body["matched_key"] == matched_key
    assert expected in body["answer"]


def test_quick_help_explains_collection_difference(client, auth_headers):
    response = _ask_collection(
        client,
        auth_headers,
        "¿Cuánto recaudo de cobranza y cuánto queda fuera?",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["matched_key"] == "metric_collection_difference"
    assert "$1.120.052.069" in body["answer"]
    assert "$215.546.798" in body["answer"]
    assert "83,86%" in body["answer"]


def test_quick_help_uses_feminine_article_for_week():
    from app.metric_assistant import answer_metrics_question

    body = answer_metrics_question(
        "¿Cuál fue la semana con mayor recaudación de cobranza?",
        _collection_metrics(),
    )

    assert body is not None
    assert body["answer"].startswith("La semana con mayor")


def test_quick_help_says_conserved_duplicates_are_in_totals(client, auth_headers):
    response = _ask_collection(
        client,
        auth_headers,
        "¿Cuántos duplicados hay y están incluidos en los totales?",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["matched_key"] == "metric_quality"
    assert "se conservaron 593" in body["answer"]
    assert "sí incluyen" in body["answer"]
    assert "maestra de clientes" not in body["answer"]


def test_quick_help_does_not_invent_total_without_duplicates(client, auth_headers):
    response = _ask_collection(client, auth_headers, "¿Cuánto sería sin duplicados?")

    assert response.status_code == 200
    body = response.json()
    assert body["matched_key"] == "metric_collection_duplicates_what_if"
    assert "incluye 593" in body["answer"]
    assert "No puedo afirmar" in body["answer"]


def test_quick_help_builds_prudent_collection_overview(client, auth_headers):
    response = _ask_collection(
        client,
        auth_headers,
        "¿Qué conclusión general sacas de mis datos?",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["matched_key"] == "metric_collection_overview"
    assert "$1.120.052.069" in body["answer"]
    assert "$1.335.598.867" in body["answer"]
    assert "FLUJO" in body["answer"]
    assert "no ventas, utilidad ni rentabilidad" in body["answer"]


def test_advanced_chat_is_off_by_default(client, auth_headers):
    response = client.get("/assistant/config", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["advanced_enabled"] is False
    assert response.json()["quick_help_enabled"] is True


def test_coin_wallet_degrades_without_database(client, auth_headers):
    response = client.get("/coins/me", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["balance"] == 0
    assert body["purchases_enabled"] is False


def test_support_chat_degrades_without_database(client, auth_headers):
    response = client.get("/support/conversation", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {
        "available": False,
        "conversation": None,
        "expires_after_hours": 24,
    }


def test_google_sheet_url_parses_each_gid():
    from app.routes.connectors import _parse_sheet_url

    url = "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz_123456/edit#gid=987654"
    assert _parse_sheet_url(url) == ("1AbCdEfGhIjKlMnOpQrStUvWxYz_123456", "987654")


def test_google_sheet_hash_detects_real_content_changes():
    from app.routes.connectors import _hash_content

    assert _hash_content(b"a,b\n1,2\n") == _hash_content(b"a,b\n1,2\n")
    assert _hash_content(b"a,b\n1,2\n") != _hash_content(b"a,b\n1,3\n")


def test_new_migration_has_rls_expiry_and_atomic_ledger():
    migration = (
        Path(__file__).parents[2]
        / "supabase"
        / "migrations"
        / "20260824011817_support_chat_coins_google_sheets.sql"
    ).read_text(encoding="utf-8")
    assert "support_conversations enable row level security" in migration
    assert "interval '24 hours'" in migration
    assert "ads_coin_transactions" in migration
    assert "adjust_ads_coins" in migration
    assert "google_sheet_sources_select_own" in migration
