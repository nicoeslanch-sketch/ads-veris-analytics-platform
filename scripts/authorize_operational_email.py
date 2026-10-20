"""Owner-only Gmail send authorization using Google's OAuth library.

Requires scripts/requirements-mail-setup.txt, not a production API dependency.
The operator supplies a private directory outside the repository containing
client.json. On Windows restrict its ACL to the current owner before use.
Only the owner completes Google's consent page. No messages are read or sent.
"""

import argparse
import json
import logging
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SCOPE = 'https://www.googleapis.com/auth/gmail.send'


def client_configuration(document):
    client = document.get('installed') if isinstance(document, dict) else None
    if not isinstance(client, dict):
        raise ValueError('A desktop OAuth client is required')
    client_id, secret = client.get('client_id'), client.get('client_secret')
    if not isinstance(client_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+\.apps\.googleusercontent\.com', client_id):
        raise ValueError('Invalid OAuth client')
    if not isinstance(secret, str) or not secret.strip():
        raise ValueError('Missing OAuth client secret')
    # Never trust endpoints supplied by a downloaded configuration file.
    return {'installed': {'client_id': client_id, 'client_secret': secret,
                          'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                          'token_uri': 'https://oauth2.googleapis.com/token',
                          'redirect_uris': ['http://localhost']}}


def write_private(path, text):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as output:
        output.write(text)


def authorize(directory, mailbox, wait_seconds=1800):
    if not 60 <= wait_seconds <= 3600:
        raise ValueError('Authorization window must be between 60 and 3600 seconds')
    directory = directory.resolve(strict=True)
    if directory.is_relative_to(ROOT) or not directory.is_dir():
        raise ValueError('Use a private directory outside the repository')
    if os.name != 'nt' and directory.stat().st_mode & 0o077:
        raise ValueError('Private directory must have owner-only permissions')
    if not re.fullmatch(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}', mailbox):
        raise ValueError('Invalid mailbox')
    link_path, result_path = directory / 'authorization-url.txt', directory / 'render-email.json'
    if link_path.exists() or result_path.exists():
        raise ValueError('Setup output already exists; do not overwrite credentials')
    config = client_configuration(json.loads((directory / 'client.json').read_text(encoding='utf-8-sig')))

    from google_auth_oauthlib.flow import InstalledAppFlow

    class OwnerFlow(InstalledAppFlow):
        def authorization_url(self, **kwargs):
            url, state = super().authorization_url(**kwargs)
            write_private(link_path, url)
            print('Authorization link prepared; owner consent required.', flush=True)
            return url, state

        def fetch_token(self, **kwargs):
            return super().fetch_token(timeout=20, **kwargs)

    flow = OwnerFlow.from_client_config(config, scopes=[SCOPE], autogenerate_code_verifier=True)
    flow.oauth2session.trust_env = False
    flow.oauth2session.max_redirects = 0
    credentials = flow.run_local_server(
        host='127.0.0.1', bind_addr='127.0.0.1', port=0, open_browser=False,
        authorization_prompt_message='', timeout_seconds=wait_seconds,
        success_message='Consentimiento recibido. ADS Veris comprobara la autorizacion. Puedes cerrar esta pestana.',
        prompt='consent', include_granted_scopes='false', login_hint=mailbox,
    )
    granted = credentials.granted_scopes or credentials.scopes
    if set(granted or []) != {SCOPE} or not credentials.refresh_token:
        raise ValueError('Send-only offline authorization was not granted')
    write_private(result_path, json.dumps({
        'OPERATIONS_EMAIL_TO': mailbox, 'OPERATIONS_EMAIL_FROM': mailbox,
        'OPERATIONS_GMAIL_CLIENT_ID': config['installed']['client_id'],
        'OPERATIONS_GMAIL_CLIENT_SECRET': config['installed']['client_secret'],
        'OPERATIONS_GMAIL_REFRESH_TOKEN': credentials.refresh_token,
    }))
    print('Send-only authorization stored privately. No email sent.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-directory', required=True, type=Path)
    parser.add_argument('--mailbox', default='servicios@adsveris.com')
    parser.add_argument('--wait-seconds', type=int, default=1800,
                        help='Owner consent window, 60-3600 seconds (default: 1800).')
    parser.add_argument('--authorize', required=True, action='store_true')
    args = parser.parse_args()
    # OAuth and local callback loggers can include authorization codes.
    logging.disable(logging.CRITICAL)
    try:
        authorize(args.private_directory, args.mailbox, args.wait_seconds)
    except Exception:
        print('Authorization incomplete. No credentials printed; review consent and private setup files.')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
