import importlib.util
from pathlib import Path


spec = importlib.util.spec_from_file_location('availability', Path(__file__).resolve().parents[2] / 'scripts/check_public_availability.py')
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


def test_retries_only_failed_endpoints():
    calls, sleeps = [], []
    def probe(name):
        calls.append(name)
        return name == 'web' or calls.count('api') == 3
    assert monitor.check(probe, sleeps.append) == []
    assert calls.count('web') == 1 and calls.count('api') == 3
    assert sleeps == [30, 30]


def test_failure_is_bounded():
    calls = []
    assert monitor.check(lambda name: calls.append(name), lambda _: None) == ['api', 'web']
    assert len(calls) == 6


def test_incidents_only_change_on_failure_transition():
    calls, issues = [], []
    def api(method, path, data=None):
        calls.append((method, path, data))
        return issues
    monitor.reconcile([], api)
    assert len(calls) == 1
    monitor.reconcile(['api'], api)
    body = calls[-1][2]['body']
    assert calls[-1][0] == 'POST' and 'api' in body
    issues.append({'number': 42, 'body': body, 'user': {'login': 'github-actions[bot]'}})
    calls.clear()
    monitor.reconcile(['api'], api)
    assert len(calls) == 1
    monitor.reconcile([], api)
    assert calls[-1] == ('PATCH', '/issues/42', {'state': 'closed', 'state_reason': 'completed'})


def test_does_not_close_human_issues_or_pull_requests():
    calls = []
    issues = [{'number': 1, 'body': monitor.MARKER, 'user': {'login': 'customer'}},
              {'number': 2, 'body': monitor.MARKER, 'user': {'login': 'github-actions[bot]'}, 'pull_request': {'url': 'example'}}]
    def api(method, path, data=None):
        calls.append(method)
        return issues
    monitor.reconcile([], api)
    assert calls == ['GET']
