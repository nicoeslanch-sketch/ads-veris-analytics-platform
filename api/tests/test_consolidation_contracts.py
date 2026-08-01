from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.consolidation.models import (
    ConsolidationProjectConfig,
    SourceAssignment,
    SourceRole,
)
from app.consolidation.source_detection import detect_source_role, validate_source_schema
from app.consolidation.target_schema import TARGET_COLUMNS


@pytest.mark.parametrize(
    ("role", "columns"),
    [
        (SourceRole.MATRICULA, ["ID_aux", "VIA", "CODIGO", "PREFERENCIA", "PTJE_POND", "CODIGO_UNIV", "TIPO_MATRICULA"]),
        (SourceRole.ARCHIVO_B, ["ID_aux", "SEXO", "ANYO_EGRESO", "CODIGO_REGION_D", "RINDIO_PROCESO_ACTUAL", "FECHA_NACIMIENTO"]),
        (SourceRole.ARCHIVO_C, ["ID_aux", "PROMEDIO_NOTAS", "PTJE_NEM", "PTJE_RANKING", "CLEC_REG_ACTUAL", "MATE1_REG_ACTUAL"]),
        (SourceRole.ARCHIVO_D, ["ID_aux", "TIPO_PREF", "ORDEN_PREF", "COD_CARRERA_PREF", "ESTADO_PREF", "PTJE_PREF"]),
        (SourceRole.OFERTA, ["Año", "Código Único", "Código IES", "Código Carrera", "Nombre Carrera", "Demre", "Nombre IES"]),
        (SourceRole.HISTORICA, ["id_aux", "cohorte", "preferencia2", "ptje_pond"]),
    ],
)
def test_detects_source_by_schema(role, columns):
    assert detect_source_role(columns) is role


def test_ambiguous_or_incomplete_schema_is_not_guessed():
    assert detect_source_role(["ID_aux", "RBD"]) is None


def test_schema_validation_reports_names_not_declared_counts():
    validation = validate_source_schema(SourceRole.ARCHIVO_B, ["ID_aux", "SEXO"])
    assert validation.valid is False
    assert "ANYO_EGRESO" in validation.missing_columns


def test_target_has_exact_92_columns_and_order():
    assert len(TARGET_COLUMNS) == 92
    assert TARGET_COLUMNS[:5] == (
        "id_aux", "cohorte", "nac_rec", "nac", "region_domicilio"
    )
    assert TARGET_COLUMNS[-1] == "Edad_Q4"
    assert TARGET_COLUMNS[83] == "cuartiles_Nem"
    assert "RETENIDO_SIES" not in TARGET_COLUMNS


def test_project_rejects_duplicate_roles():
    source = SourceAssignment(dataset_id=uuid4(), role=SourceRole.MATRICULA)
    with pytest.raises(ValidationError):
        ConsolidationProjectConfig(name="Admisión", sources=[source, source])


def test_alias_can_satisfy_project_specific_schema():
    validation = validate_source_schema(
        SourceRole.ARCHIVO_B,
        ["ID_aux", "SEXO", "ANYO_EGRESO", "CODIGO_REGION_D", "RINDIO_PROCESO_ACTUAL", "RBD"],
        aliases={"RBD": "ID_RBD"},
    )
    assert validation.valid is True


def test_real_b_structure_matches_its_declared_book_contract():
    columns = [
        "ID_aux", "ANYO_PROCESO", "FECHA_NACIMIENTO", "RBD", "COD_ENS", "REGIMEN",
        "RAMA_EDUCACIONAL", "GRUPO_DEPENDENCIA", "ANYO_EGRESO", "CODIGO_REGION",
        "CODIGO_PROVINCIA", "CODIGO_COMUNA", "CODIGO_REGION_D", "CODIGO_COMUNA_D",
        "SITUACION_EGRESO", "BEA", "PACE", "PAIS_NACIMIENTO", "SEXO",
        "INGRESO_PERCAPITA_GRUPO_FA", "RINDIO_PROCESO_ANTERIOR", "RINDIO_PROCESO_ACTUAL",
    ]
    validation = validate_source_schema(SourceRole.ARCHIVO_B, columns, aliases={"ID_RBD": "RBD"})
    assert validation.valid is True
    assert validation.warnings == []


def test_extra_columns_do_not_prevent_detection():
    columns = ["ID_aux", "VIA", "CODIGO", "PREFERENCIA", "PTJE_POND", "CODIGO_UNIV", "TIPO_MATRICULA", "EXTRA"]
    assert detect_source_role(columns) is SourceRole.MATRICULA


def test_d_detector_does_not_confuse_generic_id_table():
    assert detect_source_role(["ID_aux", "ESTADO_PREF"]) is None


def test_historical_detector_accepts_real_schema_without_cohort_id():
    assert detect_source_role(["id_aux", "cohorte", "preferencia2", "ptje_pond"]) is SourceRole.HISTORICA


def test_historical_detector_wins_when_it_also_contains_c_scores():
    columns = ["id_aux", "cohorte", "preferencia2", "ptje_pond", "PROMEDIO_NOTAS", "PTJE_NEM", "PTJE_RANKING", "CLEC_REG_ACTUAL", "MATE1_REG_ACTUAL", "CIEN_REG_ACTUAL"]
    assert detect_source_role(columns) is SourceRole.HISTORICA
