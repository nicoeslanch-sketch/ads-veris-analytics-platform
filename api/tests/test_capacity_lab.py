"""Safety and independent-oracle checks; full stack runs only on manual CI."""

import csv
import importlib.util
import io
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('capacity_lab', Path(__file__).resolve().parents[2] / 'scripts/benchmark_durable_local.py')
lab = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lab)


@pytest.mark.parametrize('url', [
    'https://ads-veris-api.onrender.com', 'https://project.supabase.co',
    'http://localhost:54321', 'http://127.0.0.1.example.org', 'http://2130706433',
    'http://127.0.0.1?target=production', 'http://127.0.0.1#remote',
])
def test_lab_rejects_remote_or_ambiguous_targets(url):
    with pytest.raises(ValueError):
        lab.require_loopback_url(url)


def test_lab_allows_only_explicit_local_services():
    assert lab.require_loopback_url('http://127.0.0.1:54321').port == 54321
    assert lab.require_loopback_url('postgresql://postgres:local@127.0.0.1:54322/postgres', ('postgresql',)).port == 54322


def test_synthetic_oracle_matches_csv_and_accounts_are_distinct():
    one, totals = lab.synthetic_csv(4000, 0)
    two, other_totals = lab.synthetic_csv(4000, 1)
    rows = list(csv.DictReader(io.StringIO(one.decode())))
    assert len(rows) == 4000 and len({r['ID Venta'] for r in rows}) == 4000
    assert sum(totals.values()) == sum(int(r['Monto Venta']) for r in rows)
    assert sum(other_totals.values()) - sum(totals.values()) == 400000
    assert one != two
    for start in ('2026-01-01', '2026-02-12', '2026-02-28'):
        assert sum(v for day, v in totals.items() if day >= start) == sum(int(r['Monto Venta']) for r in rows if r['Fecha'] >= start)


def test_percentiles_use_nearest_rank_in_small_samples():
    assert lab.quantiles([]) == {'count': 0}
    assert lab.quantiles([1, 2, 3]) == {'count': 3, 'median': 2, 'p95': 3, 'max': 3}
