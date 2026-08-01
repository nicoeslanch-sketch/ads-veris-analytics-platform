"""Worker durable separado: la API solo encola y consulta ejecuciones."""

from __future__ import annotations

import gc
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from ..config import Settings, get_settings
from .exports import write_historical_consolidated, write_historical_generic, write_pipeline_artifacts
from .generic_pipeline import run_general_pipeline
from .ingestion import sha256_file, storage_source_file, upload_consolidation_artifact
from .models import ConsolidationStatus, IssueSeverity, QualityIssue, SourceRole
from .pipeline import run_local_pipeline
from .repository import MemoryConsolidationRepository, repository_for
from .resources import ConsolidationResourceError, ResourceMonitor, directory_size, isolated_run_directory


class ConsolidationWorker:
    def __init__(self, repository: Any, settings: Settings, output_root: Path | None = None) -> None:
        if settings.consolidation_worker_concurrency != 1:
            raise ValueError("Este worker admite concurrencia 1; escale con más procesos aislados.")
        self.repository = repository
        self.settings = settings
        self.output_root = output_root

    def _artifact_record(self, run: dict[str, Any], project: dict[str, Any], kind: str, path: Path) -> dict[str, Any]:
        if self.output_root:
            storage_path = str(path)
        else:
            storage_path = f"{run['user_id']}/.consolidation/{project['id']}/{run['id']}/{path.name}"
            upload_consolidation_artifact(path, storage_path, str(run["user_id"]), self.settings)
        return {
            "run_id": str(run["id"]),
            "user_id": str(run["user_id"]),
            "kind": kind,
            "storage_path": storage_path,
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }

    def run_once(self) -> bool:
        run = self.repository.claim_next()
        if not run:
            return False
        run_id = str(run["id"])
        monitor = ResourceMonitor(self.settings)
        try:
            project = self.repository.get_project(str(run["project_id"]), str(run["user_id"]))
            if not project:
                raise ValueError("project_not_found")
            with isolated_run_directory(self.settings, run_id=run_id) as workspace:
                max_temp_bytes = 0
                with ExitStack() as stack:
                    local_sources: dict[SourceRole, Path] = {}
                    with monitor.stage("download_sources") as stage:
                        for source in project.get("sources", []):
                            role = SourceRole(source["role"])
                            if source.get("local_path") and isinstance(self.repository, MemoryConsolidationRepository):
                                local_sources[role] = Path(source["local_path"])
                                continue
                            storage_path = source.get("profile", {}).get("storage_path")
                            if not storage_path:
                                raise ValueError(f"source_without_storage:{role.value}")
                            path, _digest = stack.enter_context(storage_source_file(
                                storage_path,
                                str(run["user_id"]),
                                self.settings,
                                directory=workspace,
                            ))
                            local_sources[role] = path
                        downloaded = directory_size(workspace)
                        max_temp_bytes = max(max_temp_bytes, downloaded)
                        stage.add(temporary_bytes=downloaded, source_bytes=sum(path.stat().st_size for path in local_sources.values()), chunks=len(local_sources))

                    output = run_local_pipeline(
                        local_sources,
                        mapping_override=project.get("config", {}).get("mapping_manifest"),
                        target_columns=project.get("config", {}).get("target_columns"),
                        cohort=int(project.get("config", {}).get("cohort", 2026)),
                        cohort_id_strategy=project.get("config", {}).get("cohort_id_strategy", "cohort_and_id"),
                        settings=self.settings,
                        monitor=monitor,
                    ) if project.get("config", {}).get("template") != "general" else run_general_pipeline(
                        local_sources,
                        source_configs={
                            SourceRole(source["role"]): {
                                **source.get("profile", {}).get("configuration", {}),
                                "selected_sheet": source.get("selected_sheet") or source.get("profile", {}).get("configuration", {}).get("selected_sheet"),
                            }
                            for source in project.get("sources", [])
                        },
                        settings=self.settings,
                        monitor=monitor,
                        period_label=project.get("config", {}).get("period_label"),
                    )
                    previous = self.repository.find_completed(str(run["user_id"]), output.manifest.input_hash, output.manifest.config_hash)
                    if previous and str(previous["id"]) != run_id:
                        monitor.stop()
                        self.repository.complete_run(
                            run_id,
                            status=previous["status"],
                            input_hash=output.manifest.input_hash,
                            report=previous.get("report", {}),
                            artifacts=[],
                            reused_run_id=str(previous["id"]),
                        )
                        return True

                    if self.output_root:
                        artifact_dir = self.output_root / run_id
                    else:
                        artifact_dir = workspace / "artifacts"
                    artifact_dir.mkdir(parents=True, exist_ok=False)
                    extra_paths: dict[str, Path] = {}
                    generic = project.get("config", {}).get("template") == "general"
                    historical = local_sources.get(SourceRole.HISTORICAL if generic else SourceRole.HISTORICA)
                    if historical and project.get("config", {}).get("include_historical_output"):
                        selected_historical_sheet = next(
                            (
                                source.get("selected_sheet")
                                or source.get("profile", {}).get("configuration", {}).get("selected_sheet")
                                for source in project.get("sources", [])
                                if source["role"] == (SourceRole.HISTORICAL.value if generic else SourceRole.HISTORICA.value)
                            ),
                            None,
                        )
                        if generic:
                            historical_path, warning = write_historical_generic(
                                historical, output.annual,
                                artifact_dir / "BASE_HISTORICA_CONSOLIDADA.xlsx",
                                sheet_name=selected_historical_sheet,
                            )
                        else:
                            historical_path, warning = write_historical_consolidated(
                                historical, output.annual,
                                artifact_dir / "DEMRE_2020_2026_CONSOLIDADA.xlsx",
                                sheet_name=selected_historical_sheet or "BASE DE DATOS",
                                cohort=int(project.get("config", {}).get("cohort", 2026)),
                            )
                        if historical_path:
                            extra_paths["historical"] = historical_path
                        elif warning:
                            output.manifest.status = ConsolidationStatus.PARTIAL
                            output.audit_tables.setdefault("historical", []).append({"warning": warning})
                            output.manifest.issues.append(QualityIssue(
                                code=warning,
                                severity=IssueSeverity.WARNING,
                                message="La consolidación histórica no se generó; la base anual permanece disponible.",
                            ))
                    paths = write_pipeline_artifacts(
                        output,
                        artifact_dir,
                        monitor=monitor,
                        chunk_size=self.settings.consolidation_chunk_size,
                    )
                    paths.update(extra_paths)
                    max_temp_bytes = max(max_temp_bytes, directory_size(workspace))

                    artifacts: list[dict[str, Any]] = []
                    # Sube primero los artefactos grandes; manifest se finaliza tras liberar memoria.
                    for kind, path in paths.items():
                        if kind == "manifest":
                            continue
                        artifacts.append(self._artifact_record(run, project, kind, path))

                    with monitor.stage("cleanup_temporaries") as stage:
                        output.annual = output.annual.head(0)
                        local_sources.clear()
                        stack.close()
                        gc.collect()
                        if not self.output_root:
                            for kind, path in paths.items():
                                if kind != "manifest":
                                    path.unlink(missing_ok=True)
                        stage.add(temporary_bytes=directory_size(workspace))

                    artifact_metrics = output.manifest.resource_metrics.get("artifacts", {})
                    metrics = monitor.stop()
                    metrics["artifacts"] = artifact_metrics
                    metrics["temporary_max_bytes"] = max_temp_bytes
                    metrics["temporary_final_bytes"] = directory_size(workspace)
                    output.manifest.resource_metrics = metrics
                    output.manifest.memory_bytes_estimate = metrics["peak_rss_bytes"]
                    manifest_path = paths["manifest"]
                    manifest_path.write_text(output.manifest.model_dump_json(indent=2), encoding="utf-8")
                    artifacts.append(self._artifact_record(run, project, "manifest", manifest_path))
                    report = output.manifest.model_dump(mode="json")
                    self.repository.complete_run(
                        run_id,
                        status=output.manifest.status.value,
                        input_hash=output.manifest.input_hash,
                        report=report,
                        artifacts=artifacts,
                    )
            return True
        except ConsolidationResourceError as exc:
            metrics = monitor.stop()
            metrics.update(exc.metrics)
            self.repository.fail_run(run_id, exc.code, str(exc), report={"resource_metrics": metrics})
            return True
        except Exception as exc:
            metrics = monitor.stop()
            self.repository.fail_run(
                run_id,
                "processing_failed",
                f"{exc.__class__.__name__}: {str(exc)[:300]}",
                report={"resource_metrics": metrics},
            )
            return True

    def run_forever(self) -> None:
        self.repository.recover_interrupted(self.settings.consolidation_run_stale_seconds)
        while True:
            if not self.run_once():
                time.sleep(max(0.2, self.settings.consolidation_worker_poll_seconds))


def main() -> None:
    settings = get_settings()
    ConsolidationWorker(repository_for(settings), settings).run_forever()


if __name__ == "__main__":
    main()
