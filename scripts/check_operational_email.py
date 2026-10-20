"""Inspect protected server email configuration; send only with --send-test.

Run in the server environment after the mailbox owner grants gmail.send.
No secrets are accepted as arguments, printed, written, or loaded from .env.
Provider acceptance does not prove inbox delivery. The owner confirms receipt.
"""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'api'))

from app.config import Settings
from app.operational_notifications import email_configured, send_test_email


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--send-test', action='store_true',
                        help='Send exactly one test to the configured recipient; requires owner approval.')
    args = parser.parse_args(argv)
    try:
        settings = Settings(_env_file=None)
        if not email_configured(settings):
            result, code = {'status': 'not_configured', 'attempted': False}, 2
        elif not args.send_test:
            result, code = {'status': 'configured_not_tested', 'attempted': False}, 0
        elif send_test_email(settings):
            result, code = {'status': 'provider_accepted', 'attempted': True,
                            'receipt_confirmed': False}, 0
        else:
            result, code = {'status': 'provider_rejected', 'attempted': True}, 1
    except Exception:
        # Provider errors can contain credentials, addresses or callback codes.
        result, code = {'status': 'check_failed', 'receipt_confirmed': False}, 1
    print(json.dumps(result))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
