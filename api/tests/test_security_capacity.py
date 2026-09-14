"""Synthetic defensive probes only; no production traffic or customer files."""

import asyncio
import io
import json
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import jwt
import pytest
from fastapi import HTTPException

from app.analysis_jobs import AnalysisJobManager
from app.auth import _decode
from app.config import Settings
from app.engine.export import neutralize_excel_formula
from app.engine.loader import UnsupportedFileError, _guard_xlsx_zip
from app.request_security import RequestSecurityMiddleware
from app.routes import connectors
from app.storage import normalize_user_storage_path

SECRET = "synthetic-security-test-secret-at-least-32-bytes"


def _production_auth_settings():
    return Settings(_env_file=None, app_env="production", supabase_url="https://test.supabase.co", supabase_jwt_secret=SECRET)


def _claims():
    return {"sub": "synthetic-user", "aud": "authenticated", "iss": "https://test.supabase.co/auth/v1", "role": "authenticated", "exp": int(time.time()) + 60}


@pytest.mark.parametrize("missing", ["sub", "exp", "aud", "iss", "role"])
def test_production_rejects_signed_tokens_missing_required_claims(missing):
    claims = _claims()
    del claims[missing]
    with pytest.raises(jwt.InvalidTokenError):
        _decode(jwt.encode(claims, SECRET, algorithm="HS256"), _production_auth_settings())


@pytest.mark.parametrize("claim,value", [("sub", ""), ("sub", "  "), ("iss", "https://other.supabase.co/auth/v1"), ("aud", "anon"), ("role", "service_role"), ("exp", 1)])
def test_production_rejects_wrong_identity_or_lifetime(claim, value):
    claims = {**_claims(), claim: value}
    with pytest.raises(jwt.InvalidTokenError):
        _decode(jwt.encode(claims, SECRET, algorithm="HS256"), _production_auth_settings())


def test_production_accepts_complete_authenticated_token():
    assert _decode(jwt.encode(_claims(), SECRET, algorithm="HS256"), _production_auth_settings())["sub"] == "synthetic-user"


def test_jwks_cache_does_not_keep_individual_revoked_keys_forever(monkeypatch):
    from app import auth

    captured = {}
    monkeypatch.setattr(auth.jwt, "PyJWKClient", lambda url, **kwargs: captured.update(kwargs) or object())
    auth._jwks_client.cache_clear()
    auth._jwks_client("https://synthetic.invalid/jwks")
    auth._jwks_client.cache_clear()
    assert captured == {"cache_keys": False, "lifespan": 300, "timeout": 5}


def _request_probe(chunks, headers=(), method="POST"):
    sent = []
    consumed = []
    entered = []

    async def application(scope, receive, send):
        entered.append(True)
        content = b""
        while True:
            message = await receive()
            content += message.get("body", b"")
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": content})

    pending = list(chunks)

    async def receive():
        consumed.append(True)
        chunk = pending.pop(0) if pending else b""
        return {"type": "http.request", "body": chunk, "more_body": bool(pending)}

    async def send(message):
        sent.append(message)

    middleware = RequestSecurityMiddleware(application, max_body_bytes=20, max_json_bytes=10)
    asyncio.run(middleware({"type": "http", "method": method, "headers": list(headers)}, receive, send))
    return sent, entered, consumed


def test_oversize_content_length_is_rejected_before_read_or_parse():
    sent, entered, consumed = _request_probe([b"x"], [(b"content-length", b"21")])
    assert sent[0]["status"] == 413
    assert not entered and not consumed


@pytest.mark.parametrize("headers", [[], [(b"content-length", b"1")]])
def test_chunked_or_lying_length_cannot_bypass_body_limit(headers):
    sent, entered, _ = _request_probe([b"x" * 10, b"y" * 11], headers)
    assert sent[0]["status"] == 413
    assert not entered


@pytest.mark.parametrize("content_type", [b"application/json", b"application/problem+json; charset=utf-8"])
def test_json_has_smaller_limit_before_parsing(content_type):
    sent, entered, _ = _request_probe([b"x" * 11], [(b"content-type", content_type)])
    assert sent[0]["status"] == 413 and not entered


