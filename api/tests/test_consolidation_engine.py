import json
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import Workbook

from app.consolidation.codebooks import CodebookResult, parse_codebook, recode_values
from app.consolidation.exports import annual_shape, write_pipeline_artifacts
from app.consolidation.historical import append_historical, build_cohort_ids
from app.consolidation.models import ConsolidationStatus, SourceRole
from app.consolidation.pipeline import run_local_pipeline, stable_hash
from app.consolidation.resolvers.offer import resolve_offer_frame
from app.consolidation.resolvers.preferences_d import resolve_preferences_frame, selected_status_codes
from app.consolidation.target_schema import TARGET_COLUMNS, resolve_target_columns


def _write_csv(path: Path, frame: pd.DataFrame) -> Path:
    frame.to_csv(path, sep=";", index=False, encoding="utf-8-sig")
    return path


def _write_book(path: Path, sheets: dict[str, list[list[object]]]) -> Path:
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for row in rows:
            ws.append(row)
    wb.save(path)
    return path


@pytest.fixture
def synthetic_sources(tmp_path: Path) -> dict[SourceRole, Path]:
    ids = [f"00{i}" for i in range(10)]
    matricula = pd.DataFrame({
        "ID_aux": ids, "CODIGO_UNIV": ["11"] * 10,
        "CODIGO": [f"1{i:03}" for i in range(10)], "VIA": ["1"] * 10,
        "PREFERENCIA": ["1"] * 10, "PTJE_POND": ["600"] * 10,
        "TIPO_MATRICULA": ["REGULAR"] * 10,
    })
    b = pd.DataFrame({
        "ID_aux": ids, "SEXO": ["1", "2"] * 5, "ANYO_EGRESO": ["2025"] * 10,
        "CODIGO_REGION_D": ["13"] * 10, "CODIGO_COMUNA_D": ["13101"] * 10,
        "INGRESO_PERCAPITA_GRUPO_FA": ["3"] * 10, "RINDIO_PROCESO_ACTUAL": ["1"] * 10,
        "RBD": [f"0{i}" for i in range(10)], "COD_ENS": ["310"] * 10,
    })
    c = pd.DataFrame({
        "ID_aux": ids, "PROMEDIO_NOTAS": ["6.0"] * 10, "PTJE_NEM": ["700"] * 10,
        "PTJE_RANKING": ["710"] * 10, "RBD": [f"0{i}" for i in range(10)],
        "COD_ENS": ["310"] * 10,
    })
    d_rows = []
    for idx, key in enumerate(ids):
        for order in range(1, 5):
            d_rows.append({
                "ID_aux": key, "ORDEN_PREF": str(order),
                "COD_CARRERA_PREF": f"1{idx:03}" if order == 1 else f"9{order:03}",
                "ESTADO_PREF": "24" if order == 1 else "25", "TIPO_PREF": "R", "PTJE_PREF": "600",
            })
    offer_rows = []
    for idx in range(10):
        offer_rows.append({
            "Año": "OFE_2026", "Demre": f"1{idx:03}", "Vigencia": "Vigente con estudiantes nuevos",
            "Nombre Carrera": f"Carrera {idx}", "Nombre IES": "Universidad", "Código IES": "11",
            "Nombre Sede": "Central", "Región Sede": "Metropolitana", "Comuna Sede": "Santiago",
            "Área del conocimiento": "Educación", "Grado Académico": "Licenciatura",
            "Duración Estudios": "10", "Modalidad": "Presencial", "Tipo Carrera": "Regular",
            "Tipo de institución": "Universidad", "Ponderación Notas": "10",
            "Ponderación Ranking Notas": "20", "Ponderación Lenguaje": "20",
            "Ponderación Matemáticas": "30", "Ponderación Historia": "10",
            "Ponderación Ciencias": "10", "Vacantes Semestre Uno": "100",
        })
    sources = {
        SourceRole.MATRICULA: _write_csv(tmp_path / "m.csv", matricula),
        SourceRole.ARCHIVO_B: _write_csv(tmp_path / "b.csv", b),
        SourceRole.ARCHIVO_C: _write_csv(tmp_path / "c.csv", c),
        SourceRole.ARCHIVO_D: _write_csv(tmp_path / "d.csv", pd.DataFrame(d_rows)),
        SourceRole.OFERTA: _write_book(tmp_path / "offer.xlsx", {"in": [list(offer_rows[0]), *[list(row.values()) for row in offer_rows]]}),
        SourceRole.CODEBOOK_B: _write_book(tmp_path / "book_b.xlsx", {"Anexo - COD_ENS": [["Código", "Descripción"], ["310", "Media HC"]]}),
        SourceRole.CODEBOOK_C: _write_book(tmp_path / "book_c.xlsx", {"Anexo - COD_ENS": [["Código", "Descripción"], ["310", "Media HC"]]}),
        SourceRole.CODEBOOK_D: _write_book(tmp_path / "book_d.xlsx", {"Anexo -  Estado Preferencia": [["CÓD.", "DESCRIPCIÓN"], ["24", "ESTÁS SELECCIONADA/O PARA ESTA CARRERA"], ["25", "LISTA DE ESPERA"]]}),
    }
    return sources


def test_ids_and_codes_preserve_leading_zero(synthetic_sources):
    output = run_local_pipeline(synthetic_sources)
    assert output.annual.loc[0, "id_aux"] == "000"
    assert output.annual.loc[0, "rbd"] == "00"


def test_pipeline_keeps_grain_and_target(synthetic_sources):
    output = run_local_pipeline(synthetic_sources)
    assert output.annual.shape == (10, 92)
    assert tuple(output.annual.columns) == TARGET_COLUMNS
    assert output.annual["id_aux"].nunique() == 10
    assert output.manifest.status is ConsolidationStatus.VALID_WITH_WARNINGS


