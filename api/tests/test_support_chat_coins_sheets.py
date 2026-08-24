from pathlib import Path


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
