"""Trazabilidad celda a celda para exportaciones de limpieza."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pandas as pd

from ..version import ENGINE_VERSION
from .standardize import (
    is_missing,
    parse_date,
    parse_number,
    physical_missing_mask,
    semantic_missing_mask,
)

AUDIT_COLUMNS = [
    "archivo",
    "hoja",
    "fila_origen",
    "columna",
    "valor_original",
    "valor_final",
    "regla",
    "accion",
    "confianza",
    "confirmacion",
    "version_motor",
    "metadatos",
]


def _stable_hash(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _display(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def _rule_for_change(column_type: str) -> str:
    if column_type == "fecha":
        return "estandarizacion_fecha"
    if column_type == "numero":
        return "estandarizacion_numero"
    return "normalizacion_texto"


def build_audit_dataframe(
    *,
    filename: str,
    original: pd.DataFrame,
    cleaned: pd.DataFrame,
    original_source_rows: list[int],
    cleaned_source_rows: list[int],
    source_sheet: str | None,
    column_types: dict[str, str],
    column_confidence: dict[str, float | None],
    mapping: dict[str, str],
    rules: dict,
    scope: dict | None,
    removed_rows: list[dict],
    source_sha256: str,
    original_headers: list[str] | None = None,
) -> pd.DataFrame:
    """Registra cambios y valores conservados que requieren revisión.

    No afirma que una base esté "completa": la auditoría cubre exactamente
    las reglas ejecutadas y conserva metadatos suficientes para reproducir el
    alcance de la exportación.
    """

    roles_by_column = {column: role for role, column in mapping.items()}
    common_metadata = {
        "source_sha256": source_sha256,
        "rules_hash": _stable_hash(rules),
        "mapping_hash": _stable_hash(mapping),
        "scope": scope or {},
    }
    records: list[dict[str, Any]] = []

    def add(
        row: int | str,
        column: str,
        original_value: Any,
        final_value: Any,
        rule: str,
        action: str,
        confidence: float | None,
        confirmation: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        metadata = {**common_metadata, **(extra or {})}
        records.append(
            {
                "archivo": filename,
                "hoja": source_sheet or "CSV",
                "fila_origen": row,
                "columna": column,
                "valor_original": _display(original_value),
                "valor_final": _display(final_value),
                "regla": rule,
                "accion": action,
                "confianza": confidence,
                "confirmacion": confirmation,
                "version_motor": ENGINE_VERSION,
                "metadatos": json.dumps(metadata, ensure_ascii=False, sort_keys=True),
            }
        )

    if original_headers is not None:
        for old, new in zip(original_headers, original.columns, strict=False):
            if old != new:
                add(
                    "encabezado",
                    str(new),
                    old,
                    new,
                    "normalizacion_encabezado",
                    "transformado",
                    1.0,
                    "automatica_regla_determinista",
                )

    original_positions = {
        int(source_row): position for position, source_row in enumerate(original_source_rows)
    }
    for clean_position, source_row in enumerate(cleaned_source_rows):
        original_position = original_positions.get(int(source_row))
        if original_position is None:
            continue
        for column in cleaned.columns:
            if column not in original.columns:
                continue
            before = original.iloc[original_position][column]
            after = cleaned.iloc[clean_position][column]
            before_text = _display(before)
            after_text = _display(after)
            column_type = column_types.get(column, "texto")
            role = roles_by_column.get(column)
            confidence = column_confidence.get(column)
            context = {"tipo_columna": column_type, "rol": role}
            if before_text != after_text:
                add(
                    int(source_row),
                    column,
                    before,
                    after,
                    _rule_for_change(column_type),
                    "transformado",
                    confidence,
                    "automatica_regla_determinista",
                    context,
                )
                continue

            one = pd.Series([after_text])
            if bool(physical_missing_mask(one).iloc[0]):
                add(
                    int(source_row),
                    column,
                    before,
                    after,
                    "nulo_fisico",
                    "conservado_para_revision",
                    1.0,
                    "no_requerida",
                    context,
                )
                continue
            if bool(
                semantic_missing_mask(one, role, column_type=column_type).iloc[0]
            ):
                add(
                    int(source_row),
                    column,
                    before,
                    after,
                    "placeholder_semantico",
                    "conservado_literalmente",
                    1.0,
                    "no_requerida",
                    context,
                )
                continue
            if not is_missing(after_text) and (
                (column_type == "fecha" and parse_date(after_text) is None)
                or (column_type == "numero" and parse_number(after_text) is None)
            ):
                add(
                    int(source_row),
                    column,
                    before,
                    after,
                    "validacion_tipo",
                    "conservado_para_revision",
                    confidence,
                    "no_requerida",
                    context,
                )

    for removed in removed_rows:
        source_row = int(removed["fila_origen"])
        original_position = original_positions.get(source_row)
        original_record = (
            original.iloc[original_position].to_dict()
            if original_position is not None
            else {"detalle": "fila no disponible"}
        )
        add(
            source_row,
            "*",
            json.dumps(original_record, ensure_ascii=False, default=str),
            "",
            removed.get("regla", "duplicado_exacto_original"),
            "fila_eliminada",
            float(removed.get("confianza", 1.0)),
            "confirmada_por_usuario",
            {"motivo": removed.get("motivo")},
        )

    # Incluso cuando ninguna celda cambió, la exportación necesita una fila de
    # procedencia que vincule el archivo resultante con su fuente, alcance,
    # reglas y versión del motor. No se presenta como una transformación.
    add(
        "archivo",
        "*",
        f"{len(original)} filas",
        f"{len(cleaned)} filas",
        "alcance_exportacion",
        "metadatos_registrados",
        1.0,
        "no_requerida",
        {
            "filas_originales": len(original),
            "filas_exportadas": len(cleaned),
            "transformaciones_registradas": len(records),
        },
    )

    return pd.DataFrame.from_records(records, columns=AUDIT_COLUMNS)
