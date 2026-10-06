from contextlib import contextmanager
import json

from fastapi import HTTPException
import httpx
import pytest

from app import storage


@pytest.fixture
def storage_response(monkeypatch):
    settings = storage.get_settings()
    monkeypatch.setattr(settings, "supabase_url", "https://storage.test")
    monkeypatch.setattr(settings, "supabase_service_role_key", "test-only")

    def install(status_code, content):
        @contextmanager
        def stream(*args, **kwargs):
            yield httpx.Response(status_code, content=content)

        monkeypatch.setattr(storage.httpx, "stream", stream)

    return install


@pytest.mark.parametrize("body", [
    {"code": "NoSuchKey", "message": "Object not found"},
    {"httpStatusCode": 400, "code": "NoSuchKey", "message": "Object not found"},
    {"statusCode": "404", "error": "not_found", "message": "Object not found"},
    {"statusCode": 404, "error": "not_found", "message": "Object not found"},
])
def test_missing_object_wrapped_in_400_is_cache_miss(storage_response, body):
    storage_response(400, json.dumps(body).encode())
    assert storage.download_export_cache("owner/.analysis/dataset/clean.json.gz") is None


@pytest.mark.parametrize("status_code,body", [
    (400, {"code": "NoSuchBucket"}),
    (400, {"code": "InvalidRequest"}),
    (400, {"statusCode": "403", "error": "not_found"}),
    (400, {"statusCode": "404", "error": "unauthorized"}),
    (400, {"message": "Object not found"}),
    (400, {"code": "AccessDenied"}),
    (401, {"code": "NoSuchKey"}),
    (403, {"code": "NoSuchKey"}),
    (429, {"code": "NoSuchKey"}),
    (500, {"code": "NoSuchKey"}),
    (503, {"code": "NoSuchKey"}),
])
def test_real_storage_failure_is_not_silently_treated_as_missing(storage_response, status_code, body):
    storage_response(status_code, json.dumps(body).encode())
    with pytest.raises(HTTPException) as error:
        storage.download_export_cache("owner/.analysis/dataset/clean.json.gz")
    assert error.value.status_code == 502


@pytest.mark.parametrize("body", [
    b"<html>not found</html>", b"null", b"[]", b"404", b'"NoSuchKey"', b"\xff",
    b"[" * 2000 + b"]" * 2000,
    b'{"code":"NoSuchKey","message":"' + b"x" * 9000 + b'"}',
])
def test_invalid_or_excessive_error_body_is_not_a_cache_miss(storage_response, body):
    storage_response(400, body)
    with pytest.raises(HTTPException) as error:
        storage.download_export_cache("owner/.analysis/dataset/clean.json.gz")
    assert error.value.status_code == 502


def test_error_parser_stops_at_size_limit():
    class OversizedError:
        status_code = 400

        def iter_bytes(self):
            yield b"x" * (storage._MAX_STORAGE_ERROR_BYTES + 1)
            raise AssertionError("Do not continue reading an oversized error")

    assert not storage._legacy_missing_object(OversizedError())


def test_successful_artifact_is_not_parsed_as_error(storage_response):
    storage_response(200, b'{"code":"NoSuchKey"}')
    assert storage.download_export_cache("owner/.analysis/dataset/clean.json.gz") == b'{"code":"NoSuchKey"}'


def test_original_file_does_not_become_optional_cache(storage_response):
    storage_response(400, b'{"code":"NoSuchKey"}')
    with pytest.raises(HTTPException):
        storage.download_from_storage("owner/original.xlsx")
