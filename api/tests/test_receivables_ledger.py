"""Synthetic balances never borrow sales amounts, historical dates or IDs."""

import pandas as pd
import pytest

from app.engine.business import analyze_business_workbook, classify_business_sheets
from app.engine.mapping import resolve_mapping
from app.engine.receivables import analyze_receivables, is_receivable_sheet


def _row(**updates):
    return {"IDCxC": "R1", "IDVenta": "V001", "Saldo_CLP": 60,
            "MontoOriginal_CLP": 100, "EstadoCxC": "Pendiente",
            "FechaEmision": "2026-01-01", "FechaVencimiento": "2026-02-01",
            **updates}


def _ledger(rows=None, **kwargs):
    return analyze_receivables({"CxC": pd.DataFrame(rows or [_row()])}, {"v001", "v2"}, **kwargs)


def test_balance_is_not_original_document_value_or_cash_received():
    result = _ledger()
    assert result["saldo_declarado"] == result["saldo_validado"] == 60
    assert result["documentos_pendientes"] == 1
    assert result["estado"] == "partial"
    assert result["fecha_corte"] is None
    assert result["saldo_vencido"] is None


@pytest.mark.parametrize("value", [-5, None, "desconocido", float("inf"), float("-inf")])
def test_invalid_balances_do_not_reduce_or_inflate_the_valid_portfolio(value):
    result = _ledger([_row(), _row(IDCxC="R2", IDVenta="V2", Saldo_CLP=value)])
    assert result["saldo_validado"] == 60
    assert result["filas_saldo_invalido"] == 1
    assert result["filas_validas"] == 1


@pytest.mark.parametrize("updates", [
    {"MontoOriginal_CLP": -1}, {"MontoOriginal_CLP": None},
    {"Saldo_CLP": 120}, {"EstadoCxC": "Pagada"},
])
def test_invalid_original_or_paid_with_open_balance_is_not_certified(updates):
    result = _ledger([_row(), _row(IDCxC="R2", IDVenta="V2", **updates)])
    assert result["saldo_validado"] == 60
    assert result["filas_validas"] == 1


def test_duplicates_are_disclosed_preserved_and_installments_are_not_merged():
    rows = [_row(), _row(), _row(IDCxC="R2", Saldo_CLP=20)]
    frame = pd.DataFrame(rows)
    original = frame.copy(deep=True)
    result = analyze_receivables({"CxC": frame}, {"v001"})
    assert result["saldo_declarado"] == 140
    assert result["saldo_validado"] == 80
    assert result["documentos_pendientes"] == 2
    assert result["duplicados_excluidos_analisis"] == 1
    pd.testing.assert_frame_equal(frame, original)


def test_problem_examples_preserve_original_excel_row_numbers():
    frame = pd.DataFrame([_row(), _row(IDCxC="R2", IDVenta="V2", Saldo_CLP=-5)])
    frame.attrs['source_rows'] = [8, 18]
    result = analyze_receivables({'CxC': frame}, {'v001', 'v2'})
    assert result['filas_excluidas'] == 1
    assert result['ejemplos_problemas'] == [{'hoja': 'CxC', 'fila': 18, 'motivo': 'Saldo invalido'}]


def test_conflicting_receivable_ids_never_pick_the_first_value():
    result = _ledger([_row(), _row(Saldo_CLP=70), _row(IDCxC="R2", IDVenta="V2", Saldo_CLP=20)])
    assert result["saldo_validado"] == 20
    assert result["ids_conflictivos"] == 1


def test_ids_trim_spaces_and_case_but_do_not_remove_leading_zeroes():
    result = _ledger([_row(IDVenta=" v001 "), _row(IDCxC="R2", IDVenta="V1", Saldo_CLP=20)])
    assert result["saldo_validado"] == 60
    assert result["filas_id_sin_venta_valida"] == 1


def test_all_invalid_and_no_reference_are_unavailable_not_zero():
    assert _ledger([_row(Saldo_CLP=-5)])["saldo_validado"] is None
    assert analyze_receivables({"CxC": pd.DataFrame([_row()])}, set())["saldo_validado"] is None
    assert analyze_receivables({"CxC": pd.DataFrame([_row()])}, None)["estado"] == "blocked"
    result = _ledger([_row(Saldo_CLP=0, EstadoCxC="Pagada")])
    assert result["saldo_validado"] == 0
    assert result["documentos_pendientes"] == 0


@pytest.mark.parametrize("filters", [
    {"date_from": "2026-01-01"}, {"date_to": "2026-02-01"},
    {"dimensional_filter": True},
])
def test_without_snapshot_or_segment_evidence_the_global_balance_is_not_a_substitute(filters):
    result = _ledger(**filters)
    assert result["estado"] == "blocked"
    assert result["saldo_validado"] is None
    assert result["saldo_declarado"] is None


def test_latest_snapshot_is_not_summed_with_prior_months_or_filtered_by_issue_date():
    result = _ledger([
        _row(FechaCorte="2026-01-31", Saldo_CLP=90),
        _row(FechaCorte="2026-02-28", Saldo_CLP=60),
        _row(FechaCorte="2026-03-31", Saldo_CLP=0, EstadoCxC="Pagada"),
    ], date_from="2026-02-01", date_to="2026-02")
    assert result["saldo_validado"] == 60
    assert result["saldo_vencido"] == 60
    assert result["fecha_corte"] == "2026-02-28"
    assert result["filas_fuente"] == 3
    assert result["filas_corte"] == 1


