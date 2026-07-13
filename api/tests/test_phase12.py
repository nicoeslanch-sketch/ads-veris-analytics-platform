"""Fase 12, Bloque 1: duplicados no destructivos e identidad de filas."""

import io

import openpyxl
import pandas as pd
import pytest

from app.engine.clean import (
    analyze_and_clean,
    classify_identifier_kind,
    exclude_from_statistical_outliers,
)


def _clean(client, auth_headers, csv: str, **data):
    return client.post(
        "/clean",
        files={"file": ("fase12.csv", csv.encode("utf-8"), "text/csv")},
        data={key: str(value).lower() if isinstance(value, bool) else value for key, value in data.items()},
        headers=auth_headers,
    )


def test_exactos_se_detectan_siempre_y_solo_se_eliminan_con_flag(client, auth_headers):
    csv = "Producto;Ventas\nA;100\nA;100\n"
    safe = _clean(client, auth_headers, csv, apply=True).json()

    assert safe["problemas"]["duplicados"] == 1
    assert safe["correcciones"]["filas_duplicadas_a_eliminar"] == 0
    assert safe["resumen"]["filas_despues"] == 2
    assert safe["duplicados_detalle"] == {
        **safe["duplicados_detalle"],
        "exactos": 1,
        "grupos": 1,
        "filas_involucradas": 2,
        "tamano_maximo_grupo": 2,
        "filas_seleccionadas_para_eliminar": 0,
        "filas_eliminadas": 0,
        "eliminacion_habilitada": False,
    }

    confirmed = _clean(
        client, auth_headers, csv, apply=True, eliminar_duplicados=True
    ).json()
    assert confirmed["resumen"]["filas_despues"] == 1
    assert confirmed["correcciones"]["filas_duplicadas_a_eliminar"] == 1
    assert confirmed["correcciones"]["filas_duplicadas_eliminadas"] == 1
    assert confirmed["opciones_aplicacion"]["eliminar_duplicados"] is True


def test_normalizados_no_son_eliminables_ni_con_flag(client, auth_headers):
    csv = "Cliente;Ventas\nJuan  Perez;100\nJuan Perez;100\n"
    body = _clean(
        client, auth_headers, csv, apply=True, eliminar_duplicados=True
    ).json()

    assert body["problemas"]["duplicados"] == 0
    assert body["problemas"]["duplicados_probables"] == 1
    assert body["resumen"]["filas_despues"] == 2
    assert body["resumen"]["calidad_despues"] == body["resumen"]["calidad_antes"]
    assert body["correcciones"]["filas_duplicadas_eliminadas"] == 0


@pytest.mark.parametrize("header", ["Año", "RUT Cliente", "Teléfono", "Código Producto"])
def test_nombre_de_atributo_no_cambia_el_criterio_de_duplicados(
    client, auth_headers, header
):
    csv = f"{header};Detalle\n100;Mismo\n100;Mismo\n"
    body = _clean(client, auth_headers, csv, apply=True).json()

    assert body["duplicados_criterio"] == "fila_exacta_original_con_confirmacion"
    assert body["problemas"]["duplicados"] == 1
    assert body["resumen"]["filas_despues"] == 2


@pytest.mark.parametrize("header", ["Año", "RUT", "Teléfono", "Código", "SKU"])
def test_exclusion_iqr_es_independiente_de_la_taxonomia_de_duplicados(header):
    values = [str(value) for value in range(10, 19)] + ["99999999"]
    df = pd.DataFrame({header: values})
    result = analyze_and_clean(df, None, False, mapping={"monto": header})

    assert exclude_from_statistical_outliers(header, "monto") is True
    assert result["reporte_calidad"][header].get("outliers", 0) == 0


def test_folio_es_documento_y_no_habilita_borrado(client, auth_headers):
    csv = "Folio;Producto;Ventas\nF-1;A;100\nF-1;A;100\n"
    body = _clean(client, auth_headers, csv, apply=True).json()

    assert classify_identifier_kind("Folio") == "documento"
    assert body["duplicados_detalle"]["identificadores_fila"] == []
    assert body["resumen"]["filas_despues"] == 2


def test_conflicto_de_id_se_reporta_como_conflicto_no_duplicado(client, auth_headers):
    csv = "ID;Producto;Ventas\nMOV-1;A;100\nMOV-1;B;200\n"
    body = _clean(client, auth_headers, csv, apply=True).json()

    assert classify_identifier_kind("ID") == "fila"
    assert body["problemas"]["duplicados"] == 0
    assert body["duplicados_detalle"]["conflictos_id"] == 1
    assert body["duplicados_detalle"]["ejemplos_conflictos_id"][0]["columna"] == "ID"
    assert body["resumen"]["filas_despues"] == 2


def test_grupo_grande_advierte_granularidad_omitida(client, auth_headers):
    csv = "Producto;Ventas\nA;100\nA;100\nA;100\n"
    body = _clean(client, auth_headers, csv).json()

    detail = body["duplicados_detalle"]
    assert detail["exactos"] == 2
    assert detail["tamano_maximo_grupo"] == 3
    assert detail["posible_granularidad_omitida"] is True
    assert any("variable diferenciadora" in aviso for aviso in body["avisos"])


