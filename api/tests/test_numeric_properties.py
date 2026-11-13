"""Generated invariants for numeric normalization and safe spreadsheet exports."""

import math

from hypothesis import example, given, settings, strategies as st

from app.engine.export import neutralize_excel_formula
from app.engine.standardize import format_number, parse_number
from app.engine.quality import numeric_series
import pandas as pd


@settings(max_examples=250, deadline=None)
@given(st.floats(allow_nan=False, allow_infinity=False, width=64))
@example(1.234)
@example(-0.001)
def test_canonical_numeric_roundtrip_preserves_finite_value(value):
    result = parse_number(format_number(value), dot3_convention="decimal")
    assert result == value


@settings(max_examples=150, deadline=None)
@given(st.floats(min_value=-1e12, max_value=1e12, allow_nan=False, allow_infinity=False))
@example(0.004)
@example(1.239)
def test_native_numeric_values_keep_their_scale_without_locale_inference(value):
    assert parse_number(value) == value
    assert numeric_series(pd.DataFrame({"Saldo": [value]}), "Saldo").iloc[0] == value


def test_native_and_localized_text_numbers_remain_distinct_in_mixed_columns():
    values = pd.DataFrame({"Saldo": [1.239, "1.239", "1,239", "1.239", True]})
    result = numeric_series(values, "Saldo")
    assert result.iloc[:4].tolist() == [1.239, 1239, 1.239, 1239]
    assert pd.isna(result.iloc[4])


def test_repeated_booleans_never_share_numeric_cache_entries():
    for values in ([1, True, 0, False], [True, 1, False, 0]):
        frame = pd.DataFrame({"Saldo": values * 5})
        result = numeric_series(frame, "Saldo")
        for value, parsed in zip(values * 5, result):
            assert pd.isna(parsed) if isinstance(value, bool) else parsed == value
    assert numeric_series(pd.DataFrame({"Saldo": [True, False]}), "Saldo").isna().all()


@settings(max_examples=250, deadline=None)
@given(st.integers(-999999, 999999), st.integers(-400, 400))
@example(1, 309)
def test_numeric_parser_never_publishes_infinite_values(mantissa, exponent):
    result = parse_number(f"{mantissa}e{exponent}")
    assert result is None or math.isfinite(result)


@settings(max_examples=250, deadline=None)
@given(st.text(max_size=100))
@example("\t=HYPERLINK(\"https://invalid.example\")")
@example("-12.990")
def test_export_formula_protection_is_idempotent_and_preserves_literal_text(value):
    safe = neutralize_excel_formula(value)
    assert neutralize_excel_formula(safe) == safe
    if value.lstrip().startswith(("=", "+", "-", "@")):
        assert safe == "'" + value
    else:
        assert safe == value
