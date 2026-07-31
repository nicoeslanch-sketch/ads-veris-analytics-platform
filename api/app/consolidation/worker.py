"""Worker local durable basado en la cola persistente de consolidation_runs."""

from __future__ import annotations

import shutil
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from ..config import Settings, get_settings
from .exports import write_historical_consolidated, write_pipeline_artifacts
from .ingestion import sha256_file, storage_source_file, upload_consolidation_artifact
from .models import ConsolidationStatus, IssueSeverity, QualityIssue, SourceRole
from .pipeline import run_local_pipeline
from .repository import MemoryConsolidationRepository, repository_for


class ConsolidationWorker:
    def __init__(self, repository: Any, settings: Settings, output_root: Path | None = None) -> None:
        self.repository = repository
        self.settings = settings
        self.output_root = output_root

    def run_once(self) -> bool:
        run = self.repository.claim_next()
        if not run:
            return False
        run_id = str(run["id"])
        try:
            project = self.repository.get_project(str(run["project_id"]), str(run["user_id"]))
            if not project:
                raise ValueError("project_not_found")
            with ExitStack() as stack:
                local_sources: dict[SourceRole, Path] = {}
                for source in project.get("sources", []):
                    role = SourceRole(source["role"])
                    if source.get("local_path") and isinstance(self.repository, MemoryConsolidationRepository):
                        local_sources[role] = Path(source["local_path"])
                        continue
                    storage_path = source.get("profile", {}).get("storage_path")
                    if not storage_path:
                        raise ValueError(f"source_without_storage:{role.value}")
                    path, _digest = stack.enter_context(storage_source_file(storage_path, str(run["user_id"]), self.settings))
                    local_sources[role] = path
                output = run_local_pipeline(
                    local_sources,
                    mapping_override=project.get("config", {}).get("mapping_manifest"),
                    target_columns=project.get("config", {}).get("target_columns"),
                    cohort=int(project.get("config", {}).get("cohort", 2026)),
                    cohort_id_strategy=project.get("config", {}).get("cohort_id_strategy", "cohort_and_id"),
                )
                previous = self.repository.find_completed(str(run["user_id"]), output.manifest.input_hash, output.manifest.config_hash)
                if previous and str(previous["id"]) != run_id:
                    self.repository.complete_run(run_id, status=previous["status"], input_hash=output.manifest.input_hash, report=previous.get("report", {}), artifacts=[], reused_run_id=str(previous["id"]))
                    return True
                if self.output_root:
                    artifact_dir = self.output_root / run_id
                    artifact_dir.mkdir(parents=True, exist_ok=False)
                    cleanup = False
                else:
                    artifact_dir = Path(tempfile.mkdtemp(prefix=f"ads-consolidation-{run_id}-"))
                    cleanup = True
                try:
                    extra_paths: dict[str, Path] = {}
                    historical = local_sources.get(SourceRole.HISTORICA)
                    if historical and project.get("config", {}).get("include_historical_output"):
                        historical_path, warning = write_historical_consolidated(historical, output.annual, artifact_dir / "DEMRE_2020_2026_CONSOLIDADA.xlsx")
                        if historical_path:
                            extra_paths["historical"] = historical_path
                        elif warning:
                            output.manifest.status = ConsolidationStatus.PARTIAL
                            output.audit_tables.setdefault("historical", []).append({"warning": warning})
                            output.manifest.issues.append(QualityIssue(code=warning, severity=IssueSeverity.WARNING, message="La consolidación histórica no se generó; la base anual permanece disponible."))
                    paths = write_pipeline_artifacts(output, artifact_dir)
                    paths.update(extra_paths)
                    artifacts: list[dict[str, Any]] = []
                    for kind, path in paths.items():
                        if self.output_root:
                            storage_path = str(path)
                        else:
                            storage_path = f"{run['user_id']}/.consolidation/{project['id']}/{run_id}/{path.name}"
                            upload_consolidation_artifact(path, storage_path, str(run["user_id"]), self.settings)
                        artifacts.append({
                            "run_id": run_id, "user_id": str(run["user_id"]), "kind": kind,
                            "storage_path": storage_path, "sha256": sha256_file(path), "bytes": path.stat().st_size,
                        })
                    report = output.manifest.model_dump(mode="json")
                    self.repository.complete_run(run_id, status=output.manifest.status.value, input_hash=output.manifest.input_hash, report=report, artifacts=artifacts)
                finally:
                    if cleanup:
                        shutil.rmtree(artifact_dir, ignore_errors=True)
            return True
        except Exception as exc:
            self.repository.fail_run(run_id, "processing_failed", f"{exc.__class__.__name__}: {str(exc)[:300]}")
            return True

    def run_forever(self) -> None:
        while True:
            if not self.run_once():
                time.sleep(max(0.2, self.settings.consolidation_worker_poll_seconds))


def main() -> None:
    settings = get_settings()
    ConsolidationWorker(repository_for(settings), settings).run_forever()


if __name__ == "__main__":
    main()