def test_regla_heredada_duplicados_false_no_desactiva_deteccion(client, auth_headers):
    csv = "Producto;Ventas\nA;100\nA;100\n"
    body = _clean(
        client,
        auth_headers,
        csv,
        apply=True,
        rules='{"duplicados": false}',
    ).json()

    assert body["reglas_activas"]["duplicados"] is False
    assert body["problemas"]["duplicados"] == 1
    assert body["correcciones"]["filas_duplicadas_a_eliminar"] == 0
    assert body["resumen"]["filas_despues"] == 2


def test_cache_distingue_decision_de_eliminar(client, auth_headers, monkeypatch):
    from app.routes import pipeline as pipeline_module

    with pipeline_module._CACHE_LOCK:
        pipeline_module._CLEAN_CACHE.clear()
    calls = {"count": 0}
    real = pipeline_module.analyze_and_clean

    def counted(*args, **kwargs):
        calls["count"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(pipeline_module, "analyze_and_clean", counted)
    csv = "Producto;Ventas\nCACHE-F12;123\nCACHE-F12;123\n"
    safe = _clean(client, auth_headers, csv, apply=True).json()
    confirmed = _clean(
        client, auth_headers, csv, apply=True, eliminar_duplicados=True
    ).json()
    again = _clean(client, auth_headers, csv, apply=True).json()

    assert calls["count"] == 2
    assert safe["resumen"]["filas_despues"] == again["resumen"]["filas_despues"] == 2
    assert confirmed["resumen"]["filas_despues"] == 1


def test_metricas_respetan_la_misma_decision_de_sesion(client, auth_headers):
    csv = "Fecha;Producto;Ventas\n01/05/2026;A;100\n01/05/2026;A;100\n"
    common = {
        "files": {"file": ("metricas_f12.csv", csv.encode("utf-8"), "text/csv")},
        "headers": auth_headers,
    }
    safe = client.post("/metrics", **common).json()
    confirmed = client.post(
        "/metrics", data={"eliminar_duplicados": "true"}, **common
    ).json()

    assert safe["kpis"]["transacciones"] == 2
    assert safe["kpis"]["ingresos_totales"]["valor"] == 200
    assert confirmed["kpis"]["transacciones"] == 1
    assert confirmed["kpis"]["ingresos_totales"]["valor"] == 100


def test_limpieza_asistida_no_borra_por_instruccion_libre(client, auth_headers):
    csv = "Producto;Ventas\nA;100\nA;100\n"
    response = client.post(
        "/clean/assisted",
        files={"file": ("asistida_f12.csv", csv.encode("utf-8"), "text/csv")},
        data={"instructions": "elimina duplicados"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["resumen"]["filas_despues"] == 2
    assert body["opciones_aplicacion"]["eliminar_duplicados"] is False
    assert any("confirmar" in aviso for aviso in body["dirigida"]["avisos"])


def test_fila_origen_real_llega_a_preview_y_observaciones(client, auth_headers, monkeypatch):
    from app.routes import pipeline as pipeline_module

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Datos"
    ws.append(["REPORTE DE PRUEBA"])
    ws.append(["Producto", "Ventas"])
    ws.append(["A", 100])
    ws.append(["A", 100])
    buf = io.BytesIO()
    wb.save(buf)
    content = buf.getvalue()
    files = {
        "file": (
            "origen_f12.xlsx",
            content,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }

    cleaned = client.post(
        "/clean",
        files=files,
        data={"apply": "true", "eliminar_duplicados": "true"},
        headers=auth_headers,
    ).json()
    duplicate_issue = next(issue for issue in cleaned["preview"]["issues"] if issue["tipo"] == "duplicado")
    assert duplicate_issue["fila_origen"] == 4

    monkeypatch.setattr(
        pipeline_module,
        "require_capability_for_user",
        lambda user_id, capability, settings: "analista",
    )
    download = client.post(
        "/clean/download",
        files=files,
        data={"fmt": "xlsx", "eliminar_duplicados": "true"},
        headers=auth_headers,
    )
    assert download.status_code == 200
    exported = openpyxl.load_workbook(io.BytesIO(download.content), data_only=False)
    assert exported["Datos_limpios"].max_row == 2
    observations = list(exported["Observaciones"].iter_rows(min_row=2, values_only=True))
    removed = next(row for row in observations if row[3] == "duplicado_eliminado")
    assert removed[0] == 4
    assert removed[1] == "Datos"


def test_respuesta_conserva_campos_anteriores_y_agrega_detalle(client, auth_headers):
    body = _clean(client, auth_headers, "Producto;Ventas\nA;100\nA;100\n").json()
    for field in (
        "resumen", "problemas", "correcciones", "reglas_activas", "preview",
        "estandarizacion", "column_types", "mapeo", "reporte_calidad", "avisos",
        "duplicados_criterio", "fusiones_texto",
    ):
        assert field in body
    assert "duplicados_detalle" in body
    assert "opciones_aplicacion" in body
