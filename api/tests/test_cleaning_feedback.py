import pandas as pd

from app.engine.clean import DEFAULT_RULES, analyze_and_clean
from app.engine.loader import _drop_trailing_total_rows
from app.engine.standardize import standardize_dataframe


def test_trailing_totals_detected_in_non_first_column():
    frame = pd.DataFrame(
        [
            ["G-001", "01/01/2025", "Arriendo", "100"],
            ["G-002", "02/01/2025", "Servicios", "200"],
            ["", "", "Subtotal gastos fijos", "300"],
            ["", "", "TOTAL GASTOS 2025", "300"],
        ],
        columns=["ID_Gasto", "Fecha", "Categoria Gasto", "Monto"],
    )
    report = {"avisos": []}

    cleaned = _drop_trailing_total_rows(frame, report)

    assert cleaned["ID_Gasto"].tolist() == ["G-001", "G-002"]
    assert report["filas_totales_omitidas"] == 2


def test_total_energies_with_business_key_is_not_removed():
    frame = pd.DataFrame(
        [["CLI-001", "Total Energies", "Santiago", "100"]],
        columns=["ID_Cliente", "Cliente", "Ciudad", "Monto"],
    )
    report = {"avisos": []}

    cleaned = _drop_trailing_total_rows(frame, report)

    assert len(cleaned) == 1
    assert report.get("filas_totales_omitidas", 0) == 0


def test_fuzzy_never_rewrites_geography_or_month_description():
    frame = pd.DataFrame(
        {
            "Comuna": ["San Fernando"] * 20 + ["San Bernardo"] * 4,
            "Descripcion": ["Cotizaciones mes 02"] * 20 + ["Cotizaciones mes 10"] * 4,
        }
    )

    standardized, report = standardize_dataframe(frame)

    assert standardized["Comuna"].tail(4).tolist() == ["San Bernardo"] * 4
    assert standardized["Descripcion"].tail(4).tolist() == ["Cotizaciones mes 10"] * 4
    assert report["fusiones_texto"]["total"] == 0
    assert report["sugerencias_fusion"]


def test_unambiguous_placeholders_are_detected_but_literal_none_is_preserved():
    frame = pd.DataFrame(
        {"Comentario": ["-", "S/I", "?", "N/D", "xx", "None", "null", "NA"]}
    )

    standardized, report = standardize_dataframe(frame)

    assert standardized["Comentario"].tolist() == frame["Comentario"].tolist()
    assert report["cambios"]["placeholders_detectados"] == 5


def test_boolean_and_currency_equivalences_are_deterministic():
    frame = pd.DataFrame(
        {
            "Activo": ["Si", "S", "TRUE", "1", "No", "FALSE", "0"],
            "Moneda": ["Clp", "$", "CLP", "pesos", "USD", "US$", "dólares"],
        }
    )

    standardized, report = standardize_dataframe(frame)

    assert standardized["Activo"].tolist() == ["Si", "Si", "Si", "Si", "No", "No", "No"]
    assert standardized["Moneda"].tolist() == ["CLP", "CLP", "CLP", "CLP", "USD", "USD", "USD"]
    assert report["cambios"]["equivalencias_booleanas"] == 5
    assert report["cambios"]["equivalencias_moneda"] == 5


def test_empty_columns_are_removed_by_default_when_cleaning_is_applied():
    assert DEFAULT_RULES["columnas_vacias"] is True
    frame = pd.DataFrame({"ID": ["A", "B"], "Vacia": ["", ""]})

    result = analyze_and_clean(frame, rules=None, apply=True)

    assert "Vacia" not in result["_df_limpio"].columns


def test_undated_sales_warning_formats_currency(client, auth_headers):
    csv = "Fecha;Monto\n;$2.543.373\n01/12/2025;$100.000\n"

    response = client.post(
        "/metrics",
        files={"file": ("ventas.csv", csv.encode("utf-8"), "text/csv")},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert any(
        "$2.543.373" in warning for warning in response.json()["advertencias"]
    )