def test_allowed_body_is_replayed_exactly_and_authenticated_responses_are_private():
    sent, entered, _ = _request_probe([b"first", b"second"], [(b"authorization", b"Bearer synthetic")])
    assert entered and sent[0]["status"] == 200
    assert sent[1]["body"] == b"firstsecond"
    assert dict(sent[0]["headers"])[b"cache-control"] == b"private, no-store"
    assert dict(sent[0]["headers"])[b"x-content-type-options"] == b"nosniff"


@pytest.mark.parametrize("value", [b"-1", b"not-a-number"])
def test_invalid_content_length_is_bad_request(value):
    sent, entered, consumed = _request_probe([], [(b"content-length", value)])
    assert sent[0]["status"] == 400 and not entered and not consumed


@pytest.mark.parametrize("path", ["other-user/data.xlsx", "user/../other/data.csv", "user/%2e%2e/data.csv", "user/%252e%252e/data.csv", "user//data.csv", "user\\other/data.csv", "user/./data.csv"])
def test_storage_paths_reject_cross_user_and_traversal(path):
    with pytest.raises(HTTPException) as rejected:
        normalize_user_storage_path(path, "user")
    assert rejected.value.status_code == 403


def test_storage_paths_allow_owned_file_with_spaces():
    assert normalize_user_storage_path("user/uploads/Mi archivo.xlsx", "user") == "user/uploads/Mi archivo.xlsx"


@pytest.mark.parametrize("url", ["http://docs.google.com/spreadsheets/d/" + "A" * 24, "https://evil.invalid/docs.google.com/spreadsheets/d/" + "A" * 24, "https://docs.google.com.evil.invalid/spreadsheets/d/" + "A" * 24, "https://user:pass@docs.google.com/spreadsheets/d/" + "A" * 24, "https://docs.google.com:444/spreadsheets/d/" + "A" * 24])
def test_google_sheet_input_requires_real_https_google_origin(url):
    with pytest.raises(HTTPException) as rejected:
        connectors._parse_sheet_url(url)
    assert rejected.value.status_code == 400


@pytest.mark.parametrize("target", ["http://127.0.0.1/admin", "https://169.254.169.254/latest/meta-data", "https://docs.google.com.evil.invalid/file", "https://evil.invalid/file", "https://name:secret@docs.google.com/file"])
def test_google_redirect_is_rejected_before_network_request(monkeypatch, target):
    calls = []

    @contextmanager
    def stream(method, url, **kwargs):
        calls.append(url)
        assert kwargs["follow_redirects"] is False
        yield type("Response", (), {"status_code": 302, "headers": {"location": target}})()

    monkeypatch.setattr(connectors.httpx, "stream", stream)
    with pytest.raises(HTTPException) as rejected:
        connectors._download_sheet_csv("A" * 24, "0")
    assert rejected.value.status_code == 502 and len(calls) == 1


def test_google_allows_official_csv_redirect(monkeypatch):
    calls = []

    @contextmanager
    def stream(method, url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            yield type("Response", (), {"status_code": 302, "headers": {"location": "https://doc-01-sheets.googleusercontent.com/export.csv"}})()
        else:
            yield type("Response", (), {"status_code": 200, "headers": {"content-type": "text/csv"}, "iter_bytes": lambda self: iter([b"id,total\n1,200\n"])})()

    monkeypatch.setattr(connectors.httpx, "stream", stream)
    assert connectors._download_sheet_csv("A" * 24, "0")[1] == b"id,total\n1,200\n"
    assert len(calls) == 2


def test_zip_bomb_is_rejected_before_loading_cells():
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/worksheets/sheet1.xml", "0" * 200_000)
    with pytest.raises(UnsupportedFileError):
        _guard_xlsx_zip(content.getvalue())


@pytest.mark.parametrize("formula", ["=HYPERLINK(\"https://example.invalid\")", "+CMD|' /C calc'!A0", "@SUM(A1:A2)", "\t=1+1", "\r\n=1+1", "-12.990"])
def test_untrusted_export_text_is_not_an_executable_formula(formula):
    assert neutralize_excel_formula(formula) == "'" + formula
    assert neutralize_excel_formula(-12.99) == -12.99


class PendingExecutor:
    def __init__(self):
        self.calls = []
        self.lock = threading.Lock()

    def submit(self, *args):
        with self.lock:
            self.calls.append(args)


def _pending_manager(limit=3):
    manager = AnalysisJobManager(Settings(_env_file=None, analysis_max_jobs_per_user=limit))
    manager.executor.shutdown()
    manager.executor = PendingExecutor()
    return manager


def test_job_flood_has_atomic_per_user_limit_and_leaves_room_for_others():
    manager = _pending_manager()

    def submit(index):
        try:
            return manager.submit("user-a", ("synthetic", index), lambda: {})
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(submit, range(30)))
    assert sum(isinstance(result, dict) for result in results) == 3
    assert results.count(429) == 27
    assert manager.submit("user-b", ("synthetic", "other"), lambda: {})["status"] == "queued"
    assert len(manager.executor.calls) == 4


