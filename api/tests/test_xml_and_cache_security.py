"""Regression checks for findings from the local static analysis."""

import hashlib
import io
import zipfile

import pytest
from defusedxml.common import DefusedXmlException

from app.engine.loader import xlsx_sheet_names, _worksheet_xml_by_name
from app.routes.pipeline import _frame_key, _cache_key


@pytest.mark.parametrize("reader", [xlsx_sheet_names, lambda content: _worksheet_xml_by_name(content, ["Ventas"])])
def test_workbook_name_readers_refuse_entity_expansion(reader):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("xl/workbook.xml", b'<!DOCTYPE workbook [<!ENTITY label "Ventas">]>'
                         b'<workbook><sheets><sheet name="&label;"/></sheets></workbook>')
    with pytest.raises(DefusedXmlException):
        reader(output.getvalue())


def test_content_cache_fingerprints_use_sha256_with_context_boundaries():
    content = b"synthetic dataset content"
    expected = hashlib.sha256(content).digest()
    assert _frame_key("raw", "test.xlsx", content, "Ventas")[1] == expected
    assert _cache_key(content, {}, True, None, None)[4] == expected
    assert _frame_key("raw", "test.xlsx", content, "Ventas") != _frame_key("raw", "test.xlsx", content, "Costos")
    assert _cache_key(content, {}, True, None, None, cache_dataset_id="a") != _cache_key(content, {}, True, None, None, cache_dataset_id="b")
