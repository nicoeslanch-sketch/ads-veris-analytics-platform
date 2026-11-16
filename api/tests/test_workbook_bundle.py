from datetime import datetime
from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET

import openpyxl
import pytest

from app.consolidation.workbook_bundle import combine_workbooks
from app.processing_capacity import is_synchronous_heavy_request


def book(title='Datos', rows=None):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title
    for row in rows or [['ID', 'Valor'], ['001', 12.25], ['001', 12.25]]:
        ws.append(row)
    out = BytesIO()
    wb.save(out)
    wb.close()
    return out.getvalue()


def cached_formula(content, result):
    out = BytesIO()
    ns = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
    with ZipFile(BytesIO(content)) as src, ZipFile(out, 'w') as dst:
        for name in src.namelist():
            value = src.read(name)
            if name == 'xl/worksheets/sheet1.xml':
                root = ET.fromstring(value)
                root.find('.//' + ns + 'c/' + ns + 'v').text = str(result)
                value = ET.tostring(root)
            dst.writestr(name, value)
    return out.getvalue()


def test_preserves_all_sheets_rows_duplicates_dates_and_id_strings():
    source = book()
    output = combine_workbooks([('one.xlsx', source), ('two.xlsx', book('datos', [[datetime(2026, 1, 2), 5]]))])
    wb = openpyxl.load_workbook(BytesIO(output), data_only=False)
    assert wb.sheetnames == ['Datos', 'datos (2)']
    assert list(wb['Datos'].values) == [('ID', 'Valor'), ('001', 12.25), ('001', 12.25)]
    assert wb['datos (2)']['A1'].value == datetime(2026, 1, 2)
    assert wb['datos (2)']['A1'].is_date
    wb.close()


def test_copies_cached_result_not_formula_and_never_executes_text():
    formula = cached_formula(book(rows=[['=SUM(1,2)']]), 3)
    text = openpyxl.Workbook()
    text.active['A1'] = '=HYPERLINK("https://example.com")'
    text.active['A1'].data_type = 's'
    stream = BytesIO()
    text.save(stream)
    output = combine_workbooks([('formulas.xlsx', formula), ('text.xlsx', stream.getvalue())])
    wb = openpyxl.load_workbook(BytesIO(output), data_only=False)
    assert wb.worksheets[0]['A1'].value == 3
    assert wb.worksheets[0]['A1'].data_type == 'n'
    assert wb.worksheets[1]['A1'].value.startswith('=HYPERLINK')
    assert wb.worksheets[1]['A1'].data_type == 's'
    wb.close()


def test_missing_formula_cache_fails_without_partial_output():
    with pytest.raises(ValueError, match='formulas sin resultado'):
        combine_workbooks([('one.xlsx', book()), ('two.xlsx', book(rows=[['=1+2']]))])


@pytest.mark.parametrize('files', [[], [('a.xlsx', b'')], [('a.csv', b'a,b'), ('b.xlsx', book())]])
def test_rejects_invalid_inputs(files):
    with pytest.raises(ValueError):
        combine_workbooks(files)


def test_bounds_sparse_worksheet_expansion():
    wb = openpyxl.Workbook()
    wb.active['KN200000'] = 1
    out = BytesIO()
    wb.save(out)
    with pytest.raises(ValueError, match='supera 500.000'):
        combine_workbooks([('a.xlsx', book()), ('sparse.xlsx', out.getvalue())])


def test_combiner_uses_heavy_computation_admission():
    assert is_synchronous_heavy_request({'method': 'POST', 'path': '/consolidation/workbook'})


@pytest.mark.parametrize('mode,status', [('anonymous', 401), ('disabled', 404), ('non_admin', 403), ('allowed', 200)])
def test_endpoint_authorization_and_download(mode, status):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.auth import AuthenticatedUser, get_current_user
    from app.config import Settings, get_settings

    settings = Settings(consolidation_enabled=mode != 'disabled', consolidation_admin_only=True,
                        dev_auth_bypass=False, supabase_url='', supabase_service_role_key='',
                        supabase_jwt_secret='local-test-key-which-is-long-enough')
    if mode == 'allowed':
        settings = settings.model_copy(update={'dev_auth_bypass': True})
    saved = app.dependency_overrides.copy()
    try:
        app.dependency_overrides[get_settings] = lambda: settings
        if mode != 'anonymous':
            app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id='test', email='test@example.test', claims={})
        response = TestClient(app).post('/consolidation/workbook', files=[
            ('files', ('a.xlsx', book())), ('files', ('b.xlsx', book()))])
        assert response.status_code == status, response.text[:200]
        if status == 200:
            assert response.headers['cache-control'] == 'private, no-store'
            assert 'attachment' in response.headers['content-disposition']
            wb = openpyxl.load_workbook(BytesIO(response.content))
            assert len(wb.worksheets) == 2
            wb.close()
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved)
