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

import pandas as pd

from ..version import ENGINE_VERSION
from .codebooks import parse_codebook, recode_values
from .historical import build_cohort_ids
from .ingestion import read_csv_selected, read_xlsx_selected, sha256_file
from .models import ConsolidationManifest, ConsolidationStatus, IssueSeverity, QualityIssue, SourceRole
from .quality import null_reason_summary, validate_annual_contract
from .resolvers.offer import resolve_offer_frame
from .resolvers.preferences_d import resolve_preferences_csv, selected_status_codes
from .target_schema import resolve_target_columns


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


def _unique_dimension(frame: pd.DataFrame, role: str) -> tuple[pd.DataFrame, int]:
    keys = frame["ID_aux"].astype("string").str.strip()
    counts = keys.value_counts(dropna=False)
    ambiguous_keys = set(counts[counts > 1].index.astype(str))
    clean = frame.loc[~keys.isin(ambiguous_keys)].copy()
    if clean["ID_aux"].astype("string").str.strip().duplicated().any():
        raise RuntimeError(f"La reducción conservadora de {role} no produjo claves únicas.")
    return clean, len(ambiguous_keys)


def _source_columns(mapping: dict[str, Any], role: str) -> list[str]:
    columns = {"ID_aux"}
    for rule in mapping["direct_mappings"]:
        if rule["source"] == role:
            columns.add(rule["column"])
    for rule in mapping.get("recodings", []):
        if rule["source"] == role:
            columns.add(rule["variable"])
    return sorted(columns)