def test_overdue_boundary_and_missing_due_dates():
    result = _ledger([
        _row(FechaCorte="2026-02-01"),
        _row(IDCxC="R2", IDVenta="V2", Saldo_CLP=20, FechaCorte="2026-02-01", FechaVencimiento="2026-01-31"),
    ])
    assert result["saldo_vencido"] == 20
    assert _ledger([_row(EstadoCxC="Vencida")])["saldo_vencido"] == 60


def test_missing_due_dates_do_not_certify_zero_or_complete_overdue_totals():
    result = _ledger([_row(FechaCorte="2026-02-28", FechaVencimiento="error")])
    assert result["saldo_validado"] == 60
    assert result["saldo_vencido"] is None
    assert result["estado_vencimiento"] == "unavailable"
    result = _ledger([
        _row(FechaCorte="2026-02-28"),
        _row(IDCxC="R2", IDVenta="V2", Saldo_CLP=20, FechaCorte="2026-02-28", FechaVencimiento=None),
    ])
    assert result["saldo_vencido"] == 60
    assert result["estado_vencimiento"] == "partial"
    assert result["cuentas_sin_antiguedad_validable"] == 1


def test_invoice_issued_after_snapshot_is_not_backdated_into_the_balance():
    result = _ledger([_row(FechaCorte="2026-02-28", FechaEmision="2026-03-01")])
    assert result["saldo_validado"] is None
    assert result["filas_emision_posterior_corte"] == 1


def test_missing_and_impossible_cutoffs_stay_visible():
    result = _ledger([_row(FechaCorte="2026-02-30")])
    assert result["estado"] == "blocked"
    assert result["saldo_validado"] is None
    result = _ledger([_row(FechaCorte="2026-02-28"), _row(IDCxC="R2", FechaCorte="error")])
    assert result["estado"] == "partial"
    assert result["filas_corte_invalido"] == 1
    assert result["saldo_validado"] == 60


def test_currencies_are_not_relabelled_or_summed_across_ledgers():
    frame = pd.DataFrame([_row()]).rename(columns={"Saldo_CLP": "Saldo_UF", "MontoOriginal_CLP": "MontoOriginal_UF"})
    assert analyze_receivables({"CxC": frame}, {"v001"})["saldo_validado"] is None
    assert analyze_receivables({"CxC": frame}, {"v001"}, currency="UF")["saldo_validado"] == 60
    frame["Moneda"] = ["USD"]
    assert analyze_receivables({"CxC": frame}, {"v001"}, currency="UF")["estado"] == "blocked"


def test_business_profile_uses_the_ledger_without_expanding_sales_lines():
    frames = {
        "Ventas": pd.DataFrame({"IDVenta": ["V001", "V2"], "FechaVenta": ["2026-01-01"] * 2,
                                 "EstadoVenta": ["Pagada", "Anulada"], "IDCliente": ["C1", "C2"]}),
        "Detalle": pd.DataFrame({"IDVenta": ["V001", "V001", "V2"], "Linea": [1, 2, 1],
                                  "IDProducto": ["P1"] * 3, "Cantidad": [1] * 3,
                                  "PrecioUnitarioNeto_CLP": [100] * 3, "NetoLinea_CLP": [100] * 3}),
        "CxC": pd.DataFrame([_row(), _row(IDCxC="R2", IDVenta="V2", Saldo_CLP=20),
                             _row(IDCxC="R3", IDVenta="V001", Saldo_CLP=-5)]),
    }
    mappings = {name: resolve_mapping(list(frame.columns), None) for name, frame in frames.items()}
    result = analyze_business_workbook(frames, mappings, {})
    assert result["estado_resultados"]["ventas_observadas"] == 200
    assert result["operacion"]["cuentas_por_cobrar"] == 60
    assert result["operacion"]["cobrado_aplicado"] is None
    assert result["operacion"]["cartera_cxc"]["filas_id_sin_venta_valida"] == 1
    indicators = {row["id"]: row for c in result["catalogo_indicadores"]["categorias"] for row in c["indicadores"]}
    assert indicators["cuentas_por_cobrar"]["valor"] == 60
    assert indicators["cuentas_por_cobrar"]["estado"] == "partial"
    assert indicators["cuentas_por_cobrar"]["periodo_actual"] == {"desde": None, "hasta": None}
    assert "CxC" in result["alcance"]["hojas_utilizadas"]
    filtered = analyze_business_workbook(frames, mappings, {}, date_to="2026-01-31")
    assert filtered["operacion"]["cuentas_por_cobrar"] is None


def test_recognition_does_not_turn_customer_masters_or_payment_movements_into_receivables():
    assert is_receivable_sheet("CxC", pd.DataFrame([_row()]))
    assert not is_receivable_sheet("Clientes", pd.DataFrame({"IDCliente": ["C1"], "Saldo": [10]}))
    assert not is_receivable_sheet("Cobranzas", pd.DataFrame({"IDPago": ["P1"], "MontoPago": [10]}))
    assert classify_business_sheets({"CxC": pd.DataFrame([_row()])})["cuentas_por_cobrar"] == ["CxC"]
