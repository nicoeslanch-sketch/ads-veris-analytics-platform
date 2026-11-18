import pandas as pd
import pytest
from hypothesis import given, settings, strategies as st

from app.engine.business import _keys, _text_key


@settings(max_examples=300, deadline=None)
@given(st.lists(st.one_of(st.text(max_size=35), st.none()), max_size=60))
def test_repeated_text_keys_match_original_scalar_mapping(values):
    source = pd.Series(values * 4, dtype=object, name='ID')
    original = source.copy(deep=True)
    pd.testing.assert_series_equal(_keys(source), source.map(_text_key))
    pd.testing.assert_series_equal(source, original)


@pytest.mark.parametrize('dtype', ['object', 'string'])
def test_nullable_text_and_normalized_collisions_preserve_original_result(dtype):
    source = pd.Series(['P001', 'p1', '  P001 ', None, pd.NA, float('nan'),
                        '', '2026/1', '2026-01', 'CAF\u00c9', 'cafe'] * 10, dtype=dtype)
    pd.testing.assert_series_equal(_keys(source), source.map(_text_key))


def test_mixed_numeric_boolean_ids_do_not_collapse():
    source = pd.Series([1, 1.0, True, False, 0, '1', None] * 20, dtype=object)
    pd.testing.assert_series_equal(_keys(source), source.map(_text_key))


def test_repeated_string_keys_parse_once_per_unique_value(monkeypatch):
    from app.engine import business
    calls = []
    def counted(value):
        calls.append(value)
        return _text_key(value)
    monkeypatch.setattr(business, '_text_key', counted)
    result = _keys(pd.Series(['P001', 'P002'] * 1000))
    assert result.tolist() == ['p1', 'p2'] * 1000
    assert calls == ['P001', 'P002']
