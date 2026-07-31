"""Detección por esquema, nunca por nombre de archivo únicamente."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

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


def detect_source_role(columns: Iterable[object]) -> SourceRole | None:
    normalized = {normalize_header(column) for column in columns}
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
    return SchemaValidation(
        role=role,
        valid=not missing,
        missing_columns=missing,
        extra_columns=sorted(normalized - required),
    )
