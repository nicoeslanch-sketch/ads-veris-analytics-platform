"""Pipeline general: une tablas por claves declaradas sin reglas sectoriales."""

from __future__ import annotations

import re
import time
import unicodedata
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from ..config import Settings
from ..version import ENGINE_VERSION
from .ingestion import read_tabular_source, sha256_file
from .models import ConsolidationManifest, ConsolidationStatus, IssueSeverity, QualityIssue, SourceRole
from .pipeline import PipelineOutput, stable_hash
from .resources import ResourceMonitor


SUPPLEMENT_ROLES = (
    SourceRole.SUPPLEMENT_1,
    SourceRole.SUPPLEMENT_2,
    SourceRole.SUPPLEMENT_3,
    SourceRole.SUPPLEMENT_4,
)
EQUIVALENCE_ROLES = (SourceRole.EQUIVALENCE_1, SourceRole.EQUIVALENCE_2)


def _clean_key(values: pd.Series) -> pd.Series:
    return values.astype("string").fillna("").str.strip()


def _slug(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()[:60] or "fuente"


def _unique_output_name(existing: set[str], column: str, prefix: str) -> str:
    candidate = f"{prefix}_{column}" if prefix else column
    if candidate not in existing:
        return candidate
    base = f"{prefix or 'fuente'}_{column}"
    candidate = base
    suffix = 2
    while candidate in existing:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def _safe_preview_columns(columns: list[str]) -> list[str]:
    sensitive = ("rut", "email", "correo", "telefono", "direcc", "nombre", "apellido", "id")
    safe = [column for column in columns if not any(marker in _slug(column) for marker in sensitive)]
    return (safe or columns)[:8]


def run_general_pipeline(
    sources: dict[SourceRole, Path],
    *,
    source_configs: dict[SourceRole, dict[str, Any]],
    settings: Settings,
    monitor: ResourceMonitor,
    period_label: str | None = None,
) -> PipelineOutput:
    """Conserva cada fila del archivo principal y enriquece solo con claves únicas."""
    started = time.perf_counter()
    if SourceRole.PRIMARY not in sources:
        raise ValueError("Selecciona un archivo principal antes de ejecutar.")
    primary_config = source_configs.get(SourceRole.PRIMARY, {})
    primary_key = str(primary_config.get("primary_key") or "").strip()
    if not primary_key:
        raise ValueError("Selecciona la columna clave del archivo principal.")

    with monitor.stage("download_sources") as stage:
        source_hashes = {role.value: sha256_file(path) for role, path in sources.items()}
        stage.add(source_bytes=sum(path.stat().st_size for path in sources.values()), chunks=len(sources))
    input_hash = stable_hash(source_hashes)
    config_hash = stable_hash({
        "template": "general-v1",
        "period_label": period_label,
        "sources": {role.value: config for role, config in sorted(source_configs.items(), key=lambda item: item[0].value)},
    })
    issues: list[QualityIssue] = []
    audit: dict[str, list[dict[str, Any]]] = {
        "relations": [], "recoding": [], "null_reasons": [], "assumptions": [],
    }

    primary_metrics: dict[str, int] = {}
    with monitor.stage("read_primary") as stage:
        annual = read_tabular_source(
            sources[SourceRole.PRIMARY],
            sheet_name=primary_config.get("selected_sheet"),
            chunk_rows=settings.consolidation_chunk_size,
            checkpoint=lambda: monitor.checkpoint("read_primary"),
            metrics=primary_metrics,
        )
        stage.add(rows_read=primary_metrics.get("rows_read", len(annual)), rows_generated=len(annual), chunks=primary_metrics.get("chunks", 0))
    if primary_key not in annual.columns:
        raise ValueError(f"La clave principal '{primary_key}' no existe en el archivo principal.")
    expected_rows = len(annual)
    primary_keys = _clean_key(annual[primary_key])
    empty_primary = int(primary_keys.eq("").sum())
    if empty_primary:
        issues.append(QualityIssue(
            code="primary_key_empty", severity=IssueSeverity.WARNING,
            message="Hay filas sin clave en el archivo principal; se conservaron sin enriquecimiento.", count=empty_primary,
            column=primary_key,
        ))
    audit["assumptions"].append({"assumption": "El archivo principal define y conserva todas las filas."})
    if period_label:
        audit["assumptions"].append({"assumption": f"period_label={period_label}"})

    for role in SUPPLEMENT_ROLES:
        if role not in sources:
            continue
        config = source_configs.get(role, {})
        source_key = str(config.get("source_key") or "").strip()
        join_to = str(config.get("primary_key") or primary_key).strip()
        label = str(config.get("label") or role.value).strip()
        if join_to not in annual.columns:
            raise ValueError(f"La clave '{join_to}' para {label} no existe en el resultado actual.")
        if not source_key:
            raise ValueError(f"Selecciona la columna clave de {label}.")
        metrics: dict[str, int] = {}
        stage_name = f"read_{role.value}"
        with monitor.stage(stage_name) as stage:
            frame = read_tabular_source(
                sources[role], sheet_name=config.get("selected_sheet"),
                chunk_rows=settings.consolidation_chunk_size,
                checkpoint=lambda name=stage_name: monitor.checkpoint(name), metrics=metrics,
            )
            stage.add(rows_read=metrics.get("rows_read", len(frame)), rows_generated=len(frame), chunks=metrics.get("chunks", 0))
        if source_key not in frame.columns:
            raise ValueError(f"La clave '{source_key}' no existe en {label}.")
        keys = _clean_key(frame[source_key])
        nonempty = keys.ne("")
        duplicated = keys[nonempty].duplicated(keep=False)
        ambiguous_keys = set(keys[nonempty][duplicated].tolist())
        safe = frame.loc[nonempty & ~keys.isin(ambiguous_keys)].copy()
        safe_keys = _clean_key(safe[source_key])
        requested = [str(column) for column in config.get("include_columns", []) if str(column) in safe.columns]
        columns = requested or [str(column) for column in safe.columns if str(column) != source_key]
        raw_prefix = str(config.get("prefix") or "").strip()
        prefix = _slug(raw_prefix) if raw_prefix else ""
        existing = set(str(column) for column in annual.columns)
        output_names: dict[str, str] = {}
        with monitor.stage("mapping") as stage:
            for column in columns:
                output = _unique_output_name(existing, column, prefix)
                existing.add(output)
                output_names[column] = output
                lookup = pd.Series(safe[column].array, index=safe_keys.array)
                annual[output] = _clean_key(annual[join_to]).map(lookup).astype("string")
            stage.add(rows_read=len(frame), rows_generated=len(annual))
        matched = int(_clean_key(annual[join_to]).isin(set(safe_keys.tolist())).sum())
        unmatched = len(annual) - matched
        audit["relations"].append({
            "source": role.value, "label": label, "left_key": join_to, "right_key": source_key,
            "rows_read": len(frame), "matched_primary_rows": matched, "unmatched_primary_rows": unmatched,
            "ambiguous_keys_excluded": len(ambiguous_keys), "columns_added": len(output_names),
            "cardinality": "many_to_one_safe",
        })
        if ambiguous_keys:
            issues.append(QualityIssue(
                code=f"{role.value}_duplicate_keys", severity=IssueSeverity.WARNING,
                message=f"{label} tiene claves repetidas; esas coincidencias no se usaron para evitar multiplicar filas.",
                count=len(ambiguous_keys), column=source_key,
            ))
        if unmatched:
            issues.append(QualityIssue(
                code=f"{role.value}_unmatched", severity=IssueSeverity.WARNING,
                message=f"Algunas filas del archivo principal no encontraron coincidencia en {label}.",
                count=unmatched, column=join_to,
            ))

    for role in EQUIVALENCE_ROLES:
        if role not in sources:
            continue
        config = source_configs.get(role, {})
        target_column = str(config.get("target_column") or "").strip()
        code_column = str(config.get("source_key") or "").strip()
        value_column = str(config.get("value_column") or "").strip()
        label = str(config.get("label") or role.value).strip()
        if target_column not in annual.columns:
            raise ValueError(f"La columna a recodificar '{target_column}' no existe en el resultado.")
        if not code_column or not value_column:
            raise ValueError(f"Completa las columnas de código y valor para {label}.")
        frame = read_tabular_source(
            sources[role], sheet_name=config.get("selected_sheet"),
            chunk_rows=settings.consolidation_chunk_size,
            checkpoint=lambda name=role.value: monitor.checkpoint(name),
        )
        missing = [column for column in (code_column, value_column) if column not in frame.columns]
        if missing:
            raise ValueError(f"Faltan columnas en {label}: {', '.join(missing)}")
        codes = _clean_key(frame[code_column])
        nonempty = codes.ne("")
        ambiguous = set(codes[nonempty][codes[nonempty].duplicated(keep=False)].tolist())
        safe = frame.loc[nonempty & ~codes.isin(ambiguous)]
        lookup = pd.Series(safe[value_column].astype("string").array, index=_clean_key(safe[code_column]).array)
        output_base = str(config.get("output_column") or f"{target_column}_recodificado").strip()
        output_column = _unique_output_name(set(str(column) for column in annual.columns), output_base, "")
        mapped = _clean_key(annual[target_column]).map(lookup).astype("string")
        annual[output_column] = mapped
        populated = _clean_key(annual[target_column]).ne("")
        mapped_mask = _clean_key(mapped).ne("")
        unknown = int((populated & ~mapped_mask).sum())
        audit["recoding"].append({
            "source": role.value, "label": label, "target": target_column,
            "output": output_column, "mapped": int(mapped_mask.sum()), "unmapped": unknown,
            "ambiguous_codes_excluded": len(ambiguous),
        })
        if ambiguous:
            issues.append(QualityIssue(
                code=f"{role.value}_ambiguous_codes", severity=IssueSeverity.WARNING,
                message=f"{label} contiene códigos con más de un significado; no se recodificaron.",
                count=len(ambiguous), column=code_column,
            ))
        if unknown:
            issues.append(QualityIssue(
                code=f"{role.value}_unmapped", severity=IssueSeverity.WARNING,
                message=f"Hay valores sin equivalencia en {label}; el dato original se conservó.",
                count=unknown, column=target_column,
            ))

    if len(annual) != expected_rows:
        issues.append(QualityIssue(
            code="row_count_changed", severity=IssueSeverity.BLOCKING,
            message="El proceso cambió la cantidad de filas del archivo principal.",
            count=abs(len(annual) - expected_rows),
        ))
    blocking = any(issue.severity is IssueSeverity.BLOCKING for issue in issues)
    status = ConsolidationStatus.BLOCKED if blocking else ConsolidationStatus.VALID_WITH_WARNINGS if issues else ConsolidationStatus.CERTIFIED
    preview_columns = _safe_preview_columns([str(column) for column in annual.columns])
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    manifest = ConsolidationManifest(
        run_id=uuid4(), engine_version=ENGINE_VERSION, mapping_version="general-v1",
        config_hash=config_hash, input_hash=input_hash, status=status,
        source_hashes=source_hashes,
        row_counts={
            "primary": expected_rows, "annual": len(annual),
            "unique_keys": int(primary_keys[primary_keys.ne("")].nunique()),
        },
        issues=issues, timings_ms={"total": elapsed_ms}, target_columns=[str(column) for column in annual.columns],
        relationship_summary=audit["relations"], assumptions=[item["assumption"] for item in audit["assumptions"]],
        preview=annual[preview_columns].head(min(100, settings.consolidation_preview_rows)).fillna("").to_dict(orient="records"),
        memory_bytes_estimate=monitor.snapshot()["peak_rss_bytes"], resource_metrics=monitor.snapshot(),
    )
    return PipelineOutput(annual=annual, manifest=manifest, audit_tables=audit)
