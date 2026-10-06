from types import SimpleNamespace

import pandas as pd
import pytest

from app.clean_artifacts import (
    InvalidCleanArtifact,
    pack_clean_artifact,
    unpack_clean_artifact,
)


def test_clean_artifact_round_trip_preserves_values_types_and_attrs():
    frame = pd.DataFrame(
        {
            "Fecha": pd.to_datetime(["2026-01-02", "2026-01-03"]),
            "Monto": [1234.5, 9876.25],
            "Canal": ["Web", "Tienda"],
        }
    )
    frame.attrs = {
        "adsveris_numeric_canonical": True,
        "adsveris_source_rows": [2, 3],
    }

    payload = pack_clean_artifact(
        frame, {"identity": "abc", "result": {"resumen": {}}}, signing_key="secret"
    )
    restored, metadata = unpack_clean_artifact(payload, signing_key="secret")

    pd.testing.assert_frame_equal(restored, frame)
    assert restored.attrs == frame.attrs
    assert metadata["identity"] == "abc"


def test_clean_artifact_rejects_tampering_before_deserializing():
    payload = pack_clean_artifact(
        pd.DataFrame({"Monto": [100]}), {"identity": "abc"}, signing_key="secret"
    )
    tampered = payload[:-1] + bytes([payload[-1] ^ 1])

    with pytest.raises(InvalidCleanArtifact, match="signature"):
        unpack_clean_artifact(tampered, signing_key="secret")


def test_metrics_reuses_durable_clean_frame_after_memory_cache_is_cold(monkeypatch):
    from app.routes import pipeline

    content = (
        "Fecha,Ingresos,Canal\n"
        "2026-01-02,$ 1.200,Web\n"
        "2026-01-03,$ 800,Tienda\n"
    ).encode("utf-8")
    objects: dict[str, bytes] = {}
    settings = SimpleNamespace(
        supabase_service_role_key="server-secret",
        ai_refine_enabled=False,
    )
    monkeypatch.setattr(pipeline, "get_settings", lambda: settings)
    monkeypatch.setattr(
        pipeline, "upload_export_cache", lambda path, payload: objects.__setitem__(path, payload)
    )
    monkeypatch.setattr(pipeline, "download_export_cache", lambda path: objects.get(path))

    with pipeline._CACHE_LOCK:
        pipeline._CLEAN_CACHE.clear()
    with pipeline._FRAME_CACHE_LOCK:
        pipeline._FRAME_CACHE.clear()
    with pipeline._METRICS_CLEAN_CACHE_LOCK:
        pipeline._METRICS_CLEAN_CACHE.clear()

    first = pipeline._metrics_sync(
        "ventas.csv",
        content,
        None,
        None,
        None,
        cache_dataset_id="dataset-1",
        cache_revision=7,
        cache_user_id="user-1",
    )
    assert first["kpis"]["ingresos_totales"]["valor"] == 2000
    assert len(objects) == 1

    with pipeline._CACHE_LOCK:
        pipeline._CLEAN_CACHE.clear()
    with pipeline._FRAME_CACHE_LOCK:
        pipeline._FRAME_CACHE.clear()
    with pipeline._METRICS_CLEAN_CACHE_LOCK:
        pipeline._METRICS_CLEAN_CACHE.clear()
    monkeypatch.setattr(
        pipeline,
        "_analyze_cached",
        lambda *args, **kwargs: pytest.fail("the full cleaning engine ran again"),
    )

    restored = pipeline._metrics_sync(
        "ventas.csv",
        content,
        None,
        None,
        None,
        cache_dataset_id="dataset-1",
        cache_revision=7,
        cache_user_id="user-1",
        business_filters={"canal": "Web"},
    )

    assert restored["kpis"] == first["kpis"]


def test_metrics_discards_artifact_when_cleaning_revision_changes(monkeypatch):
    from app.routes import pipeline

    content = b"Fecha,Monto\n2026-01-02,100\n"
    objects: dict[str, bytes] = {}
    settings = SimpleNamespace(
        supabase_service_role_key="server-secret",
        ai_refine_enabled=False,
    )
    monkeypatch.setattr(pipeline, "get_settings", lambda: settings)
    monkeypatch.setattr(
        pipeline, "upload_export_cache", lambda path, payload: objects.__setitem__(path, payload)
    )
    monkeypatch.setattr(pipeline, "download_export_cache", lambda path: objects.get(path))

    pipeline._metrics_sync(
        "ventas.csv",
        content,
        None,
        None,
        None,
        cache_dataset_id="dataset-2",
        cache_revision=1,
        cache_user_id="user-1",
    )
    with pipeline._CACHE_LOCK:
        pipeline._CLEAN_CACHE.clear()
    with pipeline._FRAME_CACHE_LOCK:
        pipeline._FRAME_CACHE.clear()
    with pipeline._METRICS_CLEAN_CACHE_LOCK:
        pipeline._METRICS_CLEAN_CACHE.clear()

    original = pipeline._analyze_cached
    calls = 0

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(pipeline, "_analyze_cached", counted)
    pipeline._metrics_sync(
        "ventas.csv",
        content,
        None,
        None,
        None,
        cache_dataset_id="dataset-2",
        cache_revision=2,
        cache_user_id="user-1",
    )

    assert calls == 1


