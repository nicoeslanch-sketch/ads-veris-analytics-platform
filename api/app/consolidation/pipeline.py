"""Pipeline determinístico para construir la base anual sin alterar fuentes."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd

from ..config import Settings, get_settings
from ..version import ENGINE_VERSION
from .codebooks import parse_codebook, parse_inline_codebook, recode_series
from .ingestion import csv_columns, read_csv_selected, read_csv_unique_for_ids, read_xlsx_selected, sha256_file, workbook_headers
from .models import ConsolidationManifest, ConsolidationStatus, IssueSeverity, QualityIssue, SourceRole
from .quality import null_reason_summary, validate_annual_contract
from .resources import ResourceMonitor
from .resolvers.offer import resolve_offer_frame
from .resolvers.preferences_d import resolve_preferences_csv, selected_status_codes
from .target_schema import coerce_target_types, resolve_target_columns


@dataclass
class PipelineOutput:
    annual: pd.DataFrame
    manifest: ConsolidationManifest
    audit_tables: dict[str, list[dict[str, Any]]]


def load_mapping_manifest(path: Path | None = None) -> dict[str, Any]:
    manifest_path = path or Path(str(files("app.consolidation").joinpath("manifests/demre_2026.json")))
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_columns(mapping: dict[str, Any], role: str) -> list[str]:
    columns = {"ID_aux"}
    for rule in mapping["direct_mappings"]:
        if rule["source"] == role:
            columns.add(rule["column"])
    for rule in mapping.get("recodings", []):
        if rule["source"] == role:
            columns.add(rule["variable"])
    return sorted(columns)


def _nonempty(values: pd.Series) -> pd.Series:
    return values.notna() & values.astype("string").fillna("").str.strip().ne("")


def _source_priority(mapping: dict[str, Any], target: str, source: str) -> int:
    declared = list(mapping.get("precedence", {}).get(target, []))
    if not declared:
        declared = [
            rule["source"]
            for rule in [*mapping.get("direct_mappings", []), *mapping.get("recodings", [])]
            if rule["target"] == target
        ]
    ordered = list(dict.fromkeys(declared))
    return ordered.index(source) if source in ordered else len(ordered)


def _assign_by_authority(
    annual: pd.DataFrame,
    target: str,
    values: pd.Series,
    *,
    priority: int,
    priorities: dict[str, np.ndarray],
) -> None:
    current = annual[target]
    scores = priorities.setdefault(
        target,
        np.where(_nonempty(current).to_numpy(), -1, np.iinfo(np.int16).max).astype(np.int16),
    )
    candidate = _nonempty(values)
    mask = candidate.to_numpy() & ((~_nonempty(current).to_numpy()) | (priority < scores))
    if mask.any():
        annual.loc[mask, target] = values.loc[mask].astype("string")
        scores[mask] = priority


def _apply_declared_derivations(
    annual: pd.DataFrame,
    rules: list[dict[str, Any]],
    direct_targets: set[str],
) -> None:
    """Aplica operaciones pequeñas y auditables; no evalúa código del manifiesto."""
    for rule in rules:
        source, target = rule.get("source"), rule.get("target")
        if source not in annual.columns or target not in annual.columns:
            continue
        values = annual[source].astype("string")
        present = values.notna() & values.fillna("").str.strip().ne("")
        operation = rule.get("operation")
        result = pd.Series(pd.NA, index=annual.index, dtype="string")
        if operation == "equals":
            result.loc[present] = np.where(values.loc[present].eq(str(rule.get("value"))), "1", "0")
        elif operation == "not_equals":
            result.loc[present] = np.where(values.loc[present].ne(str(rule.get("value"))), "1", "0")
        elif operation == "less_than_or_equal":
            numeric = pd.to_numeric(values, errors="coerce")
            valid = numeric.notna()
            result.loc[valid] = np.where(numeric.loc[valid].le(float(rule.get("value"))), "1", "0")
        elif operation == "prefix_equals":
            result.loc[present] = np.where(values.loc[present].str.startswith(str(rule.get("value"))), "1", "0")
        elif operation == "in_values":
            accepted = {str(value) for value in rule.get("values", [])}
            result.loc[present] = np.where(values.loc[present].isin(accepted), "1", "0")
        else:
            raise ValueError(f"Operación de derivación no soportada: {operation}")
        annual[target] = result
        direct_targets.add(target)


def _run_local_pipeline_impl(
    sources: dict[SourceRole, Path],
    *,
    mapping_path: Path | None = None,
    mapping_override: dict[str, Any] | None = None,
    target_columns: list[str] | tuple[str, ...] | None = None,
    cohort: int = 2026,
    cohort_id_strategy: str = "cohort_and_id",
    settings: Settings,
    monitor: ResourceMonitor,
) -> PipelineOutput:
    """Entrada local solo para worker/tests; la API usa paths temporales de Storage."""
    started = time.perf_counter()
    cfg = settings
    resources = monitor
    mapping = load_mapping_manifest(mapping_path)
    if mapping_override:
        mapping = {**mapping, **mapping_override}
    target = resolve_target_columns(target_columns)
    if SourceRole.MATRICULA not in sources:
        raise ValueError("Matrícula es obligatoria.")
    with resources.stage("download_sources") as stage:
        source_hashes = {role.value: sha256_file(path) for role, path in sources.items()}
        stage.add(source_bytes=sum(path.stat().st_size for path in sources.values()), chunks=len(sources))
    input_hash = stable_hash(source_hashes)
    config_hash = stable_hash({"mapping": mapping, "target": target, "cohort": cohort})
    issues: list[QualityIssue] = []
    audit: dict[str, list[dict[str, Any]]] = {"relations": [], "recoding": [], "null_reasons": [], "assumptions": []}
    recoded_targets: set[str] = set()

    matricula_columns = _source_columns(mapping, "matricula")
    matricula_input_column_count = len(csv_columns(sources[SourceRole.MATRICULA]))
    matricula_metrics: dict[str, int] = {}
    with resources.stage("read_matricula") as stage:
        matricula = read_csv_selected(
            sources[SourceRole.MATRICULA],
            matricula_columns,
            chunk_rows=cfg.consolidation_chunk_size,
            checkpoint=lambda: resources.checkpoint("read_matricula"),
            metrics=matricula_metrics,
        )
        stage.add(rows_read=matricula_metrics.get("rows_read", 0), rows_generated=len(matricula), chunks=matricula_metrics.get("chunks", 0))
    matricula["ID_aux"] = matricula["ID_aux"].astype("string").str.strip()
    if matricula["ID_aux"].eq("").any() or matricula["ID_aux"].duplicated().any():
        raise ValueError("Matrícula contiene ID_aux vacío o repetido.")
    with resources.stage("mapping") as stage:
        annual = pd.DataFrame(pd.NA, index=range(len(matricula)), columns=list(target), dtype="string")
        direct_targets: set[str] = set()
        for rule in mapping["direct_mappings"]:
            if rule["source"] != "matricula" or rule["target"] not in annual.columns:
                continue
            if rule["column"] in matricula.columns:
                annual[rule["target"]] = matricula[rule["column"]].astype("string")
                direct_targets.add(rule["target"])
        annual["cohorte"] = str(cohort)
        direct_targets.add("cohorte")
        stage.add(rows_generated=len(annual))

    annual_ids = annual["id_aux"].astype("string").str.strip()
    authority_ids = frozenset(annual_ids.tolist())
    priorities: dict[str, np.ndarray] = {}
    codebook_paths = {
        SourceRole.CODEBOOK_MATRICULA: sources.get(SourceRole.CODEBOOK_MATRICULA),
        SourceRole.CODEBOOK_B: sources.get(SourceRole.CODEBOOK_B),
        SourceRole.CODEBOOK_C: sources.get(SourceRole.CODEBOOK_C),
    }

    # El Libro Matrícula usa secciones verticales (variable + líneas "1. ...").
    # VIA alimenta ``via2``; TIPO_MATRICULA se recodifica y audita, pero no se
    # fuerza dentro de una columna histórica con significado diferente.
    for rule in mapping.get("recodings", []):
        if rule["source"] != "matricula" or rule["variable"] not in matricula.columns:
            continue
        book_path = codebook_paths.get(SourceRole(rule["book"]))
        if book_path is None:
            issues.append(QualityIssue(code=f"{rule['variable'].lower()}_book_missing", severity=IssueSeverity.WARNING, message=f"No se proporcionó el libro para traducir {rule['variable']}."))
            continue
        try:
            with resources.stage("parse_codebooks") as stage:
                book = parse_inline_codebook(book_path, sheet_name=rule["sheet"], variable=rule["variable"])
                stage.add(rows_generated=len(book.mapping), chunks=1)
        except ValueError as exc:
            issues.append(QualityIssue(code=f"{rule['variable'].lower()}_book_incompatible", severity=IssueSeverity.WARNING, message=str(exc)))
            continue
        recoded, counts = recode_series(matricula[rule["variable"]], book)
        target_name = rule.get("target")
        if target_name and target_name in annual.columns:
            _assign_by_authority(
                annual, target_name, recoded,
                priority=_source_priority(mapping, target_name, "matricula"),
                priorities=priorities,
            )
            direct_targets.add(target_name)
            recoded_targets.add(target_name)
            target_populated = int(_nonempty(annual[target_name]).sum())
        else:
            target_populated = 0
        audit["recoding"].append({
            "source": "matricula", "variable": rule["variable"],
            "target": target_name or "audit_only", **counts,
            "target_populated": target_populated,
            "book_conflicts": len(book.conflicts),
        })
    for role in (SourceRole.ARCHIVO_B, SourceRole.ARCHIVO_C):
        if role not in sources:
            if role is SourceRole.ARCHIVO_B:
                issues.append(QualityIssue(code="source_b_missing", severity=IssueSeverity.WARNING, message="Archivo B no fue proporcionado."))
            continue
        columns = _source_columns(mapping, role.value)
        available = csv_columns(sources[role])
        selected = [column for column in columns if column in available]
        dimension_metrics: dict[str, int]
        read_stage = f"read_{role.value}"
        with resources.stage(read_stage) as stage:
            frame, dimension_metrics = read_csv_unique_for_ids(
                sources[role], selected, authority_ids,
                chunk_rows=cfg.consolidation_chunk_size,
                checkpoint=lambda name=read_stage: resources.checkpoint(name),
            )
            stage.add(
                rows_read=dimension_metrics["rows_read"],
                rows_generated=dimension_metrics["rows_retained"],
                chunks=dimension_metrics["chunks"],
            )
        ambiguous = dimension_metrics["ambiguous_keys"]
        audit["relations"].append({
            "source": role.value,
            "rows_read": dimension_metrics["rows_read"],
            "rows_in_matricula_universe": dimension_metrics["rows_matched"],
            "rows_retained": dimension_metrics["rows_retained"],
            "chunks": dimension_metrics["chunks"],
            "cardinality": "one_to_one",
            "ambiguous_keys_excluded": ambiguous,
        })
        if ambiguous:
            issues.append(QualityIssue(code=f"{role.value}_duplicate_keys", severity=IssueSeverity.WARNING, message=f"{role.value} contiene claves duplicadas; no se enriquecieron.", count=ambiguous))
        frame_keys = frame["ID_aux"].astype("string").str.strip()
        with resources.stage("mapping") as stage:
            for rule in mapping["direct_mappings"]:
                if rule["source"] != role.value or rule["target"] not in annual.columns or rule["column"] not in frame.columns:
                    continue
                lookup = pd.Series(frame[rule["column"]].array, index=frame_keys.array)
                values = annual_ids.map(lookup).astype("string")
                _assign_by_authority(
                    annual, rule["target"], values,
                    priority=_source_priority(mapping, rule["target"], role.value),
                    priorities=priorities,
                )
                direct_targets.add(rule["target"])
                del lookup, values
            stage.add(rows_read=len(frame))
        for rule in mapping.get("recodings", []):
            if rule["source"] != role.value or rule["variable"] not in frame.columns or rule["target"] not in annual.columns:
                continue
            book_path = codebook_paths.get(SourceRole(rule["book"]))
            if book_path is None:
                continue
            try:
                with resources.stage("parse_codebooks") as stage:
                    book = (
                        parse_inline_codebook(book_path, sheet_name=rule["sheet"], variable=rule["variable"])
                        if rule.get("format") == "inline"
                        else parse_codebook(book_path, sheet_name=rule["sheet"], code_column=rule["code_column"], label_column=rule["label_column"])
                    )
                    stage.add(rows_generated=len(book.mapping), chunks=1)
            except ValueError as exc:
                issues.append(QualityIssue(code=f"{role.value}_{rule['variable'].lower()}_book_incompatible", severity=IssueSeverity.WARNING, message=str(exc)))
                continue
            recoded, counts = recode_series(frame[rule["variable"]], book)
            with resources.stage("mapping") as stage:
                lookup = pd.Series(recoded.array, index=frame_keys.array)
                values = annual_ids.map(lookup).astype("string")
                _assign_by_authority(
                    annual, rule["target"], values,
                    priority=_source_priority(mapping, rule["target"], role.value),
                    priorities=priorities,
                )
                stage.add(rows_read=len(frame))
            direct_targets.add(rule["target"])
            recoded_targets.add(rule["target"])
            target_populated = int(_nonempty(annual[rule["target"]]).sum())
            audit["recoding"].append({"source": role.value, "target": rule["target"], **counts, "target_populated": target_populated, "book_conflicts": len(book.conflicts)})
            del book, lookup, recoded, values
        del frame_keys, frame
        resources.checkpoint(f"release_{role.value}")
    del annual_ids, authority_ids

    with resources.stage("mapping") as stage:
        _apply_declared_derivations(annual, mapping.get("derivations", []), direct_targets)
        stage.add(rows_read=len(annual), rows_generated=len(annual))

    if SourceRole.ARCHIVO_D in sources and SourceRole.CODEBOOK_D in sources:
        d_config = mapping.get("resolvers", {}).get("archivo_d", {})
        with resources.stage("parse_codebooks") as stage:
            d_book = parse_codebook(
                sources[SourceRole.CODEBOOK_D],
                sheet_name=d_config.get("sheet", "Anexo -  Estado Preferencia"),
                code_column=d_config.get("code_column", "CÓD."),
                label_column=d_config.get("label_column", "DESCRIPCIÓN"),
            )
            stage.add(rows_generated=len(d_book.mapping), chunks=1)
        allowed = selected_status_codes(d_book)
        with resources.stage("reduce_archivo_d") as stage:
            _resolved_d, d_counts = resolve_preferences_csv(
                matricula,
                sources[SourceRole.ARCHIVO_D],
                allowed,
                chunk_rows=cfg.consolidation_chunk_size,
                checkpoint=lambda: resources.checkpoint("reduce_archivo_d"),
                include_records=False,
            )
            stage.add(rows_read=d_counts["d_rows_read"], rows_generated=d_counts["d_match_unique"], chunks=d_counts["d_chunks"])
        audit["relations"].append({"source": "archivo_d", **d_counts, "selected_status_codes": sorted(allowed)})
        if d_counts.get("d_ambiguous"):
            issues.append(QualityIssue(code="d_ambiguous", severity=IssueSeverity.WARNING, message="Preferencias D ambiguas se conservaron sin selección.", count=d_counts["d_ambiguous"]))
        del _resolved_d, d_book, allowed, d_counts

    offer_rules = [rule for rule in mapping["direct_mappings"] if rule["source"] == "oferta" and rule["target"] in annual.columns]
    if SourceRole.OFERTA in sources and offer_rules:
        offer_sheet = mapping.get("sheets", {}).get("oferta", "in")
        offer_headers = workbook_headers(sources[SourceRole.OFERTA])
        available_offer = set(offer_headers.get(offer_sheet, []))
        required_offer = {"Año", "Demre", "Vigencia"}
        if not required_offer <= available_offer:
            issues.append(QualityIssue(code="offer_schema_incompatible", severity=IssueSeverity.WARNING, message="Oferta no contiene Año, Demre y Vigencia; se omitió sin bloquear la base anual."))
            offer_rules = []
        else:
            omitted = [rule["column"] for rule in offer_rules if rule["column"] not in available_offer]
            offer_rules = [rule for rule in offer_rules if rule["column"] in available_offer]
            if omitted:
                issues.append(QualityIssue(code="offer_optional_columns_missing", severity=IssueSeverity.WARNING, message=f"Oferta no contiene {len(omitted)} columnas opcionales; quedarán vacías."))
        offer_columns = list(dict.fromkeys(["Año", "Demre", "Vigencia", *[rule["column"] for rule in offer_rules]]))
    if SourceRole.OFERTA in sources and offer_rules:
        offer_sheet = mapping.get("sheets", {}).get("oferta", "in")
        offer_metrics: dict[str, int] = {}
        with resources.stage("read_filter_oferta") as stage:
            offer = read_xlsx_selected(
                sources[SourceRole.OFERTA], sheet_name=offer_sheet, usecols=offer_columns,
                filter_equals=("Año", f"OFE_{cohort}"),
                chunk_rows=cfg.consolidation_chunk_size,
                checkpoint=lambda: resources.checkpoint("read_filter_oferta"),
                metrics=offer_metrics,
            )
            stage.add(rows_read=offer_metrics.get("rows_read", 0), rows_generated=len(offer), chunks=offer_metrics.get("chunks", 0))
        resolved_offer, offer_counts = resolve_offer_frame(offer, [rule["column"] for rule in offer_rules])
        offer_counts["offer_scoped_rows"] = len(offer)
        resolved_codes = set(resolved_offer["codigo_carrera"].astype("string")) if not resolved_offer.empty else set()
        offer_join_target = mapping.get("resolvers", {}).get("oferta", {}).get("join_target", "CódigoCarrera")
        if offer_join_target not in annual.columns:
            raise ValueError(f"La plantilla no contiene la clave de Oferta '{offer_join_target}'.")
        annual_codes = annual[offer_join_target].astype("string").fillna("").str.strip().str.replace(r"\.0$", "", regex=True)
        offer_counts["offer_matched_rows"] = int(annual_codes.isin(resolved_codes).sum())
        offer_counts["offer_unmatched_rows"] = int((~annual_codes.isin(resolved_codes)).sum())
        audit["relations"].append({"source": "oferta", **offer_counts})
        with resources.stage("mapping") as stage:
            annual_codes = annual[offer_join_target].astype("string").fillna("").str.strip().str.replace(r"\.0$", "", regex=True)
            for rule in offer_rules:
                lookup = pd.Series(resolved_offer[rule["column"]].array, index=resolved_offer["codigo_carrera"].astype("string").array) if not resolved_offer.empty else pd.Series(dtype="string")
                values = annual_codes.map(lookup).astype("string")
                _assign_by_authority(annual, rule["target"], values, priority=0, priorities=priorities)
                direct_targets.add(rule["target"])
                del lookup, values
            stage.add(rows_read=len(resolved_offer))
        if offer_counts.get("offer_ambiguous"):
            issues.append(QualityIssue(code="offer_ambiguous", severity=IssueSeverity.WARNING, message="Ofertas ambiguas quedaron sin enriquecer.", count=offer_counts["offer_ambiguous"]))
        del offer, resolved_offer, annual_codes, offer_counts

    expected_rows = len(matricula)
    del matricula, priorities
    with resources.stage("consolidation") as stage:
        annual = coerce_target_types(annual)
        audit["assumptions"] = [{"assumption": value} for value in mapping.get("assumptions", [])]
        stage.add(rows_generated=len(annual))

    with resources.stage("quality_control") as stage:
        issues.extend(validate_annual_contract(annual, expected_rows=expected_rows, target_columns=target, cohort=cohort))
        audit["null_reasons"] = null_reason_summary(annual, direct_targets, mapping.get("null_classification", {}))
        stage.add(rows_read=len(annual), rows_generated=len(audit["null_reasons"]))
    blocking = any(issue.severity is IssueSeverity.BLOCKING for issue in issues)
    if blocking:
        status = ConsolidationStatus.BLOCKED
    elif SourceRole.ARCHIVO_B not in sources:
        status = ConsolidationStatus.PARTIAL
    elif issues:
        status = ConsolidationStatus.VALID_WITH_WARNINGS
    else:
        status = ConsolidationStatus.CERTIFIED
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    manifest = ConsolidationManifest(
        run_id=uuid4(), engine_version=ENGINE_VERSION, mapping_version=mapping["version"],
        config_hash=config_hash, input_hash=input_hash, status=status,
        source_hashes=source_hashes,
        row_counts={
            "matricula": expected_rows, "annual": len(annual), "unique_ids": int(annual["id_aux"].nunique()),
            "original_columns": matricula_input_column_count, "final_columns": len(annual.columns),
            "added_columns": max(0, len(annual.columns) - matricula_input_column_count),
            "files_related": len(audit["relations"]),
            "unmatched_rows": sum(int(row.get("unmatched_primary_rows", row.get("offer_unmatched_rows", row.get("d_no_match", 0)))) for row in audit["relations"]),
            "ambiguous_keys": sum(int(row.get("ambiguous_keys_excluded", row.get("offer_ambiguous", row.get("d_ambiguous", 0)))) for row in audit["relations"]),
            "codes_translated": sum(int(row.get("mapped", 0)) for row in audit["recoding"]),
            "codes_unmapped": sum(int(row.get("unmapped", 0)) for row in audit["recoding"]),
        },
        recoding_coverage={
            target_name: float(annual[target_name].astype("string").fillna("").str.strip().ne("").mean())
            for target_name in sorted(recoded_targets)
        },
        issues=issues, timings_ms={"total": elapsed_ms},
        target_columns=list(target),
        relationship_summary=audit["relations"],
        null_reasons=audit["null_reasons"],
        assumptions=[item["assumption"] for item in audit["assumptions"]],
        cohort_id_method=None,
        preview=annual[
            [column for column in ("CódigoCarrera", "nombrecarrera", "nombreies", "modalidad") if column in annual.columns]
        ].head(min(100, cfg.consolidation_preview_rows)).fillna("").to_dict(orient="records"),
        memory_bytes_estimate=resources.snapshot()["peak_rss_bytes"],
        resource_metrics=resources.snapshot(),
    )
    return PipelineOutput(annual=annual, manifest=manifest, audit_tables=audit)


def run_local_pipeline(
    sources: dict[SourceRole, Path],
    *,
    mapping_path: Path | None = None,
    mapping_override: dict[str, Any] | None = None,
    target_columns: list[str] | tuple[str, ...] | None = None,
    cohort: int = 2026,
    cohort_id_strategy: str = "cohort_and_id",
    settings: Settings | None = None,
    monitor: ResourceMonitor | None = None,
) -> PipelineOutput:
    """Ejecuta el pipeline y cierra siempre el muestreador que haya creado."""
    cfg = settings or get_settings()
    resources = monitor or ResourceMonitor(cfg)
    owned_monitor = monitor is None
    try:
        output = _run_local_pipeline_impl(
            sources,
            mapping_path=mapping_path,
            mapping_override=mapping_override,
            target_columns=target_columns,
            cohort=cohort,
            cohort_id_strategy=cohort_id_strategy,
            settings=cfg,
            monitor=resources,
        )
    except BaseException:
        if owned_monitor:
            resources.stop()
        raise
    if owned_monitor:
        output.manifest.resource_metrics = resources.stop()
        output.manifest.memory_bytes_estimate = output.manifest.resource_metrics["peak_rss_bytes"]
    return output
