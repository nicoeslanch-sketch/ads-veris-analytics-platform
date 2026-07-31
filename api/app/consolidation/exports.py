"""Artefactos derivados, separados e inmutables."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl import Workbook, load_workbook

from .pipeline import PipelineOutput


def _safe_cell(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    if value is None or pd.isna(value):
        return None
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def write_dataframe(path: Path, frame: pd.DataFrame, *, sheet_name: str) -> None:
    if path.exists():
        raise FileExistsError(f"El artefacto ya existe: {path.name}")
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet(sheet_name)
    sheet.append(list(frame.columns))
    for row in frame.itertuples(index=False, name=None):
        sheet.append([_safe_cell(value) for value in row])
    workbook.save(path)


def write_pipeline_artifacts(output: PipelineOutput, directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    annual_path = directory / "DEMRE_2026_COMPATIBLE.xlsx"
    audit_path = directory / "AUDITORIA_CONSOLIDACION_DEMRE_2026.xlsx"
    manifest_path = directory / "manifest.json"
    write_dataframe(annual_path, output.annual, sheet_name="BASE DE DATOS")
    workbook = Workbook(write_only=True)
    for name, records in output.audit_tables.items():
        sheet = workbook.create_sheet(name[:31])
        if not records:
            sheet.append(["sin_hallazgos"])
            continue
        columns = list(dict.fromkeys(key for record in records for key in record))
        sheet.append(columns)
        for record in records:
            sheet.append([_safe_cell(record.get(column)) for column in columns])
    issues = workbook.create_sheet("issues")
    issues.append(["code", "severity", "message", "count", "column"])
    for issue in output.manifest.issues:
        issues.append([issue.code, issue.severity.value, issue.message, issue.count, issue.column])
    workbook.save(audit_path)
    manifest_path.write_text(output.manifest.model_dump_json(indent=2), encoding="utf-8")
    return {"annual": annual_path, "audit": audit_path, "manifest": manifest_path}


def annual_shape(path: Path) -> tuple[int, int]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        rows = workbook["BASE DE DATOS"].iter_rows(values_only=True)
        header = next(rows)
        count = sum(1 for row in rows if row and row[0] not in (None, ""))
        return count, len(header)
    finally:
        workbook.close()
