"""Contratos del dominio de consolidación; no reutiliza cleaning_jobs."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class SourceRole(StrEnum):
    # Roles genéricos. Los nombres internos son estables; el usuario puede
    # asignar una etiqueta clara a cada fuente dentro del proyecto.
    PRIMARY = "primary"
    SUPPLEMENT_1 = "supplement_1"
    SUPPLEMENT_2 = "supplement_2"
    SUPPLEMENT_3 = "supplement_3"
    SUPPLEMENT_4 = "supplement_4"
    EQUIVALENCE_1 = "equivalence_1"
    EQUIVALENCE_2 = "equivalence_2"
    HISTORICAL = "historical"

    # Plantilla especializada DEMRE 2026. Se conserva para no romper los
    # proyectos creados antes de que existiera el modo general.
    MATRICULA = "matricula"
    ARCHIVO_B = "archivo_b"
    ARCHIVO_C = "archivo_c"
    ARCHIVO_D = "archivo_d"
    OFERTA = "oferta"
    HISTORICA = "historica"
    CODEBOOK_MATRICULA = "codebook_matricula"
    CODEBOOK_B = "codebook_b"
    CODEBOOK_C = "codebook_c"
    CODEBOOK_D = "codebook_d"


class ConsolidationStatus(StrEnum):
    DRAFT = "draft"
    VALIDATING = "validating"
    VALID_WITH_WARNINGS = "valid_with_warnings"
    BLOCKED = "blocked"
    PREVIEW_READY = "preview_ready"
    RUNNING = "running"
    PARTIAL = "partial"
    CERTIFIED = "certified"
    FAILED = "failed"


class IssueSeverity(StrEnum):
    BLOCKING = "blocking"
    WARNING = "warning"
    INFO = "info"


class SourceAssignment(BaseModel):
    dataset_id: UUID
    role: SourceRole
    selected_sheet: str | None = None
    required: bool = True
    label: str | None = Field(default=None, max_length=80)
    primary_key: str | None = Field(default=None, max_length=200)
    source_key: str | None = Field(default=None, max_length=200)
    target_column: str | None = Field(default=None, max_length=200)
    value_column: str | None = Field(default=None, max_length=200)
    output_column: str | None = Field(default=None, max_length=200)
    prefix: str | None = Field(default=None, max_length=80)
    include_columns: list[str] = Field(default_factory=list, max_length=500)


class ConsolidationProjectConfig(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    template: str = "general"
    cohort: int = Field(default=2026, ge=2000, le=2100)
    period_label: str | None = Field(default=None, max_length=80)
    sources: list[SourceAssignment] = Field(default_factory=list)
    include_historical_output: bool = False
    mapping_version: str = "demre-2026-historico-real-v2"
    target_columns: list[str] | None = None
    aliases: dict[str, str] = Field(default_factory=dict)
    precedence: dict[str, list[SourceRole]] = Field(default_factory=dict)
    cohort_id_strategy: str = "cohort_and_id"

    @model_validator(mode="after")
    def unique_roles(self) -> "ConsolidationProjectConfig":
        roles = [source.role for source in self.sources]
        if len(roles) != len(set(roles)):
            raise ValueError("Cada rol de fuente puede asignarse una sola vez.")
        if self.target_columns and len(self.target_columns) != len(set(self.target_columns)):
            raise ValueError("La plantilla objetivo contiene columnas duplicadas.")
        return self


class SourceProfile(BaseModel):
    role: SourceRole | None = None
    filename: str
    sheet: str | None = None
    columns: list[str]
    rows: int | None = None
    unique_ids: int | None = None
    null_ids: int | None = None
    sha256: str | None = None
    detected_by: str = "schema"


class SchemaValidation(BaseModel):
    role: SourceRole
    valid: bool
    missing_columns: list[str] = Field(default_factory=list)
    extra_columns: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CardinalityResult(BaseModel):
    left_rows: int
    right_rows: int
    matched_left: int
    unmatched_left: int
    duplicate_right_keys: int
    cardinality: str
    safe_to_join: bool


class MappingRule(BaseModel):
    target: str
    source_role: SourceRole | None = None
    source_column: str | None = None
    constant: Any | None = None
    precedence: int = 100
    reason_when_null: str = "source_not_provided"


class RecodingRule(BaseModel):
    source_role: SourceRole
    source_variable: str
    codebook_role: SourceRole
    sheet: str
    code_column: str
    label_column: str
    target: str
    unknown_policy: str = "unmapped"


class JoinResolution(BaseModel):
    status: str
    counts: dict[str, int] = Field(default_factory=dict)
    ambiguous_keys: int = 0


class QualityIssue(BaseModel):
    code: str
    severity: IssueSeverity
    message: str
    count: int = 0
    column: str | None = None


class ConsolidationManifest(BaseModel):
    run_id: UUID = Field(default_factory=uuid4)
    engine_version: str
    mapping_version: str
    config_hash: str
    input_hash: str
    status: ConsolidationStatus
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_hashes: dict[str, str] = Field(default_factory=dict)
    row_counts: dict[str, int] = Field(default_factory=dict)
    recoding_coverage: dict[str, float] = Field(default_factory=dict)
    issues: list[QualityIssue] = Field(default_factory=list)
    timings_ms: dict[str, int] = Field(default_factory=dict)
    target_columns: list[str] = Field(default_factory=list)
    relationship_summary: list[dict[str, Any]] = Field(default_factory=list)
    null_reasons: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    cohort_id_method: str | None = None
    preview: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    memory_bytes_estimate: int | None = None
    resource_metrics: dict[str, Any] = Field(default_factory=dict)


class ConsolidationPreview(BaseModel):
    status: ConsolidationStatus
    columns: list[str]
    rows: list[dict[str, Any]] = Field(max_length=100)
    total_rows: int
    issues: list[QualityIssue] = Field(default_factory=list)


class ConsolidationRunResult(BaseModel):
    run_id: UUID
    status: ConsolidationStatus
    total_rows: int
    unique_ids: int
    column_count: int
    artifacts: dict[str, str] = Field(default_factory=dict)
    issues: list[QualityIssue] = Field(default_factory=list)
