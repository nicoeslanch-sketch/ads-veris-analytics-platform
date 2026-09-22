"""HTTP regression guards; real database races are exercised in isolated CI."""

import io
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException, UploadFile

from app import quota
from app.config import Settings
from app.dataset_access import require_owned_dataset
from app.routes import admin, ai, connectors, storage_upload


def configured():
    return Settings(supabase_url="https://example.supabase.co", supabase_service_role_key="test-key",
                    _env_file=None)


@pytest.mark.parametrize("rows", [[], [{"id": str(uuid4())}]])
def test_dataset_ownership_fails_closed(monkeypatch, rows):
    uid, did = str(uuid4()), str(uuid4())
    def get(url, **kwargs):
        assert kwargs["params"]["id"] == "eq." + did
        assert kwargs["params"]["user_id"] == "eq." + uid
        return httpx.Response(200, request=httpx.Request("GET", url), json=rows)
    monkeypatch.setattr(httpx, "get", get)
    with pytest.raises(HTTPException) as exc:
        require_owned_dataset(did, uid, configured())
    assert exc.value.status_code == 404


def test_link_foreign_dataset_never_writes(client, auth_headers, monkeypatch):
    did, sid = str(uuid4()), str(uuid4())
    monkeypatch.setattr(connectors, "_source_for_user_sync", lambda *a: {"id": sid})
    def denied(*args):
        raise HTTPException(404, "No existe ese archivo en tu cuenta.")
    monkeypatch.setattr(connectors, "require_owned_dataset", denied)
    monkeypatch.setattr(connectors, "_patch_source_sync", lambda *a: pytest.fail("No write allowed"))
    r = client.post(f"/connectors/sheets/sources/{sid}/link", json={"dataset_id": did}, headers=auth_headers)
    assert r.status_code == 404


@pytest.mark.parametrize("dataset_id", ["invalid", "x&user_id=neq.y", "", "(id)"])
def test_link_rejects_non_uuid(client, auth_headers, dataset_id):
    r = client.post(f"/connectors/sheets/sources/{uuid4()}/link", json={"dataset_id": dataset_id}, headers=auth_headers)
    assert r.status_code == 422


def test_link_own_dataset_and_detach(client, auth_headers, monkeypatch):
    did, sid = str(uuid4()), str(uuid4())
    ownership, writes = [], []
    monkeypatch.setattr(connectors, "_source_for_user_sync", lambda *a: {"remote_hash": "abc"})
    monkeypatch.setattr(connectors, "require_owned_dataset", lambda *a: ownership.append(a))
    monkeypatch.setattr(connectors, "_patch_source_sync", lambda *a: writes.append(a))
    for dataset_id in (did, None):
        r = client.post(f"/connectors/sheets/sources/{sid}/link", json={"dataset_id": dataset_id}, headers=auth_headers)
        assert r.status_code == 200 and r.json()["dataset_id"] == dataset_id
        assert writes[-1][1] == "user-test-123"
    assert len(ownership) == 1 and ownership[0][0] == did


@pytest.mark.parametrize("extension", ["xls", "tsv", "txt", "exe", "xlsx.exe"])
def test_unsupported_source_rejected_before_storage(monkeypatch, extension):
    monkeypatch.setattr(storage_upload, "require_capability_for_user", lambda *a: None)
    monkeypatch.setattr(storage_upload, "safe_storage_write", lambda *a: pytest.fail("No storage write"))
    file = UploadFile(filename="example." + extension, file=io.BytesIO(b"hello"), size=5)
    with pytest.raises(HTTPException) as exc:
        storage_upload._upload_source(file, "user", configured())
    assert exc.value.status_code == 422


def test_matching_admin_email_does_not_bypass_database(monkeypatch):
    monkeypatch.setattr(admin, "get_is_admin", lambda *a: False)
    with pytest.raises(HTTPException) as exc:
        admin._require_admin_sync("user", configured(), "servicios@adsveris.com")
    assert exc.value.status_code == 403


@pytest.mark.parametrize("fn", [quota.check_quota, quota.check_cleaning_quota])
def test_legacy_quota_preflight_is_not_fail_open(monkeypatch, fn):
    def unavailable(*args):
        raise httpx.ConnectError("unavailable")
    monkeypatch.setattr(quota, "get_profile_flags", unavailable)
    with pytest.raises(HTTPException) as exc:
        fn("user", configured())
    assert exc.value.status_code == 503


@pytest.mark.parametrize("reason,expected", [("plan", 403), ("burst", 429), ("quota", 429)])
def test_atomic_quota_denials(monkeypatch, reason, expected):
    monkeypatch.setattr(quota, "commercial_rpc", lambda *a: {"allowed": False, "reason": reason})
    with pytest.raises(HTTPException) as exc:
        quota.reserve_usage("user", "summary", configured())
    assert exc.value.status_code == expected


@pytest.mark.parametrize("path,body", [("summary", {"metrics": {}}), ("recommendation", {"metrics": {}}),
                                      ("chat", {"metrics": {}, "pregunta": "hola"})])
def test_provider_never_called_without_reservation(client, auth_headers, monkeypatch, path, body):
    class Provider:
        @property
        def messages(self):
            pytest.fail("Provider must not run when quota cannot be verified")
    monkeypatch.setattr(ai, "_guard_ai_burst", lambda *a: None)
    monkeypatch.setattr(ai, "_client", lambda *a: Provider())
    def unavailable(*a):
        raise HTTPException(503, "No se pudo verificar tu cupo.")
    monkeypatch.setattr(quota, "reserve_usage", unavailable)
    r = client.post("/ai/" + path, json=body, headers=auth_headers)
    assert r.status_code == 503


def test_no_implicit_provider_retry(monkeypatch):
    captured = {}
    monkeypatch.setattr(ai, "AsyncAnthropic", lambda **kwargs: captured.update(kwargs))
    settings = configured()
    settings.anthropic_api_key = "test-key"
    ai._client(settings)
    assert captured["max_retries"] == 0
    assert captured["timeout"] == 60


def test_manual_plan_route_cannot_impersonate_payment():
    with pytest.raises(HTTPException) as exc:
        admin.set_user_plan("admin", "user", "gold", configured(), source="pasarela")
    assert exc.value.status_code == 422
