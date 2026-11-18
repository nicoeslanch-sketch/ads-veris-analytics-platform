"""Offline cold/warm preparation benchmark; receipts contain no cell values."""

import argparse
import cProfile
import hashlib
import json
import os
from pathlib import Path
import pstats
import socket
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'api'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('workbook', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compare', type=Path)
    parser.add_argument('--profile', action='store_true')
    args = parser.parse_args()
    for name in ('SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY', 'SUPABASE_JWT_SECRET',
                 'ANALYSIS_REDIS_URL', 'ANTHROPIC_API_KEY', 'OPENAI_API_KEY'):
        os.environ[name] = ''
    os.environ.update(APP_ENV='development', DEV_AUTH_BYPASS='false', AI_REFINE_ENABLED='false')
    from app.engine.loader import xlsx_sheet_names
    from app.routes import pipeline
    import psutil

    content = args.workbook.read_bytes()
    receipt = {'scope': 'local workbook reading and cleaning; no HTTP/storage or commercial SLA',
               'source_sha256': hashlib.sha256(content).hexdigest(), 'runs': []}
    profiler = cProfile.Profile()
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('Network prohibited')):
        for label in ('cold', 'warm'):
            if args.profile and label == 'cold':
                profiler.enable()
            started = time.perf_counter()
            loaded, _ = pipeline._load_batch_frames_cached(args.workbook.name, content, xlsx_sheet_names(content))
            loaded_at = time.perf_counter()
            profiles = next(iter(loaded.values()))[1]['clasificacion_hojas']
            manifest = pipeline._parse_sheet_manifest(json.dumps({'hojas': [
                {'nombre': row['nombre'], 'procesar': row['clasificacion'] == 'datos',
                 'mapping': {}, 'rules': {}, 'eliminar_duplicados': False} for row in profiles]}))
            frames, mappings, results = pipeline._processed_manifest_frames(args.workbook.name, content, manifest)
            finished = time.perf_counter()
            if args.profile and label == 'cold':
                profiler.disable()
            digest = hashlib.sha256()
            for name, frame in frames.items():
                digest.update(name.encode())
                digest.update(frame.to_json(orient='split', date_format='iso', double_precision=15).encode())
                digest.update(json.dumps({'mapping': mappings[name], 'summary': results[name]['resumen']},
                                         sort_keys=True, default=str).encode())
            run = {'mode': label, 'read_seconds': round(loaded_at - started, 4),
                   'prepare_seconds': round(finished - loaded_at, 4),
                   'total_seconds': round(finished - started, 4), 'sheets': len(frames),
                   'rows': sum(len(frame) for frame in frames.values()),
                   'rss_mb': round(psutil.Process().memory_info().rss / 1024**2, 2),
                   'result_sha256': digest.hexdigest()}
            receipt['runs'].append(run)
            print(json.dumps(run), flush=True)
    assert receipt['runs'][0]['result_sha256'] == receipt['runs'][1]['result_sha256']
    if args.profile:
        receipt['profile_top'] = [
            {'function': f'{Path(path).name}:{line}:{name}', 'calls': count,
             'self_seconds': round(own, 4), 'cumulative_seconds': round(cumulative, 4)}
            for (path, line, name), (_, count, own, cumulative, _) in
            sorted(pstats.Stats(profiler).stats.items(), key=lambda item: item[1][3], reverse=True)[:40]]
    if args.compare:
        baseline = json.loads(args.compare.read_text(encoding='utf-8'))
        assert baseline['source_sha256'] == receipt['source_sha256']
        assert baseline['runs'][0]['result_sha256'] == receipt['runs'][0]['result_sha256']
        receipt['baseline_results_identical'] = True
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
