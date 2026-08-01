"""Detección por esquema, nunca por nombre de archivo únicamente."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any

from .models import SchemaValidation, SourceRole


def normalize_header(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^A-Z0-9]+", "_", text.upper()).strip("_")


ROLE_REQUIRED_COLUMNS: dict[SourceRole, frozenset[str]] = {
    SourceRole.MATRICULA: frozenset({"ID_AUX", "VIA", "CODIGO", "PREFERENCIA", "PTJE_POND"}),
    SourceRole.ARCHIVO_B: frozenset({"ID_AUX", "SEXO", "ANYO_EGRESO", "CODIGO_REGION_D", "RINDIO_PROCESO_ACTUAL"}),
    SourceRole.ARCHIVO_C: frozenset({"ID_AUX", "PROMEDIO_NOTAS", "PTJE_NEM", "PTJE_RANKING", "CLEC_REG_ACTUAL"}),
    SourceRole.ARCHIVO_D: frozenset({"ID_AUX", "ORDEN_PREF", "COD_CARRERA_PREF", "ESTADO_PREF", "TIPO_PREF", "PTJE_PREF"}),
    SourceRole.OFERTA: frozenset({"ANO", "CODIGO_UNICO", "CODIGO_IES", "CODIGO_CARRERA", "NOMBRE_CARRERA", "DEMRE"}),
    SourceRole.HISTORICA: frozenset({"ID_AUX", "COHORTE"}),
}

ROLE_SIGNATURE_COLUMNS: dict[SourceRole, frozenset[str]] = {
    SourceRole.MATRICULA: frozenset({"CODIGO_UNIV", "TIPO_MATRICULA"}),
    SourceRole.ARCHIVO_B: frozenset({"FECHA_NACIMIENTO", "PAIS_NACIMIENTO", "INGRESO_PERCAPITA_GRUPO_FA"}),
    SourceRole.ARCHIVO_C: frozenset({"MATE1_REG_ACTUAL", "CIEN_REG_ACTUAL", "MODULO_REG_ACTUAL"}),
    SourceRole.ARCHIVO_D: frozenset({"COD_CARRERA_PREF", "ESTADO_PREF"}),
    SourceRole.OFERTA: frozenset({"NOMBRE_IES", "NOMBRE_SEDE", "VIGENCIA"}),
    SourceRole.HISTORICA: frozenset({"PREFERENCIA2", "PTJE_POND"}),
}

ROLE_EXPECTED_COLUMNS: dict[SourceRole, frozenset[str]] = {
    SourceRole.ARCHIVO_B: frozenset({
        "ID_AUX", "ANYO_PROCESO", "FECHA_NACIMIENTO", "RBD", "COD_ENS",
        "REGIMEN", "RAMA_EDUCACIONAL", "GRUPO_DEPENDENCIA", "ANYO_EGRESO",
        "CODIGO_REGION", "CODIGO_PROVINCIA", "CODIGO_COMUNA",
        "CODIGO_REGION_D", "CODIGO_COMUNA_D", "SITUACION_EGRESO", "BEA",
        "PACE", "PAIS_NACIMIENTO", "SEXO", "INGRESO_PERCAPITA_GRUPO_FA",
        "RINDIO_PROCESO_ANTERIOR", "RINDIO_PROCESO_ACTUAL",
    }),
}


def detect_source_role(columns: Iterable[object]) -> SourceRole | None:
    normalized = {normalize_header(column) for column in columns}
    # ``cohorte`` es la señal estructural del histórico. Un histórico real
    # también contiene los puntajes de C y, sin esta precedencia, empata con C.
    if ROLE_REQUIRED_COLUMNS[SourceRole.HISTORICA] <= normalized and "COHORTE" in normalized:
        return SourceRole.HISTORICA
    matches: list[tuple[int, SourceRole]] = []
    for role, required in ROLE_REQUIRED_COLUMNS.items():
        if not required <= normalized:
            continue
        score = len(ROLE_SIGNATURE_COLUMNS.get(role, frozenset()) & normalized)
        matches.append((score, role))
    matches.sort(key=lambda item: item[0], reverse=True)
    if not matches or (len(matches) > 1 and matches[0][0] == matches[1][0]):
        return None
    return matches[0][1]


def validate_source_schema(
    role: SourceRole,
    columns: Iterable[object],
    aliases: dict[str, str] | None = None,
) -> SchemaValidation:
    normalized = {normalize_header(column) for column in columns}
    normalized_aliases = {
        normalize_header(source): normalize_header(target)
        for source, target in (aliases or {}).items()
    }
    normalized |= {target for source, target in normalized_aliases.items() if source in normalized}
    required = ROLE_REQUIRED_COLUMNS.get(role, frozenset())
    missing = sorted(required - normalized)
    optional_missing = sorted(ROLE_EXPECTED_COLUMNS.get(role, frozenset()) - normalized - required)
    return SchemaValidation(
        role=role,
        valid=not missing,
        missing_columns=missing,
        extra_columns=sorted(normalized - required),
        warnings=[f"Columna esperada no encontrada: {column}" for column in optional_missing],
    )


ROLE_LABELS: dict[SourceRole, str] = {
    SourceRole.PRIMARY: "Archivo base: conservará todas sus filas",
    SourceRole.SUPPLEMENT_1: "Aporta información adicional",
    SourceRole.SUPPLEMENT_2: "Aporta información adicional",
    SourceRole.SUPPLEMENT_3: "Aporta información adicional",
    SourceRole.SUPPLEMENT_4: "Aporta información adicional",
    SourceRole.EQUIVALENCE_1: "Traduce códigos a descripciones",
    SourceRole.EQUIVALENCE_2: "Traduce códigos a descripciones",
    SourceRole.HISTORICAL: "Contiene periodos anteriores",
    SourceRole.MATRICULA: "Archivo base de matrículas: conservará todas sus filas",
    SourceRole.ARCHIVO_B: "Aporta antecedentes demográficos y educacionales",
    SourceRole.ARCHIVO_C: "Aporta notas, ranking y pruebas",
    SourceRole.ARCHIVO_D: "Aporta preferencias mediante una regla especializada",
    SourceRole.OFERTA: "Aporta carrera, institución y sede",
    SourceRole.HISTORICA: "Contiene los periodos DEMRE anteriores",
    SourceRole.CODEBOOK_MATRICULA: "Libro de códigos para vía y tipo de matrícula",
    SourceRole.CODEBOOK_B: "Libro de códigos de antecedentes",
    SourceRole.CODEBOOK_C: "Libro de códigos de pruebas",
    SourceRole.CODEBOOK_D: "Libro de estados y preferencias",
}


def _codebook_role(sheet_names: Iterable[str]) -> SourceRole | None:
    names = {normalize_header(name) for name in sheet_names}
    if {"MATRICULA", "ANEXO_OFERTA_ACADEMICA"} <= names:
        return SourceRole.CODEBOOK_MATRICULA
    if "INSCRIPCION" in names and "ANEXO_COD_ENS" in names:
        return SourceRole.CODEBOOK_B
    if "RINDEN" in names and "ANEXO_COD_ENS" in names:
        return SourceRole.CODEBOOK_C
    if "POSTULACION_Y_SELECCION" in names and "ANEXO_ESTADO_PREFERENCIA" in names:
        return SourceRole.CODEBOOK_D
    return None


def _best_sheet(item: dict[str, Any]) -> dict[str, Any]:
    sheets = list(item.get("sheets") or [])
    return max(sheets, key=lambda sheet: (len(sheet.get("columns") or []), int(sheet.get("sample_rows") or 0)), default={})


def _looks_like_equivalence(sheet: dict[str, Any]) -> bool:
    columns = list(sheet.get("columns") or [])
    normalized = {normalize_header(column) for column in columns}
    if len(columns) != 2:
        return False
    semantic = any(any(marker in column for marker in ("COD", "ID", "CLAVE")) for column in normalized)
    semantic = semantic and any(any(marker in column for marker in ("DESC", "NOMBRE", "LABEL", "DETALLE")) for column in normalized)
    ratios = sheet.get("unique_ratio") or {}
    unique_column = any(float(value) >= 0.9 for value in ratios.values())
    return semantic and unique_column


def _suggest_common_keys(primary: dict[str, Any], related: dict[str, Any]) -> list[dict[str, str]]:
    primary_columns = {normalize_header(column): str(column) for column in primary.get("columns") or []}
    related_columns = {normalize_header(column): str(column) for column in related.get("columns") or []}
    common = set(primary_columns) & set(related_columns)
    ordered = sorted(common, key=lambda value: (not any(marker in value for marker in ("ID", "COD", "RUT", "CLAVE")), value))
    return [{"base": primary_columns[key], "related": related_columns[key]} for key in ordered[:3]]


def build_detection_proposal(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Construye una propuesta explicable desde estructura y muestras acotadas."""
    detected: list[dict[str, Any]] = []
    demre_roles: set[SourceRole] = set()
    for item in items:
        sheets = list(item.get("sheets") or [])
        codebook_role = _codebook_role(sheet.get("name", "") for sheet in sheets)
        best = _best_sheet(item)
        role = codebook_role
        if role is None:
            candidates = [detect_source_role(sheet.get("columns") or []) for sheet in sheets]
            candidates = [candidate for candidate in candidates if candidate is not None]
            role = candidates[0] if len(set(candidates)) == 1 else None
        if role is not None:
            demre_roles.add(role)
        detected.append({
            "dataset_id": item["dataset_id"], "name": item["name"],
            "kind": item.get("kind", "Archivo"), "sheet": best.get("name"),
            "columns": best.get("columns") or [], "column_count": len(best.get("columns") or []),
            "approximate_rows": best.get("approximate_rows"),
            "sample_rows": best.get("sample_rows"), "sha256": item.get("sha256"),
            "detected_role": role.value if role else None,
            "suggested_role": role.value if role else None,
            "role_label": ROLE_LABELS.get(role, "No se pudo determinar automáticamente") if role else "No se pudo determinar automáticamente",
            "confidence": 0.99 if codebook_role else 0.96 if role else 0.0,
            "suggested_keys": [], "warnings": [],
        })

    demre_data = {SourceRole.MATRICULA, SourceRole.ARCHIVO_B, SourceRole.ARCHIVO_C, SourceRole.ARCHIVO_D, SourceRole.OFERTA}
    is_demre = SourceRole.MATRICULA in demre_roles and len(demre_roles & demre_data) >= 3
    if is_demre:
        missing = sorted(role.value for role in demre_data - demre_roles if role is not SourceRole.ARCHIVO_B)
        return {
            "template": "demre_2026", "confidence": 0.98 if not missing else 0.9,
            "message": "Detectamos una consolidación Educación / DEMRE 2026. Podemos configurar automáticamente Matrícula, B, C, D, Oferta y sus libros de códigos.",
            "files": detected, "questions": [],
        }

    candidates = [row for row in detected if row["detected_role"] is None]
    equivalences = [row for row in candidates if _looks_like_equivalence(_best_sheet(next(item for item in items if item["dataset_id"] == row["dataset_id"])))]
    data_files = [row for row in candidates if row not in equivalences]
    data_files.sort(key=lambda row: int(row.get("approximate_rows") or 0), reverse=True)
    primary = data_files[0] if data_files else None
    if primary:
        primary["suggested_role"] = SourceRole.PRIMARY.value
        primary["role_label"] = ROLE_LABELS[SourceRole.PRIMARY]
        second_rows = int(data_files[1].get("approximate_rows") or 0) if len(data_files) > 1 else 0
        primary["confidence"] = 0.9 if int(primary.get("approximate_rows") or 0) > second_rows * 1.25 else 0.65
        primary_sheet = _best_sheet(next(item for item in items if item["dataset_id"] == primary["dataset_id"]))
        primary_ratios = primary_sheet.get("unique_ratio") or {}
        likely_keys = sorted(primary["columns"], key=lambda column: (-float(primary_ratios.get(column, 0)), normalize_header(column)))
        primary["suggested_keys"] = [{"base": column, "related": column} for column in likely_keys[:3] if any(marker in normalize_header(column) for marker in ("ID", "COD", "RUT", "CLAVE"))]
        for index, row in enumerate(data_files[1:5], start=1):
            row["suggested_role"] = f"supplement_{index}"
            row["role_label"] = ROLE_LABELS[SourceRole(f"supplement_{index}")]
            related_sheet = _best_sheet(next(item for item in items if item["dataset_id"] == row["dataset_id"]))
            row["suggested_keys"] = _suggest_common_keys(primary_sheet, related_sheet)
            row["confidence"] = 0.88 if len(row["suggested_keys"]) == 1 else 0.62 if row["suggested_keys"] else 0.2
            if not row["suggested_keys"]:
                row["warnings"].append("No encontramos una columna común segura; revisa la configuración.")
    for index, row in enumerate(equivalences[:2], start=1):
        row["suggested_role"] = f"equivalence_{index}"
        row["role_label"] = ROLE_LABELS[SourceRole(f"equivalence_{index}")]
        if primary:
            primary_sheet = _best_sheet(next(item for item in items if item["dataset_id"] == primary["dataset_id"]))
            related_sheet = _best_sheet(next(item for item in items if item["dataset_id"] == row["dataset_id"]))
            row["suggested_keys"] = _suggest_common_keys(primary_sheet, related_sheet)
        row["confidence"] = 0.92 if len(row["suggested_keys"]) == 1 else 0.65
    questions = []
    for row in detected:
        if len(row["suggested_keys"]) > 1 and row["suggested_role"] != SourceRole.PRIMARY.value:
            keys = " y ".join(key["base"] for key in row["suggested_keys"][:2])
            questions.append(f"Encontramos posibles columnas para relacionar {row['name']}: {keys}. Confirma cuál corresponde.")
    return {
        "template": "general", "confidence": float(primary["confidence"] if primary else 0),
        "message": "Preparamos una propuesta segura. Confirma las relaciones con confianza media o baja.",
        "files": detected, "questions": questions,
    }
