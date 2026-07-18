"""Trazabilidad celda a celda para exportaciones de limpieza."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pandas as pd

from ..version import ENGINE_VERSION
from .standardize import (
    is_missing,
    map_unique,
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
    detected_duplicate_rows: list[dict] | None = None,
    revision: int | None = None,
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
        "revision": revision,
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
    valid_pairs = [
        (clean_position, original_positions[int(source_row)], int(source_row))
        for clean_position, source_row in enumerate(cleaned_source_rows)
        if int(source_row) in original_positions
    ]
    if valid_pairs:
        clean_positions, source_positions, aligned_rows = zip(*valid_pairs, strict=True)
        common_columns = [column for column in cleaned.columns if column in original.columns]

        # La versión anterior ejecutaba dos `.iloc` y varias Series de una celda
        # dentro de un bucle fila × columna. Alinear una sola vez y calcular
        # máscaras vectoriales conserva el mismo contrato con costo lineal.
        before_frame = original.iloc[list(source_positions)][common_columns].reset_index(drop=True)
        after_frame = cleaned.iloc[list(clean_positions)][common_columns].reset_index(drop=True)

        def display_series(series: pd.Series) -> pd.Series:
            missing = series.isna()
            return series.astype(str).mask(missing, "")

        for column in common_columns:
            before_values = before_frame[column]
            after_values = after_frame[column]
            before_text = display_series(before_values)
            after_text = display_series(after_values)
            changed = before_text.ne(after_text)
            column_type = column_types.get(column, "texto")
            role = roles_by_column.get(column)
            confidence = column_confidence.get(column)
            context = {"tipo_columna": column_type, "rol": role}

            physical = physical_missing_mask(after_text) & ~changed
            semantic = (
                semantic_missing_mask(after_text, role, column_type=column_type)
                & ~changed
                & ~physical
            )
            invalid = pd.Series(False, index=after_text.index)
            candidates = ~changed & ~physical & ~semantic & ~after_text.map(is_missing)
            if column_type == "fecha":
                parsed = map_unique(after_text, parse_date)
                invalid = candidates & parsed.isna()
            elif column_type == "numero":
                parsed = map_unique(after_text, parse_number)
                invalid = candidates & parsed.isna()

            def add_mask(mask: pd.Series, rule: str, action: str, conf: float | None, confirmation: str) -> None:
                for position in mask[mask].index:
                    add(
                        aligned_rows[position],
                        column,
                        before_values.iat[position],
                        after_values.iat[position],
                        rule,
                        action,
                        conf,
                        confirmation,
                        context,
                    )

            add_mask(
                changed,
                _rule_for_change(column_type),
                "transformado",
                confidence,
                "automatica_regla_determinista",
            )
            add_mask(physical, "nulo_fisico", "conservado_para_revision", 1.0, "no_requerida")
            add_mask(semantic, "placeholder_semantico", "conservado_literalmente", 1.0, "no_requerida")
            add_mask(invalid, "validacion_tipo", "conservado_para_revision", confidence, "no_requerida")

    removed_source_rows = {int(row["fila_origen"]) for row in removed_rows}
    for duplicate in detected_duplicate_rows or []:
        source_row = int(duplicate["fila_origen"])
        if source_row in removed_source_rows:
            continue
        add(
            source_row,
            "*",
            "fila repetida exacta",
            "fila conservada",
            "duplicado_exacto_original",
            "duplicado_detectado_y_conservado",
            1.0,
            "pendiente_confirmacion",
            {"motivo": duplicate.get("motivo")},
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