def test_simultaneous_identical_jobs_submit_one_producer():
    manager = _pending_manager()
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(lambda _: manager.submit("user", ("same",), lambda: {}), range(30)))
    assert len({result["job_id"] for result in results}) == 1
    assert len(manager.executor.calls) == 1


def test_retry_cannot_bypass_per_user_capacity_or_other_user_ownership():
    manager = _pending_manager(limit=1)
    failed = manager.submit("user", ("failed",), lambda: {})
    with manager.lock:
        manager.jobs[("user", failed["job_id"])]["status"] = "failed"
    manager.submit("user", ("running",), lambda: {})
    with pytest.raises(HTTPException) as rejected:
        manager.retry("user", failed["job_id"])
    assert rejected.value.status_code == 429
    assert manager.retry("other", failed["job_id"]) is None
    assert len(manager.executor.calls) == 2


@pytest.mark.parametrize("path", ["/clean", "/standardize/batch", "/metrics", "/restore/latest", "/sheets/relationship-dashboard", "/clean/download/"])
def test_sync_heavy_endpoints_share_one_processing_slot(path):
    from app.processing_capacity import HEAVY_WORK_SLOT, ProcessingCapacityMiddleware

    sent = []
    entered = []

    async def application(scope, receive, send):
        entered.append(True)

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        sent.append(message)

    with HEAVY_WORK_SLOT:
        asyncio.run(ProcessingCapacityMiddleware(application)({"type": "http", "method": "POST", "path": path}, receive, send))
    assert not entered and sent[0]["status"] == 429
    assert dict(sent[0]["headers"])[b"retry-after"] == b"10"
    assert json.loads(sent[1]["body"])["code"] == "PROCESSING_BUSY"


def test_browser_can_read_busy_retry_and_download_filename_headers(client):
    from app.main import settings
    from app.processing_capacity import HEAVY_WORK_SLOT

    origin = settings.cors_origins[0]
    with HEAVY_WORK_SLOT:
        response = client.post("/clean", headers={"Origin": origin})
    assert response.status_code == 429
    assert response.json()["code"] == "PROCESSING_BUSY"
    exposed = {name.strip().lower() for name in response.headers["access-control-expose-headers"].split(",")}
    assert {"retry-after", "content-disposition"} <= exposed
    assert response.headers["access-control-allow-origin"] == origin


@pytest.mark.parametrize("method,path", [("GET", "/health"), ("GET", "/analysis/jobs/123"), ("POST", "/assistant/bot"), ("POST", "/clean/batch/jobs"), ("POST", "/analysis/jobs/123/cancel"), ("POST", "/restore/state")])
def test_navigation_bot_and_job_control_do_not_need_processing_slot(method, path):
    from app.processing_capacity import is_synchronous_heavy_request

    assert not is_synchronous_heavy_request({"type": "http", "method": method, "path": path})


def test_background_job_waits_for_sync_processing_slot():
    from app.processing_capacity import HEAVY_WORK_SLOT

    manager = AnalysisJobManager(Settings(_env_file=None))
    entered = threading.Event()

    def producer():
        entered.set()
        return {"ok": True}

    with HEAVY_WORK_SLOT:
        job = manager.submit("user", ("wait-for-legacy",), producer)
        assert not entered.wait(0.05)
        assert manager.get("user", job["job_id"])["status"] == "queued"
    assert entered.wait(1)
    manager.executor.shutdown(wait=True)
    assert manager.get("user", job["job_id"])["status"] == "completed"
