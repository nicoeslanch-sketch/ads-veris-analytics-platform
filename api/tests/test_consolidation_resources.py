from __future__ import annotations

from collections import namedtuple
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import psutil
import pytest

from app.config import Settings
from app.consolidation.exports import logical_sheet_hash, write_dataframe
from app.consolidation.ingestion import read_csv_unique_for_ids
from app.consolidation.ingestion import upload_consolidation_artifact
from app.consolidation.models import SourceRole
from app.consolidation.pipeline import run_local_pipeline
from app.consolidation.repository import MemoryConsolidationRepository
from app.consolidation.resources import (
    ConsolidationResourceError,
    ResourceMonitor,
    ensure_temp_capacity,
    isolated_run_directory,
)
from app.consolidation.target_schema import TARGET_COLUMNS
from app.consolidation.worker import ConsolidationWorker
from tests.test_consolidation_engine import synthetic_sources


def _settings(**overrides) -> Settings:
    return Settings(
        consolidation_memory_soft_limit_mb=3_000,
        consolidation_memory_hard_limit_mb=3_600,
        consolidation_temp_disk_min_mb=1,
        **overrides,
    )


def _synthetic(path: Path):
    path.mkdir(parents=True, exist_ok=True)
    return synthetic_sources.__wrapped__(path)


def test_configurable_memory_limits_fail_with_auditable_code(monkeypatch):
    monitor = ResourceMonitor(_settings())
    monkeypatch.setattr(monitor, "current_rss_bytes", lambda: 4_000 * 1024 * 1024)
    try:
        with pytest.raises(ConsolidationResourceError) as raised:
            monitor.checkpoint("simulated_large_stage")
        assert raised.value.code == "memory_hard_limit_exceeded"
        assert "initial_rss_bytes" in raised.value.metrics
    finally:
        monitor.stop()


def test_resource_monitor_falls_back_when_process_metrics_are_unavailable(monkeypatch):
    monkeypatch.setattr(
        "app.consolidation.resources.psutil.Process",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(psutil.NoSuchProcess(123)),
    )
    monitor = ResourceMonitor(_settings())
    try:
        assert monitor.memory_backend == "rusage"
        assert monitor.current_rss_bytes() >= 0
        assert monitor.snapshot()["memory_backend"] == "rusage"
    finally:
        monitor.stop()


def test_isolated_run_directory_is_removed(tmp_path):
    settings = _settings(consolidation_temp_dir=str(tmp_path))
    with isolated_run_directory(settings, run_id="run-test") as directory:
        marker = directory / "marker.tmp"
        marker.write_bytes(b"temporary")
        assert marker.exists()
    assert not directory.exists()


def test_insufficient_temporary_disk_is_controlled(tmp_path, monkeypatch):
    Usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr("app.consolidation.resources.shutil.disk_usage", lambda _path: Usage(100, 99, 1))
    with pytest.raises(ConsolidationResourceError) as raised:
        ensure_temp_capacity(tmp_path, _settings())
    assert raised.value.code == "temporary_disk_insufficient"
    assert raised.value.metrics["temporary_required_bytes"] > raised.value.metrics["temporary_free_bytes"]


def test_worker_rejects_unvalidated_in_process_concurrency():
    with pytest.raises(ValueError, match="concurrencia 1"):
        ConsolidationWorker(MemoryConsolidationRepository(), _settings(consolidation_worker_concurrency=2))


def test_chunk_interruption_does_not_return_partial_dimension(tmp_path):
    path = tmp_path / "large.csv"
    pd.DataFrame({"ID_aux": [str(index) for index in range(30)], "VALUE": [str(index) for index in range(30)]}).to_csv(path, sep=";", index=False)
    calls = 0

    def interrupt() -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("simulated_interrupt")

    with pytest.raises(RuntimeError, match="simulated_interrupt"):
        read_csv_unique_for_ids(path, ["ID_aux", "VALUE"], frozenset(str(index) for index in range(30)), chunk_rows=5, checkpoint=interrupt)


def test_stale_running_job_is_requeued_safely():
    repo = MemoryConsolidationRepository()
    project = repo.create_project("user", {"name": "P", "config": {}, "config_hash": "a" * 64, "engine_version": "test"})
    run = repo.enqueue_run(project, "b" * 64)
    repo.runs[run["id"]]["status"] = "running"
    repo.runs[run["id"]]["started_at"] = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
    assert repo.recover_interrupted(21_600) == 1
    assert repo.claim_next()["id"] == run["id"]


