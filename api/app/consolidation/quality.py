"""Gates y trazabilidad agregada del resultado anual."""

from __future__ import annotations

import pandas as pd

from .models import IssueSeverity, QualityIssue


def validate_annual_contract(
    annual: pd.DataFrame,
    *,
    expected_rows: int,
    target_columns: tuple[str, ...],
    cohort: int,
) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    if len(annual) != expected_rows:
        issues.append(QualityIssue(code="row_count_changed", severity=IssueSeverity.BLOCKING, message="La salida no conserva el universo de Matrícula.", count=abs(len(annual) - expected_rows)))
    if list(annual.columns) != list(target_columns):
        issues.append(QualityIssue(code="target_schema_mismatch", severity=IssueSeverity.BLOCKING, message="La salida no respeta la plantilla objetivo."))
    if annual["id_aux"].astype("string").str.strip().duplicated().any():
        issues.append(QualityIssue(code="duplicate_id_aux", severity=IssueSeverity.BLOCKING, message="La salida contiene id_aux repetidos.", count=int(annual["id_aux"].duplicated().sum())))
    if not annual["cohorte"].astype("string").str.strip().eq(str(cohort)).all():
        issues.append(QualityIssue(code="invalid_cohort", severity=IssueSeverity.BLOCKING, message="La cohorte de salida no es uniforme."))
    if annual["cohorte_id"].astype("string").str.strip().duplicated().any():
        issues.append(QualityIssue(code="duplicate_cohort_id", severity=IssueSeverity.BLOCKING, message="cohorte_id no es único."))
    return issues


def null_reason_summary(annual: pd.DataFrame, source_targets: set[str]) -> list[dict[str, object]]:
    summary: list[dict[str, object]] = []
    for column in annual.columns:
        values = annual[column]
        null_count = int((values.isna() | values.astype("string").fillna("").str.strip().eq("")).sum())
        if null_count:
            reason = "source_value_missing" if column in source_targets else "unsupported_in_2026"
            summary.append({"column": column, "reason_code": reason, "count": null_count})
    return summary
