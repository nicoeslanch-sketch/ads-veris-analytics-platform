"""Synthetic export comparison in fresh processes; no network or customer files."""

import argparse
import ast
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'api'))


def measure(args):
    import openpyxl
    import pandas as pd
    import psutil
    from app.routes import pipeline

    if args.mode == 'baseline':
        source = subprocess.check_output(['git', 'show', args.baseline + ':api/app/routes/pipeline.py'],
                                         cwd=ROOT, text=True, encoding='utf-8')
        node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == '_clean_download_sync')
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<baseline export>', 'exec'), pipeline.__dict__)
    frame = pd.DataFrame({
        'ID': [f'{i:08d}' for i in range(args.rows)],
        'Fecha': ['2026-10-18'] * args.rows,
        'Producto': [f'Producto {i % 100}' for i in range(args.rows)],
        **{f'Importe_{j}': [str(i * 10 + j) for i in range(args.rows)] for j in range(9)},
    })
    kinds = {c: 'numero' if c.startswith('Importe_') else 'texto' for c in frame}
    pipeline._analyze_cached = lambda *a, **kw: {'_df_limpio': frame, 'column_types': kinds}
    pipeline._build_export_audit = lambda *a: pd.DataFrame({'regla': ['sin_cambio']})
    pipeline._export_annotations = lambda *a: ({}, {}, [])
    process = psutil.Process()
    initial = peak = process.memory_info().rss
    stop = threading.Event()
    def sample():
        nonlocal peak
        while not stop.wait(.01):
            peak = max(peak, process.memory_info().rss)
    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    started = perf_counter()
    data, _, _ = pipeline._clean_download_sync('synthetic.csv', b'synthetic', {}, 'xlsx')
    elapsed = perf_counter() - started
    stop.set()
    thread.join()
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
    count = sum(1 for _ in wb['Datos_limpios'].values) - 1
    wb.close()
    assert count == args.rows
    print(json.dumps(dict(mode=args.mode, rows=count, columns=len(frame.columns), seconds=round(elapsed, 3),
                         peak_rss_mib=round(peak / 1048576, 2), added_rss_mib=round((peak-initial) / 1048576, 2),
                         output_bytes=len(data))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rows', type=int, default=20000)
    parser.add_argument('--baseline', default='629367548059004eeb2969b39ae32c877629394f')
    parser.add_argument('--mode', choices=['baseline', 'current'])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not 100 <= args.rows <= 100000:
        parser.error('rows must be between 100 and 100000')
    if args.mode:
        measure(args)
        return
    results = []
    for mode in ('baseline', 'current'):
        output = subprocess.check_output([sys.executable, __file__, '--mode', mode, '--rows', str(args.rows),
            '--baseline', args.baseline], cwd=ROOT, text=True, encoding='utf-8',
            env={**os.environ, 'SUPABASE_URL': '', 'SUPABASE_SERVICE_ROLE_KEY': ''})
        results.append(json.loads(output.strip().splitlines()[-1]))
    report = dict(scope='synthetic cached export only, fresh processes, same machine', results=results)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
