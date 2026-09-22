"""Enable real TOTP only in the disposable CI stack, never on a remote project."""

from pathlib import Path
import sys

import tomlkit


path = Path(sys.argv[1]).resolve()
if not str(path).startswith('/tmp/ads-security-') or path.name != 'config.toml':
    raise SystemExit('Only the disposable CI configuration may be changed')
document = tomlkit.parse(path.read_text(encoding='utf-8'))
document['auth']['mfa']['totp']['enroll_enabled'] = True
document['auth']['mfa']['totp']['verify_enabled'] = True
path.write_text(tomlkit.dumps(document), encoding='utf-8')
