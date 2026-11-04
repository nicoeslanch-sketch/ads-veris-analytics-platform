"""Bounded synthetic probes; no private account data or production writes."""

import io
import logging
import zipfile

import httpx
import pytest
from fastapi import HTTPException, UploadFile
from fastapi.routing import APIRoute
from openpyxl import Workbook

from app.auth import get_current_user, get_verified_user
from app.config import Settings
from app.engine.loader import UnsupportedFileError, validate_source_content
from app.main import app, validate_production_config
from app.routes import ai, storage_upload


def workbook_bytes(extra=None):
    output = io.BytesIO()
    book = Workbook()
    book.active.append(['Producto', 'Ingreso'])
    book.active.append(['Prueba', 10])
    book.save(output)
    if extra:
        with zipfile.ZipFile(output, 'a') as archive:
            for name, value in extra.items():
                archive.writestr(name, value)
    return output.getvalue()


@pytest.mark.parametrize('name,content', [
    ('fake.xlsx', b'not an Excel'), ('fake.csv', b'MZ\x00binary'),
    ('fake.csv', b'%PDF-1.7\n'), ('fake.csv', b'col\nabc\x00def'),
    ('empty.csv', b'\xef\xbb\xbf \r\n'),
    ('macro.xlsx', workbook_bytes({'xl/vbaProject.bin': b'synthetic'})),
    ('control.xlsx', workbook_bytes({'xl/activeX/activeX1.bin': b'synthetic'})),
    ('path.xlsx', workbook_bytes({'../outside': b'synthetic'})),
    ('not-workbook.xlsx', b'PK\x03\x04'),
])
def test_invalid_source_never_reaches_storage(monkeypatch, name, content):
    monkeypatch.setattr(storage_upload, 'require_capability_for_user', lambda *a: None)
    monkeypatch.setattr(storage_upload, 'safe_storage_write', lambda *a: pytest.fail('Must not store invalid content'))
    settings = Settings(_env_file=None, supabase_url='https://example.invalid', supabase_service_role_key='test')
    upload = UploadFile(filename=name, file=io.BytesIO(content), size=len(content))
    with pytest.raises(HTTPException) as error:
        storage_upload._upload_source(upload, 'synthetic-user', settings)
    assert error.value.status_code == 422


@pytest.mark.parametrize('name,content', [
    ('normal.xlsx', workbook_bytes()), ('accents.csv', 'nombre;valor\nCafe;10\n'.encode()),
    ('latin.csv', 'nombre;valor\nPi\xf1a;10\n'.encode('latin-1')),
    ('quoted.csv', b'name,notes\nitem,"line one\nline two"\n'),
])
def test_preflight_keeps_supported_files_unchanged(monkeypatch, name, content):
    monkeypatch.setattr(storage_upload, 'require_capability_for_user', lambda *a: None)
    calls = []
    def write(path, size, kind, settings, sender):
        calls.append((path, size, kind))
        return sender()
    def post(url, **kwargs):
        assert b''.join(kwargs['content']) == content
        return httpx.Response(200)
    monkeypatch.setattr(storage_upload, 'safe_storage_write', write)
    monkeypatch.setattr(storage_upload, '_storage_object_url', lambda path: 'https://example.invalid/' + path)
    monkeypatch.setattr(storage_upload.httpx, 'post', post)
    settings = Settings(_env_file=None, supabase_url='https://example.invalid', supabase_service_role_key='test')
    upload = UploadFile(filename=name, file=io.BytesIO(content), size=len(content))
    result = storage_upload._upload_source(upload, 'synthetic-user', settings)
    assert result['bytes'] == len(content)
    assert calls[0][0].startswith('synthetic-user/')


def test_generic_zip_not_accepted_as_workbook():
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('notes.txt', 'not Excel')
    with pytest.raises(UnsupportedFileError):
        validate_source_content('fake.xlsx', output.getvalue())


def test_upload_distributed_budget_rejects_before_read(monkeypatch):
    monkeypatch.setattr(storage_upload, 'require_capability_for_user', lambda *a: None)
    def budget(bucket, settings, **kwargs):
        assert bucket == 'upload:synthetic-user' and kwargs == {'limit': 20, 'window': 60}
        raise HTTPException(429, 'Limited')
    monkeypatch.setattr(storage_upload, 'consume_budget', budget)
    upload = UploadFile(filename='file.csv', file=io.BytesIO(b'a\n1'), size=3)
    settings = Settings(_env_file=None, app_env='production', supabase_url='https://example.invalid', supabase_service_role_key='test')
    with pytest.raises(HTTPException) as error:
        storage_upload._upload_source(upload, 'synthetic-user', settings)
    assert error.value.status_code == 429 and upload.file.tell() == 0


@pytest.mark.parametrize('origins,regex', [
    ('*', ''), ('null', ''), ('http://example.com', ''),
    ('https://name:password@example.com', ''), ('https://example.com?token=secret', ''),
    ('https://example.com', '.*'), ('https://example.com', r'https://.*'),
    ('https://example.com', r'https://.*\.vercel\.app'), ('https://example.com', '['),
])
def test_unsafe_production_cors_is_rejected(origins, regex):
    cfg = Settings(_env_file=None, app_env='production', supabase_url='https://example.supabase.co',
                   supabase_service_role_key='test', plan_enforcement=True,
                   allowed_origins=origins, allowed_origin_regex=regex)
    assert validate_production_config(cfg)


def test_provider_error_logging_does_not_echo_sensitive_text(caplog):
    with caplog.at_level(logging.WARNING, logger=ai.__name__):
        incident = ai._log_incident(RuntimeError('customer-data secret-token raw-prompt'))
    assert incident in caplog.text and 'RuntimeError' in caplog.text
    assert not any(text in caplog.text for text in ('customer-data', 'secret-token', 'raw-prompt'))


def _dependencies(dependant):
    yield dependant.call
    for child in dependant.dependencies:
        yield from _dependencies(child)


def test_every_private_api_route_has_backend_authentication():
    public = {'/health', '/version'}
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path not in public:
            assert {get_current_user, get_verified_user}.intersection(_dependencies(route.dependant)), route.path


def test_cors_log_does_not_echo_attacker_origin_or_private_path(client, caplog):
    with caplog.at_level(logging.WARNING):
        response = client.get('/private-name?secret=hidden', headers={'Origin': 'https://attacker-secret.invalid'})
    assert response.status_code == 404
    assert 'attacker-secret' not in caplog.text and 'private-name' not in caplog.text
