"""Bounded public smoke check. No customer data or production credentials."""

import argparse
import json
import os
import time
from urllib.request import HTTPRedirectHandler, Request, build_opener


REPOSITORY = 'nicoeslanch-sketch/ads-veris-analytics-platform'
ENDPOINTS = {
    'web': 'https://ads-veris-analytics-platform-pi.vercel.app/',
    'api': 'https://ads-veris-api.onrender.com/health',
}
MARKER = '<!-- ads-veris-public-availability-v1 -->'
TITLE = 'Disponibilidad publica: comprobacion fallida'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def probe(name):
    try:
        request = Request(ENDPOINTS[name], headers={'User-Agent': 'ADS-Veris-availability/1'})
        with build_opener(NoRedirect()).open(request, timeout=20) as response:
            body = response.read(512 * 1024).decode('utf-8', errors='replace')
            if response.status != 200:
                return False
            if name == 'api':
                result = json.loads(body)
                return isinstance(result, dict) and result.get('status') == 'ok' and result.get('service') == 'ads-veris-data-engine'
            return 'id="root"' in body and '/assets/' in body and '<script' in body
    except Exception:
        return False


def check(probe_fn=probe, sleep=time.sleep):
    pending = set(ENDPOINTS)
    for attempt in range(3):
        pending = {name for name in sorted(pending) if not probe_fn(name)}
        if not pending:
            break
        if attempt < 2:
            sleep(30)
    return sorted(pending)


def github(method, path, data=None):
    if os.environ.get('GITHUB_REPOSITORY') != REPOSITORY:
        raise RuntimeError('Unexpected monitoring repository')
    token = os.environ['GH_TOKEN']
    request = Request('https://api.github.com/repos/' + REPOSITORY + path,
                      data=json.dumps(data).encode() if data is not None else None,
                      method=method, headers={'Authorization': 'Bearer ' + token,
                      'Accept': 'application/vnd.github+json', 'Content-Type': 'application/json',
                      'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'ADS-Veris-availability/1'})
    with build_opener(NoRedirect()).open(request, timeout=20) as response:
        return json.load(response)


def reconcile(failed, api=github):
    active = []
    for page in range(1, 11):
        issues = api('GET', f'/issues?state=open&per_page=100&page={page}')
        active.extend(item for item in issues if not item.get('pull_request')
                      and item.get('user', {}).get('login') == 'github-actions[bot]'
                      and MARKER in (item.get('body') or ''))
        if len(issues) < 100:
            break
    else:
        raise RuntimeError('Monitoring issue listing exceeded limit')
    if failed:
        body = (MARKER + '\nTres comprobaciones consecutivas fallaron para: '
                + ', '.join(failed) + '.\nSolo se consultaron direcciones publicas, sin datos de clientes.'
                + '\nRevisar Render/Vercel y el workflow Public availability.'
                + '\nEsta incidencia se cierra automaticamente al recuperar ambas respuestas.')
        if not active:
            api('POST', '/issues', {'title': TITLE, 'body': body})
        else:
            for issue in active:
                if issue['body'] != body:
                    api('PATCH', f"/issues/{issue['number']}", {'body': body})
    else:
        for issue in active:
            api('PATCH', f"/issues/{issue['number']}", {'state': 'closed', 'state_reason': 'completed'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--notify', action='store_true')
    args = parser.parse_args()
    failed = check()
    print(json.dumps({'healthy': not failed, 'failed_public_services': failed}))
    if args.notify:
        try:
            reconcile(failed)
        except Exception:
            raise SystemExit('Availability notification could not be updated') from None
    raise SystemExit(1 if failed else 0)
