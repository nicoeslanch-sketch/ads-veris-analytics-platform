"""Ejecuta una aceptación local sin exponer rutas por la API ni modificar fuentes.

Ejemplo (desde api/):
  python scripts/run_consolidation_local.py --source matricula=... --output ...
"""

from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path

from app.consolidation.exports import write_pipeline_artifacts
from app.consolidation.ingestion import safe_local_acceptance_path
from app.consolidation.models import SourceRole
from app.consolidation.pipeline import run_local_pipeline
from app.consolidation.resources import ResourceMonitor, directory_size, ensure_temp_capacity
from app.config import get_settings


def parse_source(value: str) -> tuple[SourceRole, Path]:
    role_value, separator, path_value = value.partition("=")
    if not separator:
        raise argparse.ArgumentTypeError("Usa rol=ruta.")
    try:
        role = SourceRole(role_value)
        path = safe_local_acceptance_path(path_value)
    except (ValueError, FileNotFoundError) as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return role, path


def main() -> None:
    parser = argparse.ArgumentParser(description="Consolidación local auditable")
    parser.add_argument("--source", action="append", required=True, type=parse_source)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sources = dict(args.source)
    settings = get_settings()
    ensure_temp_capacity(
        Path(settings.consolidation_temp_dir) if settings.consolidation_temp_dir else args.output.resolve().parent,
        settings,
        source_bytes=sum(path.stat().st_size for path in sources.values()),
    )
    monitor = ResourceMonitor(settings)
    output = run_local_pipeline(sources, settings=settings, monitor=monitor)
    artifacts = write_pipeline_artifacts(
        output,
        args.output.resolve(),
        monitor=monitor,
        chunk_size=settings.consolidation_chunk_size,
    )
    result_shape = (len(output.annual), len(output.annual.columns))
    with monitor.stage("cleanup_temporaries") as stage:
        output.annual = output.annual.head(0)
        gc.collect()
        stage.add(artifact_bytes=directory_size(args.output.resolve()))
    artifact_metrics = output.manifest.resource_metrics.get("artifacts", {})
    metrics = monitor.stop()
    metrics["artifacts"] = artifact_metrics
    metrics["temporary_max_bytes"] = 0
    metrics["temporary_final_bytes"] = 0
    metrics["artifact_output_bytes"] = directory_size(args.output.resolve())
    output.manifest.resource_metrics = metrics
    output.manifest.memory_bytes_estimate = metrics["peak_rss_bytes"]
    artifacts["manifest"].write_text(output.manifest.model_dump_json(indent=2), encoding="utf-8")
    print(json.dumps({
        "status": output.manifest.status.value,
        "shape": result_shape,
        "row_counts": output.manifest.row_counts,
        "artifact_names": sorted(path.name for path in artifacts.values()),
        "resource_metrics": metrics,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