def test_clean_artifact_identity_includes_user_even_with_identical_dataset_and_input():
    from app.routes import pipeline

    args = (b"same-content", {}, {}, {}, "Ventas", False, "same-dataset", 7)
    assert pipeline._metrics_clean_artifact_identity(*args, "user-a") != (
        pipeline._metrics_clean_artifact_identity(*args, "user-b")
    )


def test_warm_clean_artifact_memory_does_not_cross_user_boundary(monkeypatch):
    from app.routes import pipeline

    content = b"Fecha,Monto\n2026-01-02,100\n"
    objects = {}
    settings = SimpleNamespace(supabase_service_role_key="server-secret", ai_refine_enabled=False)
    monkeypatch.setattr(pipeline, "get_settings", lambda: settings)
    monkeypatch.setattr(pipeline, "upload_export_cache", lambda path, payload: objects.__setitem__(path, payload))
    monkeypatch.setattr(pipeline, "download_export_cache", lambda path: objects.get(path))
    with pipeline._METRICS_CLEAN_CACHE_LOCK:
        pipeline._METRICS_CLEAN_CACHE.clear()
    result = pipeline._analyze_cached("ventas.csv", content, None, True)
    args = ("ventas.csv", content, None, None, None, None, False, "shared-dataset", 7)
    pipeline._store_metrics_clean_artifact(*args, "user-a", result)
    assert pipeline._load_metrics_clean_artifact(*args, "user-a") is not None
    assert pipeline._load_metrics_clean_artifact(*args, "user-b") is None
    # A wrongly placed signed object still has an identity for the original user.
    first_path = pipeline._metrics_clean_artifact_path("user-a", "shared-dataset", None)
    other_path = pipeline._metrics_clean_artifact_path("user-b", "shared-dataset", None)
    objects[other_path] = objects[first_path]
    assert pipeline._load_metrics_clean_artifact(*args, "user-b") is None


@pytest.mark.parametrize("kind", ["business", "catalog", "dashboard"])
def test_relationship_views_reuse_persisted_clean_tables_after_cold_start(monkeypatch, kind):
    from app.routes import pipeline
    from tests.test_batch_pipeline import _book

    content = _book()
    manifest = {"hojas": [{
        "nombre": name, "procesar": True, "rules": {}, "mapping": {},
        "scope": {}, "eliminar_duplicados": False, "revision": 7,
    } for name in ("Enero", "Febrero")]}
    objects = {}
    settings = SimpleNamespace(
        supabase_service_role_key="server-secret", ai_refine_enabled=False,
        analysis_redis_url="", analysis_cache_ttl_seconds=1800,
        analysis_lock_ttl_seconds=600,
    )
    monkeypatch.setattr(pipeline, "get_settings", lambda: settings)
    monkeypatch.setattr(pipeline, "upload_export_cache", lambda path, payload: objects.__setitem__(path, payload))
    monkeypatch.setattr(pipeline, "download_export_cache", lambda path: objects.get(path))
    with pipeline._METRICS_CLEAN_CACHE_LOCK:
        pipeline._METRICS_CLEAN_CACHE.clear()
    expected, _, _ = pipeline._processed_manifest_frames(
        "libro.xlsx", content, manifest, "relationship-dataset", None, "user-a",
    )
    assert len(objects) == 2
    for lock, cache in ((pipeline._CACHE_LOCK, pipeline._CLEAN_CACHE),
                        (pipeline._FRAME_CACHE_LOCK, pipeline._FRAME_CACHE),
                        (pipeline._METRICS_CLEAN_CACHE_LOCK, pipeline._METRICS_CLEAN_CACHE),
                        (pipeline._ANALYSIS_CACHE_LOCK, pipeline._ANALYSIS_CACHE)):
        with lock:
            cache.clear()
    monkeypatch.setattr(pipeline, "_load_batch_frames_cached", lambda *args: pytest.fail("source XLSX reopened"))
    monkeypatch.setattr(pipeline, "_analyze_cached", lambda *args, **kwargs: pytest.fail("cleaning repeated"))
    captured = {}

    def capture_frames(frames, *args, **kwargs):
        captured.update(frames)
        return [] if kind == "business" else {"candidates": []}

    if kind == "business":
        monkeypatch.setattr(pipeline, "detect_relationships", capture_frames)
        monkeypatch.setattr(pipeline, "analyze_business_workbook", lambda *args: None)
        result = pipeline._relationships_cached_sync(
            "libro.xlsx", content, manifest, None, "relationship-dataset", None, "user-a",
        )
        assert result["candidates"] == []
    elif kind == "catalog":
        monkeypatch.setattr(pipeline, "detect_relationship_catalog", capture_frames)
        result = pipeline._relationship_catalog_cached_sync(
            "libro.xlsx", content, manifest, "relationship-dataset", "user-a",
        )
        assert result == {"candidates": []}
    else:
        monkeypatch.setattr(pipeline, "build_relationship_dashboard", capture_frames)
        result = pipeline._relationship_dashboard_cached_sync(
            "libro.xlsx", content, manifest,
            {"left_sheet": "Enero", "right_sheet": "Febrero"},
            None, None, "relationship-dataset", "user-a",
        )
        assert result == {"candidates": []}
    assert set(captured) == set(expected)
    for name, frame in captured.items():
        pd.testing.assert_frame_equal(frame, expected[name])
