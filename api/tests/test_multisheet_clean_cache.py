from collections import OrderedDict
from types import SimpleNamespace

import pandas as pd
import pytest

from app.routes import pipeline


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch):
    monkeypatch.setattr(pipeline, "_METRICS_CLEAN_CACHE", OrderedDict())


def frame_result(cells):
    return {"_df_limpio": pd.DataFrame({"amount": list(range(cells))})}


def test_small_sheets_share_a_bounded_cache():
    for index in range(18):
        pipeline._metrics_clean_cache_store(str(index), frame_result(10))
    for index in range(18):
        assert pipeline._metrics_clean_cache_get(str(index)) is not None


def test_cell_budget_evicts_least_recently_used_sheet(monkeypatch):
    monkeypatch.setattr(pipeline, "_METRICS_CLEAN_CACHE_CELL_BUDGET", 10, raising=False)
    pipeline._metrics_clean_cache_store("a", frame_result(4))
    pipeline._metrics_clean_cache_store("b", frame_result(4))
    assert pipeline._metrics_clean_cache_get("a") is not None
    pipeline._metrics_clean_cache_store("c", frame_result(4))
    assert set(pipeline._METRICS_CLEAN_CACHE) == {"a", "c"}


def test_entry_larger_than_budget_does_not_evict_useful_data(monkeypatch):
    monkeypatch.setattr(pipeline, "_METRICS_CLEAN_CACHE_CELL_BUDGET", 10, raising=False)
    pipeline._metrics_clean_cache_store("small", frame_result(2))
    pipeline._metrics_clean_cache_store("oversized", frame_result(11))
    assert set(pipeline._METRICS_CLEAN_CACHE) == {"small"}


def test_empty_sheets_still_have_entry_limit(monkeypatch):
    monkeypatch.setattr(pipeline, "_METRICS_CLEAN_CACHE_MAX_ENTRIES", 3)
    for index in range(4):
        pipeline._metrics_clean_cache_store(str(index), frame_result(0))
    assert set(pipeline._METRICS_CLEAN_CACHE) == {"1", "2", "3"}


def test_replacing_entry_does_not_double_count_cells(monkeypatch):
    monkeypatch.setattr(pipeline, "_METRICS_CLEAN_CACHE_CELL_BUDGET", 10, raising=False)
    pipeline._metrics_clean_cache_store("a", frame_result(4))
    pipeline._metrics_clean_cache_store("b", frame_result(4))
    pipeline._metrics_clean_cache_store("a", frame_result(6))
    assert set(pipeline._METRICS_CLEAN_CACHE) == {"a", "b"}


def test_multisheet_revisit_needs_neither_network_nor_recleaning(monkeypatch):
    from tests.test_batch_pipeline import _book

    settings = SimpleNamespace(
        supabase_service_role_key="test-only", ai_refine_enabled=False,
        analysis_redis_url="", analysis_cache_ttl_seconds=1800,
        analysis_lock_ttl_seconds=600,
    )
    monkeypatch.setattr(pipeline, "get_settings", lambda: settings)
    monkeypatch.setattr(pipeline, "upload_export_cache", lambda *args: None)
    monkeypatch.setattr(pipeline, "download_export_cache", lambda *args: None)
    manifest = {"hojas": [{
        "nombre": name, "procesar": True, "rules": {}, "mapping": {},
        "scope": {}, "eliminar_duplicados": False, "revision": 7,
    } for name in ("Enero", "Febrero")]}
    args = ("libro.xlsx", _book(), manifest, "revisit-dataset", None, "user-a")
    expected, _, _ = pipeline._processed_manifest_frames(*args)
    monkeypatch.setattr(pipeline, "download_export_cache", lambda *args: pytest.fail("Repeated Storage download"))
    monkeypatch.setattr(pipeline, "_load_batch_frames_cached", lambda *args: pytest.fail("Repeated XLSX load"))
    monkeypatch.setattr(pipeline, "_analyze_cached", lambda *args, **kwargs: pytest.fail("Repeated cleaning"))
    actual, _, _ = pipeline._processed_manifest_frames(*args)
    for name in expected:
        pd.testing.assert_frame_equal(expected[name], actual[name])
    actual["Enero"].iloc[0, 0] = "modified-copy"
    untouched, _, _ = pipeline._processed_manifest_frames(*args)
    pd.testing.assert_frame_equal(expected["Enero"], untouched["Enero"])
