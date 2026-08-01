from app.consolidation.source_detection import build_detection_proposal


def _item(dataset_id, name, columns, rows, *, sheets=None):
    return {
        "dataset_id": dataset_id,
        "name": name,
        "kind": "Excel" if sheets else "CSV",
        "sha256": "a" * 64,
        "sheets": sheets or [{
            "name": "Datos", "columns": columns, "approximate_rows": rows,
            "sample_rows": min(rows, 1000),
            "unique_ratio": {column: (1.0 if "ID" in column or "COD" in column else 0.2) for column in columns},
        }],
    }


def test_general_detection_suggests_base_and_common_keys():
    proposal = build_detection_proposal([
        _item("ventas", "ventas.csv", ["ID_VENTA", "ID_PRODUCTO", "MONTO"], 1000),
        _item("productos", "productos.csv", ["ID_PRODUCTO", "DESCRIPCION", "CATEGORIA", "COSTO"], 100),
    ])
    assert proposal["template"] == "general"
    by_id = {item["dataset_id"]: item for item in proposal["files"]}
    assert by_id["ventas"]["suggested_role"] == "primary"
    assert by_id["productos"]["suggested_role"] == "supplement_1"
    assert by_id["productos"]["suggested_keys"] == [{"base": "ID_PRODUCTO", "related": "ID_PRODUCTO"}]


def test_general_detection_recognizes_equivalence_table():
    proposal = build_detection_proposal([
        _item("ventas", "ventas.csv", ["ID_VENTA", "COD_ESTADO", "MONTO"], 1000),
        _item("estados", "estados.csv", ["COD_ESTADO", "DESCRIPCION"], 3),
    ])
    by_id = {item["dataset_id"]: item for item in proposal["files"]}
    assert by_id["estados"]["suggested_role"] == "equivalence_1"
    assert by_id["estados"]["suggested_keys"] == [{"base": "COD_ESTADO", "related": "COD_ESTADO"}]
    assert "Traduce" in by_id["estados"]["role_label"]


def test_demre_group_is_detected_structurally_with_books():
    proposal = build_detection_proposal([
        _item("m", "uno.csv", ["ID_aux", "CODIGO_UNIV", "CODIGO", "VIA", "PREFERENCIA", "PTJE_POND", "TIPO_MATRICULA"], 100),
        _item("b", "dos.csv", ["ID_aux", "SEXO", "ANYO_EGRESO", "CODIGO_REGION_D", "RINDIO_PROCESO_ACTUAL", "FECHA_NACIMIENTO", "PAIS_NACIMIENTO", "INGRESO_PERCAPITA_GRUPO_FA"], 100),
        _item("c", "tres.csv", ["ID_aux", "PROMEDIO_NOTAS", "PTJE_NEM", "PTJE_RANKING", "CLEC_REG_ACTUAL", "MATE1_REG_ACTUAL", "CIEN_REG_ACTUAL", "MODULO_REG_ACTUAL"], 100),
        _item("d", "cuatro.csv", ["ID_aux", "ORDEN_PREF", "COD_CARRERA_PREF", "ESTADO_PREF", "TIPO_PREF", "PTJE_PREF"], 1000),
        _item("book", "cinco.xlsx", [], 0, sheets=[
            {"name": "Matrícula", "columns": ["Variable", "Detalle"], "approximate_rows": 20, "sample_rows": 20, "unique_ratio": {}},
            {"name": "Anexo - Oferta académica", "columns": ["PROCESO", "CODIGO_CARRERA"], "approximate_rows": 20, "sample_rows": 20, "unique_ratio": {}},
        ]),
    ])
    assert proposal["template"] == "demre_2026"
    roles = {item["suggested_role"] for item in proposal["files"]}
    assert {"matricula", "archivo_b", "archivo_c", "archivo_d", "codebook_matricula"} <= roles
    assert proposal["confidence"] >= 0.9
