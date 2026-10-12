"""Exact regression oracle for the pre-optimization grouped-profit contract."""

import numpy as np
import pandas as pd
import pytest
from pandas.core.groupby.generic import DataFrameGroupBy

from app.engine.business import _canonical_labels, _group_profit
from app.engine.standardize import physical_missing_mask


def reference(frame, column, amount, cost, limit=15, normalize_labels=False):
    # Freeze the original Series/dropna/sum path, including integer promotion
    # from where(), stable ties and null coverage. Do not use groupby.sum here.
    if not column or column not in frame.columns:
        return []
    labels = frame[column].copy()
    labels = (_canonical_labels(labels, 'Sin clasificar') if normalize_labels
              else labels.mask(physical_missing_mask(labels), 'Sin clasificar'))
    grouped = pd.DataFrame({'nombre': labels.astype(str).str.strip().replace('', 'Sin clasificar'),
                           'ingresos': amount, 'costo': cost})
    grouped['pareada'] = grouped['ingresos'].notna() & grouped['costo'].notna()
    grouped['ingreso_pareado'] = grouped['ingresos'].where(grouped['pareada'])
    grouped['costo_pareado'] = grouped['costo'].where(grouped['pareada'])
    total_positive = float(grouped.loc[grouped['ingresos'] > 0, 'ingresos'].sum())
    rows = []
    for name, values in grouped.groupby('nombre', dropna=False):
        income = float(values['ingresos'].dropna().sum())
        positive_income = float(values.loc[values['ingresos'] > 0, 'ingresos'].dropna().sum())
        paired_income = float(values['ingreso_pareado'].dropna().sum())
        paired_cost = float(values['costo_pareado'].dropna().sum())
        paired_rows = int(values['pareada'].sum())
        profit = paired_income - paired_cost if paired_rows else None
        rows.append({
            'nombre': str(name) or 'Sin clasificar', 'ingresos': round(income, 2),
            'ingresos_positivos': round(positive_income, 2),
            'participacion_pct': round(float(values.loc[values['ingresos'] > 0, 'ingresos'].sum())
                                       / total_positive * 100, 2) if total_positive else None,
            'costo': round(paired_cost, 2) if paired_rows else None,
            'utilidad': round(profit, 2) if profit is not None else None,
            'margen_pct': round(profit / paired_income * 100, 2) if profit is not None and paired_income else None,
            'filas': len(values), 'filas_pareadas': paired_rows,
            'cobertura_costos_pct': round(paired_rows / max(len(values), 1) * 100, 1),
        })
    rows.sort(key=lambda row: row['ingresos'], reverse=True)
    return rows if limit is None else rows[:limit]


@pytest.mark.parametrize('seed', range(6))
@pytest.mark.parametrize('dtype', ['float64', 'float32', 'Float64', 'Float32', 'Int64', 'object'])
@pytest.mark.parametrize('normalize_labels', [False, True])
def test_grouped_profit_matches_reference_and_does_not_mutate(seed, dtype, normalize_labels):
    rng = np.random.default_rng(seed)
    index = pd.Index(rng.permutation(257) * 3 + 100)
    frame = pd.DataFrame({'grupo': rng.choice([' A ', 'a', 'B', '', None, 'null', 'NaT'], 257)}, index=index)
    amount = pd.Series(rng.integers(-10000, 10000, 257), index=index, dtype=dtype)
    cost = pd.Series(rng.integers(-5000, 5000, 257), index=index, dtype=dtype)
    amount.iloc[::7] = None
    cost.iloc[::3] = None
    if dtype not in ('Int64', 'object'):
        amount /= 100
        cost /= 100
    # Input series can arrive in a different index order after a relationship.
    amount = amount.iloc[::-1]
    before = frame.copy(deep=True), amount.copy(deep=True), cost.copy(deep=True)
    for limit in (None, 2, 0):
        expected = reference(frame, 'grupo', amount, cost, limit, normalize_labels)
        assert _group_profit(frame, 'grupo', amount, cost, limit, normalize_labels) == expected
    pd.testing.assert_frame_equal(frame, before[0])
    pd.testing.assert_series_equal(amount, before[1])
    pd.testing.assert_series_equal(cost, before[2])


@pytest.mark.parametrize('values,costs', [
    ([], []), ([None, None], [None, 1]), ([0, 0], [0, None]),
    ([-100, -20, 5], [-50, None, 2]),
    ([100, None, 100, 100], [40, 50, None, 60]),
    ([1e16, 0.005, -1e16, 0.005, 0.01] * 51, [0.01] * 255),
    ([2**53 + 1, 1, -2**53], [2, 2, 2]),
    ([2**62, 2**62, -1], [2, 2, 2]),
    ([2**53 + 1, 1, -2**53], [2, None, 2]),
])
def test_grouped_profit_preserves_nulls_returns_and_floating_point_order(values, costs):
    frame = pd.DataFrame({'grupo': ['A'] * len(values)})
    amount, cost = pd.Series(values), pd.Series(costs)
    assert _group_profit(frame, 'grupo', amount, cost) == reference(frame, 'grupo', amount, cost)


def test_grouped_profit_ties_and_duplicate_indexes_preserve_order():
    frame = pd.DataFrame({'grupo': ['Z', 'B', 'A', 'Z', 'B', 'A']}, index=[4, 4, 5, 5, 6, 6])
    amount = pd.Series([1, 2, 3, 5, 4, 3], index=frame.index)
    cost = pd.Series([0, 1, None, 1, 0, 3], index=frame.index)
    assert _group_profit(frame, 'grupo', amount, cost) == reference(frame, 'grupo', amount, cost)
    assert [row['nombre'] for row in _group_profit(frame, 'grupo', amount, cost, 2)] == ['A', 'B']


def test_grouped_profit_does_not_construct_a_dataframe_for_each_group(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Grouped calculation must use positions, not per-group DataFrames')
    monkeypatch.setattr(DataFrameGroupBy, '__iter__', forbidden)
    frame = pd.DataFrame({'grupo': [f'P{i}' for i in range(300)]})
    rows = _group_profit(frame, 'grupo', pd.Series([100] * 300), pd.Series([40] * 300), None)
    assert len(rows) == 300
    assert all(row['utilidad'] == 60 and row['cobertura_costos_pct'] == 100 for row in rows)
