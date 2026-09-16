"""Isolated full-stack capacity lab. Never accepts a remote target or real data.

Requires a fresh local Supabase stack and psql. Auth, RLS, quota reservations,
Storage and the durable queue are real; only input data and accounts are synthetic.
Results describe this runner, not a Render plan or a commercial user guarantee.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import io
import json
import math
import os
from pathlib import Path
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import unquote, urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {'completed', 'failed', 'cancelled'}


def require_loopback_url(value, schemes=('http',)):
    parsed = urlsplit(value)
    if parsed.scheme not in schemes or parsed.hostname not in {'127.0.0.1', '::1'}:
        raise ValueError('Only literal loopback targets are allowed')
    if parsed.query or parsed.fragment:
        raise ValueError('Target URLs cannot contain query parameters or fragments')
    return parsed


def block_external_connections():
    connect = socket.socket.connect

    def guarded(sock, address):
        if not isinstance(address, tuple) or address[0] not in {'127.0.0.1', '::1'}:
            raise RuntimeError('External connections prohibited in capacity lab')
        return connect(sock, address)

    socket.socket.connect = guarded


def quantiles(values):
    values = sorted(values)
    if not values:
        return {'count': 0}
    return {'count': len(values), 'median': round(statistics.median(values), 3),
            'p95': round(values[math.ceil(len(values) * .95) - 1], 3),
            'max': round(values[-1], 3)}


def synthetic_csv(rows, account):
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['ID Venta', 'Fecha', 'Producto', 'Canal', 'Cantidad', 'Monto Venta'])
    daily_totals = {}
    for i in range(rows):
        day = f'2026-{i % 12 + 1:02}-{i % 28 + 1:02}'
        amount = 1000 + account * 100 + i % 300
        writer.writerow([f'V{account}-{i}', day, f'P{i % 300:04}', 'Web' if i % 2 else 'Local', 1, amount])
        daily_totals[day] = daily_totals.get(day, 0) + amount
    return output.getvalue().encode(), daily_totals


def child_process(args):
    require_loopback_url(os.environ['SUPABASE_URL'])
    if os.environ.get('CAPACITY_LAB_ISOLATED') != '1':
        raise RuntimeError('Missing isolated-lab marker')
    block_external_connections()
    sys.path.insert(0, str(ROOT / 'api'))
    if args.serve:
        import uvicorn
        uvicorn.run('app.main:app', host='127.0.0.1', port=args.serve, log_level='warning')
    elif args.fault_marker:
        from app.analysis_worker import AnalysisWorker
        from app.config import get_settings

        def pause_after_real_claim(*_):
            # Controlled crash point: real lease acquired, heartbeat active, no
            # altered SQL or shortened expiry. Parent kills this owned process.
            args.fault_marker.touch()
            time.sleep(300)
            raise RuntimeError('Fault injection was not terminated')

        AnalysisWorker(get_settings(), execute=pause_after_real_claim).run()
    else:
        from app.analysis_worker import main
        main()


class Lab:
    def __init__(self, args):
        import httpx
        self.args = args
        self.status = json.loads(args.status_file.read_text(encoding='utf-8-sig'))
        self.base = self.status['API_URL'].rstrip('/')
        require_loopback_url(self.base)
        db = require_loopback_url(self.status['DB_URL'], ('postgresql', 'postgres'))
        self.pg_env = {**os.environ, 'PGHOST': db.hostname, 'PGPORT': str(db.port or 5432),
                       'PGUSER': unquote(db.username or ''), 'PGPASSWORD': unquote(db.password or ''),
                       'PGDATABASE': unquote(db.path.lstrip('/')), 'PGCONNECT_TIMEOUT': '5',
                       'PGOPTIONS': '-c statement_timeout=10000'}
        self.service = {'apikey': self.status['SERVICE_ROLE_KEY'],
                        'Authorization': 'Bearer ' + self.status['SERVICE_ROLE_KEY']}
        self.http = httpx.Client(timeout=30, trust_env=False)
        self.processes = []
        self.samples = []
        self.jobs = []
        self.peak = {}
        self.stop = threading.Event()
        self.report = {'scope': 'ephemeral local Supabase; not production capacity certification',
                       'parameters': {'accounts': args.clients, 'rows': args.rows, 'seconds': args.seconds},
                       'cpu_count': os.cpu_count(), 'checks': {}, 'passed': False,
                       'safety': {'production_requests': 0, 'customer_files_read': 0}}
        self.tmp = tempfile.TemporaryDirectory(prefix='ads-capacity-')
        self.env = {**os.environ, 'CAPACITY_LAB_ISOLATED': '1', 'APP_ENV': 'development',
                    'SUPABASE_URL': self.base, 'SUPABASE_SERVICE_ROLE_KEY': self.status['SERVICE_ROLE_KEY'],
                    'SUPABASE_JWT_SECRET': self.status['JWT_SECRET'], 'SUPABASE_STORAGE_BUCKET': 'datasets',
                    'DEV_AUTH_BYPASS': 'false', 'PLAN_ENFORCEMENT': 'true',
                    'ANALYSIS_DURABLE_MODE': 'external', 'ANALYSIS_WORKER_POLL_SECONDS': '1',
                    'ANALYSIS_REDIS_URL': '', 'ANTHROPIC_API_KEY': '', 'AI_REFINE_ENABLED': 'false',
                    'AI_CLASSIFIER_ENABLED': 'false', 'ADVANCED_AI_ENABLED': 'false',
                    'CONSOLIDATION_ENABLED': 'false', 'HTTP_PROXY': '', 'HTTPS_PROXY': '', 'ALL_PROXY': ''}

    def sql(self, query):
        result = subprocess.run(['psql', '-X', '-A', '-t', '-v', 'ON_ERROR_STOP=1', '-c', query],
                                env=self.pg_env, capture_output=True, text=True, timeout=15)
        if result.returncode:
            raise RuntimeError('Local database inspection failed')
        return json.loads(result.stdout.strip())

    def request(self, method, url, expected=200, **kwargs):
        response = self.http.request(method, url, **kwargs)
        if response.status_code != expected:
            # Never include request headers, tokens or response bodies in logs.
            raise RuntimeError(f'{method} {urlsplit(url).path}: expected {expected}, got {response.status_code}')
        return response

    def start(self, role, *extra):
        log = Path(self.tmp.name) / f'{role}-{len(self.processes)}.log'
        with log.open('wb') as output:
            process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), *extra],
                                       cwd=self.tmp.name, env={**self.env, 'PYTHONPATH': str(ROOT / 'api')},
                                       stdout=output, stderr=output,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        self.processes.append((role, process, log))
        return process

    def start_api(self):
        with socket.socket() as reserved:
            reserved.bind(('127.0.0.1', 0))
            port = reserved.getsockname()[1]
        self.api = f'http://127.0.0.1:{port}'
        process = self.start('api', '--serve', str(port))
        for _ in range(150):
            if process.poll() is not None:
                raise RuntimeError('Isolated API stopped during startup')
            try:
                response = self.http.get(self.api + '/version')
                if response.status_code == 200:
                    self.report['version'] = response.json()
                    assert response.json()['analysis_worker_mode'] == 'external'
                    return process
            except Exception:
                pass
            time.sleep(.2)
        raise TimeoutError('Isolated API startup exceeded 30 seconds')

    def sample_resources(self):
        import psutil
        while not self.stop.wait(.1):
            for role, process, _ in list(self.processes):
                if process.poll() is not None:
                    continue
                try:
                    rss = psutil.Process(process.pid).memory_info().rss / 1024**2
                    self.peak[role] = max(self.peak.get(role, 0), rss)
                except psutil.Error:
                    pass

    def seed_account(self, index):
        email, password = f'capacity-{uuid4().hex}@example.invalid', uuid4().hex + 'A!7'
        response = self.request('POST', self.base + '/auth/v1/admin/users', headers=self.service,
                                json={'email': email, 'password': password, 'email_confirm': True})
        user_id = response.json()['id']
        self.request('PATCH', self.base + '/rest/v1/profiles', expected=204, headers=self.service,
                     params={'id': f'eq.{user_id}'}, json={'plan': 'analista'})
        token = self.request('POST', self.base + '/auth/v1/token?grant_type=password',
                             headers={'apikey': self.status['ANON_KEY']},
                             json={'email': email, 'password': password}).json()['access_token']
        headers = {'Authorization': 'Bearer ' + token}
        body, totals = synthetic_csv(self.args.rows, index)
        path = self.request('POST', self.api + '/storage/upload', headers=headers,
                            files={'file': (f'synthetic-{index}.csv', body, 'text/csv')}).json()['storage_path']
        dataset_id = str(uuid4())
        self.request('POST', self.base + '/rest/v1/datasets', expected=201,
                     headers={**headers, 'apikey': self.status['ANON_KEY']},
                     json={'id': dataset_id, 'user_id': user_id, 'name': f'synthetic-{index}.csv',
                           'storage_path': path, 'source': 'excel_csv'})
        return {'headers': headers, 'dataset_id': dataset_id, 'storage_path': path, 'totals': totals}

    def submit(self, account, start_date, expected_status=202):
        begin = time.monotonic()
        response = self.request('POST', self.api + '/analysis/jobs/metrics', expected=expected_status,
                                headers=account['headers'], data={'dataset_id': account['dataset_id'],
                                'storage_path': account['storage_path'], 'date_from': start_date})
        self.samples.append({'route': 'admission', 'ms': (time.monotonic() - begin) * 1000,
                             'status': response.status_code})
        if expected_status != 202:
            return response
        job = response.json()
        assert job['job_id'].startswith('dq_')
        return {'id': job['job_id'], 'account': account, 'start': begin,
                'expected': sum(v for day, v in account['totals'].items() if day >= start_date)}

    def poll(self, job):
        start = time.monotonic()
        response = self.request('GET', self.api + '/analysis/jobs/' + job['id'], headers=job['account']['headers'])
        self.samples.append({'route': 'poll', 'ms': (time.monotonic() - start) * 1000,
                             'status': response.status_code})
        result = response.json()
        assert not {'source_path', 'options', 'lease_token', 'user_id'} & result.keys()
        return result

    def verify_result(self, job, result):
        assert result['status'] == 'completed', f"Job ended as {result['status']}: {result.get('error')}"
        assert result['result']['kpis']['ingresos_totales']['valor'] == job['expected'], 'Incorrect income total'

    def wait_result(self, job, timeout=240):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self.poll(job)
            if result['status'] in TERMINAL:
                self.verify_result(job, result)
                return result
            time.sleep(.5)
        raise TimeoutError('Bounded job deadline exceeded')

    def preflight(self):
        count = self.sql('select (select count(*) from auth.users) + '
                         '(select count(*) from public.datasets) + (select count(*) from storage.objects);')
        if count != 0:
            raise RuntimeError('Refusing to run: local database is not empty')
        self.report['queue_limits'] = self.sql('select row_to_json(l) from app_private.analysis_queue_limits l;')
        assert self.report['queue_limits']['max_running'] == 1
        api_process = self.start_api()
        self.accounts = [self.seed_account(i) for i in range(self.args.clients)]
        first = self.submit(self.accounts[0], '2026-01-01')
        duplicate = self.submit(self.accounts[0], '2026-01-01')
        assert first['id'] == duplicate['id']
        assert self.poll(first)['status'] == 'queued'
        # No worker yet: admission survives destruction of the serving process.
        api_process.terminate()
        api_process.wait(timeout=15)
        self.start_api()
        assert self.poll(first)['status'] == 'queued'
        path = self.api + '/analysis/jobs/' + first['id']
        self.request('GET', path, expected=401)
        self.request('GET', path, expected=404, headers=self.accounts[1]['headers'])
        for action in ('cancel', 'retry'):
            self.request('POST', path + '/' + action, expected=404, headers=self.accounts[1]['headers'])
        denied = self.http.post(self.base + '/rest/v1/rpc/analysis_queue',
                               headers={**self.accounts[0]['headers'], 'apikey': self.status['ANON_KEY']},
                               json={'p_action': 'claim'})
        assert denied.status_code in {401, 403, 404}
        queued = [self.submit(self.accounts[0], f'2026-01-0{i}') for i in (2, 3)]
        rejected = self.submit(self.accounts[0], '2026-01-04', expected_status=429)
        assert rejected.headers['retry-after'] == '10'
        for job in queued:
            cancelled = self.request('POST', self.api + '/analysis/jobs/' + job['id'] + '/cancel',
                                     headers=job['account']['headers']).json()
            assert cancelled['status'] == 'cancelled'
        self.report['checks'].update(idempotency=True, api_restart_preserves_queue=True,
                                     unauthenticated_rejected=True, cross_account_isolation=True,
                                     private_rpc_denied=True, per_account_admission_limit=True,
                                     queued_cancellation=True)
        return first

    def recovery(self, job):
        marker = Path(self.tmp.name) / 'claimed'
        faulty = self.start('fault_worker', '--worker', '--fault-marker', str(marker))
        deadline = time.monotonic() + 30
        while not marker.exists():
            if faulty.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Fault worker did not acquire a real lease')
            time.sleep(.1)
        assert self.poll(job)['status'] == 'running'
        faulty.kill()
        faulty.wait(timeout=10)
        killed = time.monotonic()
        self.start('worker', '--worker')
        # Actual 120-second lease expiry, no database timestamp mutation.
        result = self.wait_result(job, timeout=210)
        assert result['attempt'] == 2
        self.report['recovery'] = {'seconds_after_kill': round(time.monotonic() - killed, 3),
                                    'attempts': result['attempt'], 'correct_total': True}
        self.report['checks']['worker_crash_recovers_without_lost_job'] = True

    def sustained(self):
        start = time.monotonic()
        # Two consumers must still respect the one-running-job database limit.
        self.start('worker', '--worker')
        in_flight, completed, sequences = {}, [], [0] * len(self.accounts)
        max_running, submitted = 0, 0
        next_submit = [start] * len(self.accounts)
        with ThreadPoolExecutor(max_workers=len(self.accounts)) as executor:
            while time.monotonic() - start < self.args.seconds or in_flight:
                now = time.monotonic()
                if now - start > self.args.seconds + 180:
                    raise TimeoutError('Queue did not drain within 180 seconds')
                for i, account in enumerate(self.accounts):
                    if i not in in_flight and now >= next_submit[i] and now - start < self.args.seconds and submitted < 40:
                        sequences[i] += 1
                        day = f'2026-02-{sequences[i]:02}'
                        in_flight[i] = self.submit(account, day)
                        submitted += 1
                        next_submit[i] = now + 10
                indices = list(in_flight)
                responses = executor.map(self.poll, [in_flight[i] for i in indices])
                for i, result in zip(indices, responses):
                    if result['status'] in TERMINAL:
                        job = in_flight.pop(i)
                        self.verify_result(job, result)
                        completed.append({'id': job['id'], 'observed_seconds': round(time.monotonic() - job['start'], 3)})
                running = self.sql("select count(*) from app_private.analysis_queue_jobs where status='running';")
                max_running = max(max_running, running)
                assert running <= 1, 'Global concurrency limit violated'
                time.sleep(.5)
        elapsed = time.monotonic() - start
        assert len(completed) == submitted and submitted >= len(self.accounts)
        ids = {job['id'] for job in completed}
        records = self.sql("select coalesce(json_agg(json_build_object('id',job_id,"
                           "'wait',extract(epoch from started_at-created_at),"
                           "'processing',extract(epoch from updated_at-started_at))), '[]'::json) "
                           "from app_private.analysis_queue_jobs where status='completed';")
        records = [row for row in records if row['id'] in ids]
        assert len(records) == submitted
        self.report['sustained'] = {'submitted': submitted, 'completed': len(completed),
                                    'elapsed_seconds': round(elapsed, 3), 'observed_max_running': max_running,
                                    'jobs_per_minute': round(len(completed) / elapsed * 60, 3),
                                    'queue_wait_seconds': quantiles([row['wait'] for row in records]),
                                    'processing_seconds': quantiles([row['processing'] for row in records]),
                                    'end_to_end_seconds': quantiles([row['observed_seconds'] for row in completed]),
                                    'offered_load': 'closed loop, one outstanding/account, >=10s between starts, max 40 jobs'}
        self.report['checks'].update(all_synthetic_totals_match=True, two_consumers_respect_global_limit=True)

    def run(self):
        sampler = threading.Thread(target=self.sample_resources, daemon=True)
        sampler.start()
        try:
            first = self.preflight()
            print('Preflight passed; testing actual lease recovery (about two minutes).', flush=True)
            self.recovery(first)
            print('Crash recovery passed; starting bounded sustained workload.', flush=True)
            self.sustained()
            self.report['passed'] = True
        except Exception as exc:
            self.report['failure'] = {'type': type(exc).__name__, 'message': str(exc)[:300]}
            raise
        finally:
            self.stop.set()
            sampler.join(timeout=5)
            for _, process, _ in self.processes:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=10)
            self.report['peak_process_rss_mib'] = {k: round(v, 2) for k, v in self.peak.items()}
            self.report['http_ms'] = {route: quantiles([s['ms'] for s in self.samples if s['route'] == route])
                                       for route in ('admission', 'poll')}
            self.report['http_status_counts'] = {str(status): sum(s['status'] == status for s in self.samples)
                                                 for status in {s['status'] for s in self.samples}}
            self.args.output.parent.mkdir(parents=True, exist_ok=True)
            self.args.output.write_text(json.dumps(self.report, indent=2), encoding='utf-8')
            self.http.close()
            self.tmp.cleanup()
            print(json.dumps(self.report, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--status-file', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--clients', type=int, default=5)
    parser.add_argument('--rows', type=int, default=4000)
    parser.add_argument('--seconds', type=int, default=120)
    parser.add_argument('--serve', type=int, help=argparse.SUPPRESS)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--fault-marker', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.serve or args.worker:
        child_process(args)
        return
    if not args.status_file or not args.output or not 2 <= args.clients <= 10 or not 100 <= args.rows <= 10000 or not 60 <= args.seconds <= 300:
        parser.error('Require --status-file, --output; clients 2..10, rows 100..10000, seconds 60..300')
    block_external_connections()
    Lab(args).run()


if __name__ == '__main__':
    main()
