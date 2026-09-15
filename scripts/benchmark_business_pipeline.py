"""Profile the real business-summary path with synthetic, already-clean frames.

No workbook files, credentials, uploads or external requests are used. The JSON
receipt separates CPU/RAM measurements from a production concurrency promise.
"""

from __future__ import annotations

import argparse
import cProfile
import hashlib
import json
import os
from pathlib import Path
import platform
import pstats
import socket
import statistics
import sys
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))


def synthetic_frames(rows):
    import pandas as pd

    frames, mappings, expected_income, expected_cost = {}, {}, 0, 0
    for year in (2024, 2025, 2026):
        records = []
        for i in range(rows):
            sku, quantity = i % 300, i % 5 + 1
            amount, cost = quantity * (1000 + sku), quantity * (100 + sku)
            expected_income += amount
            expected_cost += cost
            records.append({
                "ID Venta": f"V{year}-{i:07}", "Fecha": pd.Timestamp(year, i % 12 + 1, i % 28 + 1),
                "SKU Producto": f"P{sku:04}", "ID Cliente": f"C{i % 800:04}",
                "Canal": "Web" if i % 2 else "Local", "Cantidad": quantity,
                "Monto Venta": amount, "Estado": "Vigente",
            })
        name = f"Ventas_{year}"
        frames[name] = pd.DataFrame(records)
        mappings[name] = {"fecha": "Fecha", "monto": "Monto Venta", "producto": "SKU Producto",
                          "cantidad": "Cantidad", "cliente": "ID Cliente", "canal": "Canal"}
    frames['Costos_Productos'] = pd.DataFrame({
        'SKU Producto': [f'P{i:04}' for i in range(300)],
        'Costo Unitario': [100 + i for i in range(300)],
    })
    mappings['Costos_Productos'] = {'producto': 'SKU Producto', 'costo': 'Costo Unitario'}
    results = {name: {'resumen': {'calidad_despues': 100}, 'problemas': {}, 'correcciones': {}, 'avisos': []}
               for name in frames}
    return frames, mappings, results, expected_income, expected_cost


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rows-per-sheet', type=int, default=4000)
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compare', type=Path)
    args = parser.parse_args()
    if not 100 <= args.rows_per_sheet <= 10000 or not 1 <= args.runs <= 5:
        parser.error('Use 100..10000 rows per sheet and 1..5 runs.')
    for name in ('SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY', 'SUPABASE_JWT_SECRET',
                 'ANALYSIS_REDIS_URL', 'ANTHROPIC_API_KEY'):
        os.environ[name] = ''
    os.environ.update(APP_ENV='development', DEV_AUTH_BYPASS='false', AI_REFINE_ENABLED='false')
    from app.routes import pipeline
    from app.engine.multi_sheet import validate_analysis_scope
    import psutil

    frames, mappings, results, income, cost = synthetic_frames(args.rows_per_sheet)
    scope = validate_analysis_scope({
        'mode': 'append_join', 'sheets': list(frames), 'append_sheets': list(frames)[:3],
        'active_sheet': 'Ventas_2024', 'join': {'left_sheet': 'Ventas_2024',
        'right_sheet': 'Costos_Productos', 'left_keys': ['SKU Producto'],
        'right_keys': ['SKU Producto'], 'type': 'left'},
    }, list(frames))
    process, stopped = psutil.Process(), threading.Event()
    peak = [process.memory_info().rss]
    def sample():
        while not stopped.wait(0.02):
            peak[0] = max(peak[0], process.memory_info().rss)
    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    receipt = {'scope': 'local synthetic business computation only; excludes XLSX parsing, cleaning, HTTP and storage',
               'rows': args.rows_per_sheet * 3, 'sheets': len(frames), 'python': platform.python_version(),
               'logical_cpus': os.cpu_count(), 'baseline_rss_mb': round(peak[0] / 1024**2, 2), 'runs': []}
    try:
        with patch.object(socket.socket, 'connect', side_effect=AssertionError('Network prohibited')):
            for _ in range(args.runs):
                with patch.object(pipeline, 'analyze_business_workbook', wraps=pipeline.analyze_business_workbook) as calls:
                    start = time.perf_counter()
                    computed = pipeline._metrics_multi_from_processed('synthetic', frames, mappings, results, scope, None, None)
                    elapsed = time.perf_counter() - start
                    digest = hashlib.sha256(json.dumps(computed, sort_keys=True, ensure_ascii=True, default=str,
                                                       allow_nan=False).encode()).hexdigest()
                    checks = {
                        'rows_preserved': computed['analysis_provenance']['rows'] == args.rows_per_sheet * 3,
                        'income_matches_independent_sum': computed['kpis']['ingresos_totales']['valor'] == income,
                        'business_income_matches': computed['analisis_negocio']['estado_resultados']['ventas_brutas'] == income,
                        'cost_matches_independent_sum': computed['analisis_negocio']['estado_resultados']['costo_venta_conocido'] == cost,
                    }
                    assert all(checks.values()), checks
                    receipt['runs'].append({'seconds': round(elapsed, 4), 'business_calls': calls.call_count,
                                            'result_sha256': digest, 'checks': checks})
                    print(json.dumps(receipt['runs'][-1]), flush=True)
            # Keep the sampler's timer waits out of the deterministic profile.
            stopped.set()
            sampler.join()
            profiler = cProfile.Profile()
            profiler.runcall(pipeline._metrics_multi_from_processed, 'synthetic', frames, mappings, results, scope, None, None)
            stats = pstats.Stats(profiler)
            receipt['profile_top'] = [
                {'function': f'{Path(path).name}:{line}:{name}', 'calls': count, 'cumulative_seconds': round(cumulative, 4)}
                for (path, line, name), (_primitive, count, _self, cumulative, _callers) in
                sorted(stats.stats.items(), key=lambda item: item[1][3], reverse=True)[:20]
            ]
    finally:
        stopped.set()
        sampler.join()
    receipt['median_seconds'] = statistics.median(row['seconds'] for row in receipt['runs'])
    receipt['peak_rss_mb'] = round(peak[0] / 1024**2, 2)
    receipt['independent_totals'] = {'income': income, 'cost': cost}
    receipt['safety'] = {'production_requests': 0, 'uploaded_files': 0, 'customer_files_read': 0}
    if args.compare:
        baseline = json.loads(args.compare.read_text(encoding='utf-8'))
        assert baseline['rows'] == receipt['rows']
        receipt['all_outputs_unchanged'] = all(row['result_sha256'] == baseline['runs'][0]['result_sha256'] for row in receipt['runs'])
        assert receipt['all_outputs_unchanged']
        receipt['median_reduction_pct'] = round((1 - receipt['median_seconds'] / baseline['median_seconds']) * 100, 1)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in receipt.items() if key not in {'runs', 'profile_top'}}), flush=True)


if __name__ == '__main__':
    main()
