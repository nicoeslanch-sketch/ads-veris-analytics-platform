import io

import httpx
import pytest
from fastapi import HTTPException, UploadFile

from app import storage_capacity as capacity
from app.config import Settings
from app.routes import storage_upload


def settings():
    return Settings(_env_file=None, supabase_url="https://synthetic.invalid", supabase_service_role_key="test", plan_enforcement=False)


def test_quota_failure_never_starts_upload(monkeypatch):
    calls = []
    monkeypatch.setattr(capacity, "capacity_rpc", lambda *_: {"ok": False, "detail": "Quota"})
    with pytest.raises(HTTPException) as error:
        capacity.safe_storage_write("user/source.csv", 10, "source", settings(), lambda: calls.append(True))
    assert error.value.status_code == 507
    assert calls == []


@pytest.mark.parametrize("status,settle", [(201, True), (200, True), (400, False), (403, False), (409, False), (500, None), (503, None)])
def test_settlement_distinguishes_definite_and_ambiguous_outcomes(monkeypatch, status, settle):
    calls = []
    monkeypatch.setattr(capacity, "reserve_capacity", lambda *_: calls.append("reserved"))
    monkeypatch.setattr(capacity, "settle_capacity", lambda path, written, cfg: calls.append(written))
    capacity.safe_storage_write("user/source.csv", 10, "source", settings(), lambda: httpx.Response(status))
    assert calls == (["reserved"] if settle is None else ["reserved", settle])


def test_timeout_keeps_budget_reserved(monkeypatch):
    calls = []
    monkeypatch.setattr(capacity, "reserve_capacity", lambda *_: calls.append("reserved"))
    monkeypatch.setattr(capacity, "settle_capacity", lambda *_: calls.append("released"))
    def write():
        raise httpx.ReadTimeout("uncertain remote result")
    with pytest.raises(httpx.ReadTimeout):
        capacity.safe_storage_write("user/source.csv", 10, "source", settings(), write)
    assert calls == ["reserved"]


def test_rpc_fails_closed_and_hides_provider_details(monkeypatch):
    monkeypatch.setattr(capacity.httpx, "post", lambda *_args, **_kwargs: httpx.Response(503, request=httpx.Request("POST", "https://synthetic.invalid")))
    with pytest.raises(HTTPException) as error:
        capacity.capacity_rpc("storage_capacity", {}, settings())
    assert error.value.status_code == 503
    assert "synthetic" not in error.value.detail


def test_source_path_is_server_generated_and_stream_size_is_measured(monkeypatch):
    captured = {}
    def writer(path, size, kind, cfg, write):
        captured.update(path=path, size=size, kind=kind)
        return write()
    def post(url, **kwargs):
        captured["body"] = b"".join(kwargs["content"])
        captured["headers"] = kwargs["headers"]
        return httpx.Response(201)
    monkeypatch.setattr(storage_upload, "safe_storage_write", writer)
    monkeypatch.setattr(storage_upload.httpx, "post", post)
    file = UploadFile(io.BytesIO(b"x,y\n1,2"), size=7, filename="../../otro/ventas.csv")
    result = storage_upload._upload_source(file, "owner", settings())
    assert result["storage_path"].startswith("owner/")
    assert result["storage_path"].count("/") == 1
    assert captured["body"] == b"x,y\n1,2"
    assert captured["headers"]["Content-Length"] == "7"
    assert captured["headers"]["x-upsert"] == "false"


@pytest.mark.parametrize("size,name,status", [(0,"x.csv",413),(16*1024*1024,"x.csv",413),(5,"evil.exe",422)])
def test_invalid_sources_rejected_before_reservation(monkeypatch, size, name, status):
    monkeypatch.setattr(storage_upload, "safe_storage_write", lambda *_: pytest.fail("Must not reserve"))
    with pytest.raises(HTTPException) as error:
        storage_upload._upload_source(UploadFile(io.BytesIO(b"test"), size=size, filename=name), "owner", settings())
    assert error.value.status_code == status


def test_upload_and_quota_require_authentication(client):
    assert client.post("/storage/upload", files={"file": ("x.csv", b"x\n1")}).status_code == 401
    assert client.get("/storage/quota").status_code == 401
