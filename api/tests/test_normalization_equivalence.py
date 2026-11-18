"""Optimization must preserve the former Unicode normalization contract."""
import unicodedata

from hypothesis import example, given, settings, strategies as st
import pytest

from app.engine.mapping import strip_accents_lower


def reference(value):
    normalized = unicodedata.normalize('NFKD', str(value))
    return ''.join(c for c in normalized if not unicodedata.combining(c)).lower().strip()


@settings(max_examples=500)
@given(st.text(max_size=300))
@example('  CATEGORÍA \u00a0 Ñandú  ')
@example(' A\x00B\t\r\n')
@example('ＶＥＮＴＡＳ ① ﬁ ²')
def test_unicode_matches_previous_normalizer(value):
    assert strip_accents_lower(value) == reference(value)


@settings(max_examples=500)
@given(st.text(alphabet=st.characters(max_codepoint=127), max_size=300))
def test_ascii_fast_path_matches_previous_normalizer(value):
    assert strip_accents_lower(value) == reference(value)


@pytest.mark.parametrize('value', [None, 0, -12.34, True, float('nan')])
def test_non_string_conversion_is_unchanged(value):
    assert strip_accents_lower(value) == reference(value)