def run_local_pipeline(
    sources: dict[SourceRole, Path],
    *,
    mapping_path: Path | None = None,
    target_columns: list[str] | tuple[str, ...] | None = None,
    cohort: int = 2026,
) -> PipelineOutput:
    """Entrada local solo para worker/tests; la API usa paths temporales de Storage."""
    started = time.perf_counter()
    mapping = load_mapping_manifest(mapping_path)
    target = resolve_target_columns(target_columns)
    if SourceRole.MATRICULA not in sources:
        raise ValueError("Matrícula es obligatoria.")
    source_hashes = {role.value: sha256_file(path) for role, path in sources.items()}
    input_hash = stable_hash(source_hashes)
    config_hash = stable_hash({"mapping": mapping, "target": target, "cohort": cohort})
    issues: list[QualityIssue] = []
    audit: dict[str, list[dict[str, Any]]] = {"relations": [], "recoding": [], "null_reasons": [], "assumptions": []}

    matricula_columns = _source_columns(mapping, "matricula")
    matricula = read_csv_selected(sources[SourceRole.MATRICULA], matricula_columns)
    matricula["ID_aux"] = matricula["ID_aux"].astype("string").str.strip()
    if matricula["ID_aux"].eq("").any() or matricula["ID_aux"].duplicated().any():
        raise ValueError("Matrícula contiene ID_aux vacío o repetido.")
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

    source_frames: dict[str, pd.DataFrame] = {}
    for role in (SourceRole.ARCHIVO_B, SourceRole.ARCHIVO_C):
        if role not in sources:
            if role is SourceRole.ARCHIVO_B:
                issues.append(QualityIssue(code="source_b_missing", severity=IssueSeverity.WARNING, message="Archivo B no fue proporcionado."))
            continue
        columns = _source_columns(mapping, role.value)
        available = pd.read_csv(sources[role], sep=";", nrows=0, encoding="utf-8-sig").columns.tolist()
        selected = [column for column in columns if column in available]
        frame = read_csv_selected(sources[role], selected)
        frame, ambiguous = _unique_dimension(frame, role.value)
        source_frames[role.value] = frame
        audit["relations"].append({"source": role.value, "cardinality": "one_to_one", "ambiguous_keys_excluded": ambiguous})
        if ambiguous:
            issues.append(QualityIssue(code=f"{role.value}_duplicate_keys", severity=IssueSeverity.WARNING, message=f"{role.value} contiene claves duplicadas; no se enriquecieron.", count=ambiguous))

    for target_name in annual.columns:
        candidates = [rule for rule in mapping["direct_mappings"] if rule["target"] == target_name and rule["source"] in source_frames]
        precedence = mapping.get("precedence", {}).get(target_name, [rule["source"] for rule in candidates])
        for source_name in precedence:
            rule = next((item for item in candidates if item["source"] == source_name), None)
            if not rule or rule["column"] not in source_frames[source_name].columns:
                continue
            dimension = source_frames[source_name][["ID_aux", rule["column"]]].rename(columns={rule["column"]: "__value"})
            values = annual[["id_aux"]].merge(dimension, left_on="id_aux", right_on="ID_aux", how="left", validate="one_to_one")["__value"]
            current = annual[target_name]
            annual[target_name] = current.where(current.notna() & current.astype("string").str.strip().ne(""), values)
            direct_targets.add(target_name)

    codebook_paths = {
        SourceRole.CODEBOOK_B: sources.get(SourceRole.CODEBOOK_B),
        SourceRole.CODEBOOK_C: sources.get(SourceRole.CODEBOOK_C),
    }
    for rule in mapping.get("recodings", []):
        source_name = rule["source"]
        source_frame = source_frames.get(source_name)
        book_role = SourceRole(rule["book"])
        book_path = codebook_paths.get(book_role)
        if source_frame is None or book_path is None or rule["variable"] not in source_frame.columns or rule["target"] not in annual.columns:
            continue
        book = parse_codebook(book_path, sheet_name=rule["sheet"], code_column=rule["code_column"], label_column=rule["label_column"])
        recoded, counts = recode_values(source_frame[rule["variable"]].tolist(), book)
        dimension = pd.DataFrame({"ID_aux": source_frame["ID_aux"], "__value": recoded})
        values = annual[["id_aux"]].merge(dimension, left_on="id_aux", right_on="ID_aux", how="left", validate="one_to_one")["__value"]
        current = annual[rule["target"]]
        annual[rule["target"]] = current.where(current.notna() & current.astype("string").str.strip().ne(""), values)
        direct_targets.add(rule["target"])
        audit["recoding"].append({"target": rule["target"], **counts, "book_conflicts": len(book.conflicts)})

    if SourceRole.ARCHIVO_D in sources and SourceRole.CODEBOOK_D in sources:
        d_book = parse_codebook(sources[SourceRole.CODEBOOK_D], sheet_name="Anexo -  Estado Preferencia", code_column="CÓD.", label_column="DESCRIPCIÓN")
        allowed = selected_status_codes(d_book)
        _resolved_d, d_counts = resolve_preferences_csv(matricula, sources[SourceRole.ARCHIVO_D], allowed)
        audit["relations"].append({"source": "archivo_d", **d_counts, "selected_status_codes": sorted(allowed)})
        if d_counts.get("d_ambiguous"):
            issues.append(QualityIssue(code="d_ambiguous", severity=IssueSeverity.WARNING, message="Preferencias D ambiguas se conservaron sin selección.", count=d_counts["d_ambiguous"]))

    offer_rules = [rule for rule in mapping["direct_mappings"] if rule["source"] == "oferta" and rule["target"] in annual.columns]
    if SourceRole.OFERTA in sources and offer_rules:
        offer_columns = list(dict.fromkeys(["Año", "Demre", "Vigencia", *[rule["column"] for rule in offer_rules]]))
        offer = read_xlsx_selected(sources[SourceRole.OFERTA], sheet_name="in", usecols=offer_columns, filter_equals=("Año", "OFE_2026"))
        resolved_offer, offer_counts = resolve_offer_frame(offer, [rule["column"] for rule in offer_rules])
        audit["relations"].append({"source": "oferta", **offer_counts})
        for rule in offer_rules:
            dimension = resolved_offer[["codigo_carrera", rule["column"]]].rename(columns={rule["column"]: "__value"}) if not resolved_offer.empty else pd.DataFrame(columns=["codigo_carrera", "__value"])
            values = annual[["codigo_carrera"]].merge(dimension, on="codigo_carrera", how="left", validate="many_to_one")["__value"]
            current = annual[rule["target"]]
            annual[rule["target"]] = current.where(current.notna() & current.astype("string").str.strip().ne(""), values)
            direct_targets.add(rule["target"])
        if offer_counts.get("offer_ambiguous"):
            issues.append(QualityIssue(code="offer_ambiguous", severity=IssueSeverity.WARNING, message="Ofertas ambiguas quedaron sin enriquecer.", count=offer_counts["offer_ambiguous"]))

    cohort_ids, cohort_method = build_cohort_ids(annual["id_aux"], cohort)
    annual["cohorte_id"] = cohort_ids
    annual["cohorte_id_repetido"] = "0"
    direct_targets.update({"cohorte_id", "cohorte_id_repetido"})
    issues.append(QualityIssue(code="cohort_id_generated_fallback", severity=IssueSeverity.WARNING, message="cohorte_id fue generado como cohorte:id_aux y requiere validación histórica."))
    audit["assumptions"] = [{"assumption": value} for value in mapping.get("assumptions", [])] + [{"assumption": f"cohorte_id_method={cohort_method}"}]

    issues.extend(validate_annual_contract(annual, expected_rows=len(matricula), target_columns=target, cohort=cohort))
    audit["null_reasons"] = null_reason_summary(annual, direct_targets)
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
        row_counts={"matricula": len(matricula), "annual": len(annual), "unique_ids": int(annual["id_aux"].nunique())},
        recoding_coverage={item["target"]: item["mapped"] / max(1, len(annual)) for item in audit["recoding"]},
        issues=issues, timings_ms={"total": elapsed_ms},
    )
    return PipelineOutput(annual=annual, manifest=manifest, audit_tables=audit)