def test_large_simulated_dimension_is_reduced_per_chunk(tmp_path):
    rows = 25_000
    path = tmp_path / "large.csv"
    pd.DataFrame({"ID_aux": [str(index) for index in range(rows)], "VALUE": ["x"] * rows, "UNUSED": ["z"] * rows}).to_csv(path, sep=";", index=False)
    authority = frozenset(str(index) for index in range(0, rows, 2))
    frame, metrics = read_csv_unique_for_ids(path, ["ID_aux", "VALUE"], authority, chunk_rows=1_000)
    assert len(frame) == len(authority)
    assert metrics == {
        "rows_read": rows,
        "rows_matched": len(authority),
        "rows_retained": len(authority),
        "ambiguous_keys": 0,
        "chunks": 25,
    }


def test_dimension_reducer_does_not_concatenate_full_chunks(tmp_path, monkeypatch):
    path = tmp_path / "dimension.csv"
    pd.DataFrame({"ID_aux": ["1", "2", "3"], "VALUE": ["a", "b", "c"]}).to_csv(path, sep=";", index=False)
    monkeypatch.setattr(pd, "concat", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("concat not allowed")))
    frame, _metrics = read_csv_unique_for_ids(path, ["ID_aux", "VALUE"], frozenset({"1", "2"}), chunk_rows=1)
    assert frame["ID_aux"].tolist() == ["1", "2"]


def test_streaming_export_has_chunks_and_stable_logical_hash(tmp_path):
    frame = pd.DataFrame({"id": pd.Series(["001", "002", "003"], dtype="string"), "value": ["a", None, "=unsafe"]})
    first = tmp_path / "first.xlsx"
    second = tmp_path / "second.xlsx"
    metrics = write_dataframe(first, frame, sheet_name="BASE DE DATOS", chunk_size=2)
    write_dataframe(second, frame, sheet_name="BASE DE DATOS", chunk_size=1)
    assert metrics["chunks"] == 2
    assert logical_sheet_hash(first) == logical_sheet_hash(second) == metrics["logical_sha256"]


def test_metrics_are_aggregated_and_contain_no_row_values():
    monitor = ResourceMonitor(_settings())
    with monitor.stage("read_archivo_b") as stage:
        stage.add(rows_read=10, rows_generated=5, chunks=2)
    metrics = monitor.stop()
    serialized = str(metrics)
    assert "ID_aux" not in serialized
    assert "nombre" not in serialized.casefold()
    assert metrics["stages"][0]["rows_read"] == 10


def test_pipeline_is_logically_identical_across_chunk_sizes(tmp_path):
    sources = _synthetic(tmp_path / "sources")
    output_a = run_local_pipeline(sources, settings=_settings(consolidation_chunk_size=2))
    output_b = run_local_pipeline(sources, settings=_settings(consolidation_chunk_size=7))
    pd.testing.assert_frame_equal(output_a.annual, output_b.annual)
    assert output_a.manifest.row_counts == output_b.manifest.row_counts
    assert output_a.manifest.recoding_coverage == output_b.manifest.recoding_coverage


def test_real_manifest_classifies_every_fully_empty_column(tmp_path):
    sources = _synthetic(tmp_path / "sources")
    output = run_local_pipeline(sources, settings=_settings())
    fully_empty = [row for row in output.audit_tables["null_reasons"] if row["count"] == len(output.annual)]
    assert fully_empty
    assert all(row.get("reason_code") for row in fully_empty)
    categories = {row["reason_code"] for row in fully_empty}
    assert {
        "unsupported_in_2026",
        "normalization_pending",
        "derivation_pending",
        "historical_method_not_available",
    } <= categories


def test_default_schema_remains_exactly_92_columns(tmp_path):
    sources = _synthetic(tmp_path / "sources")
    output = run_local_pipeline({role: path for role, path in sources.items() if role is not SourceRole.ARCHIVO_B}, settings=_settings())
    assert tuple(output.annual.columns) == TARGET_COLUMNS


def test_retry_reuses_only_identical_immutable_artifact(tmp_path, monkeypatch):
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"derived-content")

    class Conflict:
        status_code = 409

    class Existing:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def iter_bytes(self, _size):
            yield b"derived-content"

    monkeypatch.setattr("app.consolidation.ingestion.httpx.post", lambda *_args, **_kwargs: Conflict())
    monkeypatch.setattr("app.consolidation.ingestion.httpx.stream", lambda *_args, **_kwargs: Existing())
    upload_consolidation_artifact(
        artifact,
        "user/.consolidation/project/run/artifact.bin",
        "user",
        Settings(supabase_url="https://example.test", supabase_service_role_key="secret"),
    )
