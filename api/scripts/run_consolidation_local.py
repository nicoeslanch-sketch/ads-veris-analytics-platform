"""Ejecuta una aceptación local sin exponer rutas por la API ni modificar fuentes.

Ejemplo (desde api/):
  python scripts/run_consolidation_local.py --source matricula=... --output ...
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.consolidation.exports import annual_shape, write_pipeline_artifacts
from app.consolidation.ingestion import safe_local_acceptance_path
from app.consolidation.models import SourceRole
from app.consolidation.pipeline import run_local_pipeline


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
    output = run_local_pipeline(sources)
    artifacts = write_pipeline_artifacts(output, args.output.resolve())
    print(json.dumps({
        "status": output.manifest.status.value,
        "shape": annual_shape(artifacts["annual"]),
        "row_counts": output.manifest.row_counts,
        "artifact_names": sorted(path.name for path in artifacts.values()),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