def test_missing_b_is_partial_and_keeps_schema(synthetic_sources):
    sources = {role: path for role, path in synthetic_sources.items() if role not in {SourceRole.ARCHIVO_B, SourceRole.CODEBOOK_B}}
    output = run_local_pipeline(sources)
    assert output.manifest.status is ConsolidationStatus.PARTIAL
    assert output.annual.shape == (10, 92)
    assert output.annual["sexo"].isna().all()
    assert any(row["column"] == "sexo" for row in output.audit_tables["null_reasons"])


def test_duplicate_matricula_blocks_before_join(synthetic_sources):
    frame = pd.read_csv(synthetic_sources[SourceRole.MATRICULA], sep=";", dtype="string")
    frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    _write_csv(synthetic_sources[SourceRole.MATRICULA], frame)
    with pytest.raises(ValueError, match="repetido"):
        run_local_pipeline(synthetic_sources)


def test_codebook_unknown_and_conflict(tmp_path):
    path = _write_book(tmp_path / "book.xlsx", {"Notas": [["x"]], "Códigos": [["Código", "Descripción"], ["01", "Uno"], ["02", "Dos"], ["02", "Deux"]]})
    result = parse_codebook(path, sheet_name="Códigos", code_column="Código", label_column="Descripción")
    assert result.mapping["01"] == "Uno"
    assert result.conflicts["02"] == ("Deux", "Dos")
    values, counts = recode_values(["01", "02", "03", ""], result)
    assert values == ["Uno", None, None, None]
    assert counts == {"mapped": 1, "unmapped": 1, "conflict": 1, "empty": 1}


def test_d_unique_no_match_and_ambiguous():
    m = pd.DataFrame({"ID_aux": ["1", "2", "3"], "CODIGO": ["10", "20", "30"]})
    d = pd.DataFrame({
        "ID_aux": ["1", "2", "3", "3"], "COD_CARRERA_PREF": ["10", "99", "30", "30"],
        "ESTADO_PREF": ["24"] * 4, "ORDEN_PREF": ["1", "1", "1", "2"], "PTJE_PREF": ["1"] * 4,
    })
    resolved, counts = resolve_preferences_frame(m, d, frozenset({"24"}))
    assert resolved["ID_aux"].tolist() == ["1"]
    assert counts == {"d_match_unique": 1, "d_ambiguous": 1, "d_no_match": 1}


def test_selected_status_comes_from_book():
    book = CodebookResult({"24": "ESTÁS SELECCIONADA/O PARA ESTA CARRERA", "25": "LISTA"}, {}, "s", "c", "l")
    assert selected_status_codes(book) == frozenset({"24"})


def test_offer_unique_and_ambiguous():
    frame = pd.DataFrame([
        {"Año": "OFE_2026", "Demre": "10", "Vigencia": "Vigente con estudiantes nuevos", "Nombre": "A"},
        {"Año": "OFE_2026", "Demre": "20", "Vigencia": "Vigente", "Nombre": "B"},
        {"Año": "OFE_2026", "Demre": "20", "Vigencia": "Vigente", "Nombre": "C"},
        {"Año": "OFE_2025", "Demre": "30", "Vigencia": "Vigente", "Nombre": "D"},
    ])
    resolved, counts = resolve_offer_frame(frame, ["Nombre"])
    assert resolved["codigo_carrera"].tolist() == ["10"]
    assert counts == {"offer_unique": 1, "offer_ambiguous": 1}


def test_offer_resolves_only_by_declared_vigencia():
    frame = pd.DataFrame([
        {"Año": "OFE_2026", "Demre": "10", "Vigencia": "Vigente con estudiantes nuevos", "Nombre": "A"},
        {"Año": "OFE_2026", "Demre": "10", "Vigencia": "No vigente", "Nombre": "B"},
    ])
    resolved, counts = resolve_offer_frame(frame, ["Nombre"])
    assert resolved.iloc[0]["Nombre"] == "A"
    assert counts == {"offer_resolved_by_vigencia": 1}


def test_cohort_fallback_is_deterministic_and_unique():
    values, method = build_cohort_ids(["001", "002"], 2026)
    assert values.tolist() == ["2026:001", "2026:002"]
    assert method == "generated_fallback"


def test_cohort_fallback_rejects_duplicates():
    with pytest.raises(ValueError, match="duplicado"):
        build_cohort_ids(["1", "1"], 2026)


def test_historical_incompatible_returns_warning():
    combined, warnings = append_historical(pd.DataFrame({"old": [1]}), pd.DataFrame({"new": [2]}))
    assert combined is None
    assert warnings == ["historical_schema_incompatible"]


def test_custom_target_is_validated():
    assert resolve_target_columns(["id_aux", "cohorte"]) == ("id_aux", "cohorte")
    with pytest.raises(ValueError, match="duplicadas"):
        resolve_target_columns(["id_aux", "id_aux"])


def test_manifest_hash_is_stable():
    assert stable_hash({"b": 2, "a": 1}) == stable_hash({"a": 1, "b": 2})


def test_exports_are_separate_and_do_not_overwrite(synthetic_sources, tmp_path):
    output = run_local_pipeline(synthetic_sources)
    artifacts = write_pipeline_artifacts(output, tmp_path / "out")
    assert annual_shape(artifacts["annual"]) == (10, 92)
    assert json.loads(artifacts["manifest"].read_text(encoding="utf-8"))["input_hash"]
    with pytest.raises(FileExistsError):
        write_pipeline_artifacts(output, tmp_path / "out")
