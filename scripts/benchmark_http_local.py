"""Bounded real-HTTP probe on an isolated loopback API, never production.

Measures responsiveness with two real synthetic CSV calculations in progress.
PostgreSQL, Storage, external authentication and durable workers are excluded.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import io
import json
import os
from pathlib import Path
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def serve(port):
    connect = socket.socket.connect
    def loopback_only(sock, address):
        if not isinstance(address, tuple) or address[0] not in {'127.0.0.1', '::1'}:
            raise RuntimeError('External connections prohibited in local benchmark')
        return connect(sock, address)
    socket.socket.connect = loopback_only
    sys.path.insert(0, str(ROOT / 'api'))
    import uvicorn
    uvicorn.run('app.main:app', host='127.0.0.1', port=port, log_level='warning')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--serve', type=int, help=argparse.SUPPRESS)
    parser.add_argument('--rows', type=int, default=4000)
    parser.add_argument('--clients', type=int, default=10)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.serve:
        serve(args.serve)
        return
    if not args.output or not 100 <= args.rows <= 10000 or not 1 <= args.clients <= 20:
        parser.error('Specify --output; use 100..10000 rows and 1..20 clients.')
    import httpx
    import jwt
    import psutil

    secret = uuid4().hex + uuid4().hex
    env = {**os.environ, 'APP_ENV': 'development', 'SUPABASE_URL': '', 'SUPABASE_SERVICE_ROLE_KEY': '',
           'SUPABASE_JWT_SECRET': secret, 'DEV_AUTH_BYPASS': 'false', 'PLAN_ENFORCEMENT': 'false',
           'ANALYSIS_DURABLE_MODE': 'off', 'ANALYSIS_REDIS_URL': '', 'ANTHROPIC_API_KEY': '',
           'AI_REFINE_ENABLED': 'false'}
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1', 0))
        port = reserved.getsockname()[1]
    output = {'scope': 'local HTTP responsiveness; two synthetic accounts; no production capacity certification',
              'clients': args.clients, 'rows_per_job': args.rows, 'jobs': [], 'samples': []}
    stop, peak = threading.Event(), [0]
    with tempfile.TemporaryFile() as logs:
        server = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--serve', str(port)],
            env=env, cwd=ROOT / 'api', stdout=logs, stderr=logs,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        process = psutil.Process(server.pid)
        def sample():
            while not stop.wait(0.02):
                try:
                    rss = sum(p.memory_info().rss for p in [process, *process.children(recursive=True)] if p.is_running())
                    peak[0] = max(peak[0], rss)
                except psutil.Error:
                    pass
        sampler = threading.Thread(target=sample, daemon=True)
        sampler.start()
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=30, trust_env=False) as client:
                deadline = time.monotonic() + 30
                while True:
                    if server.poll() is not None:
                        raise RuntimeError('Isolated API failed to start')
                    try:
                        response = client.get('/version')
                        if response.status_code == 200:
                            output['version'] = response.json()
                            break
                    except httpx.HTTPError:
                        pass
                    if time.monotonic() > deadline:
                        raise TimeoutError('Local API startup exceeded 30 seconds')
                    time.sleep(0.1)
                jobs = []
                for user_index in range(2):
                    token = jwt.encode({'sub': str(uuid4()), 'aud': 'authenticated',
                                        'exp': int(time.time()) + 600}, secret, algorithm='HS256')
                    headers = {'Authorization': f'Bearer {token}'}
                    csv_buffer = io.StringIO(newline='')
                    writer = csv.writer(csv_buffer)
                    writer.writerow(['ID Venta', 'Fecha', 'Producto', 'Canal', 'Cantidad', 'Monto Venta'])
                    expected = 0
                    for i in range(args.rows):
                        amount = 1000 + i % 300
                        expected += amount
                        writer.writerow([f'V{user_index}-{i}', f'2026-{i % 12 + 1:02}-{i % 28 + 1:02}',
                                         f'P{i % 300:04}', 'Web' if i % 2 else 'Local', 1, amount])
                    started = time.monotonic()
                    response = client.post('/analysis/jobs/metrics', headers=headers,
                                           files={'file': (f'synthetic-{user_index}.csv', csv_buffer.getvalue().encode(), 'text/csv')})
                    response.raise_for_status()
                    job = response.json()
                    jobs.append((job['job_id'], headers, expected, started))
                    output['jobs'].append({'admission_status': response.status_code,
                                           'admission_seconds': round(time.monotonic() - started, 4)})

                def probe(index):
                    job_id, headers, _expected, _started = jobs[index % 2]
                    path = ['/version', '/assistant/config', f'/analysis/jobs/{job_id}'][index % 3]
                    start = time.perf_counter()
                    response = client.get(path, headers=headers)
                    return {'route': path if index % 3 != 2 else '/analysis/jobs/:id',
                            'status': response.status_code, 'ms': round((time.perf_counter() - start) * 1000, 2)}
                with ThreadPoolExecutor(max_workers=args.clients) as executor:
                    output['samples'] = list(executor.map(probe, range(60)))
                assert all(row['status'] == 200 for row in output['samples']), output['samples']
                for index, (job_id, headers, expected, started) in enumerate(jobs):
                    while True:
                        response = client.get(f'/analysis/jobs/{job_id}', headers=headers)
                        response.raise_for_status()
                        job = response.json()
                        if job['status'] in {'completed', 'failed', 'cancelled'}:
                            break
                        if time.monotonic() - started > 180:
                            raise TimeoutError('Local job exceeded 180 seconds')
                        time.sleep(0.5)
                    assert job['status'] == 'completed', job.get('error')
                    assert job['result']['kpis']['ingresos_totales']['valor'] == expected
                    output['jobs'][index].update(status='completed', independent_total_matches=True,
                                                observed_seconds=round(time.monotonic() - started, 3))
                foreign = client.get(f'/analysis/jobs/{jobs[0][0]}', headers=jobs[1][1])
                output['foreign_job_status'] = foreign.status_code
                assert foreign.status_code == 404
        finally:
            stop.set()
            sampler.join()
            owned = [process, *process.children(recursive=True)] if process.is_running() else []
            for child in reversed(owned):
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
            _gone, alive = psutil.wait_procs(owned, timeout=10)
            for child in alive:
                child.kill()
            server.wait(timeout=10)
    values = sorted(row['ms'] for row in output['samples'])
    output.update(peak_api_process_tree_rss_mb=round(peak[0] / 1024**2, 2),
                  response_p95_ms=values[int(len(values) * 0.95) - 1], response_median_ms=statistics.median(values),
                  safety={'production_requests': 0, 'customer_files_read': 0, 'storage_uploads': 0})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in output.items() if key != 'samples'}), flush=True)


if __name__ == '__main__':
    main()
