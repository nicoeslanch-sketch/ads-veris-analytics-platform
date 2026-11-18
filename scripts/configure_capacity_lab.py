"""Assign free host ports only to a disposable capacity-lab configuration."""

from contextlib import ExitStack
from pathlib import Path
import socket
import sys

import tomlkit


PORTS = (
    ('api', 'port'), ('db', 'port'), ('db', 'shadow_port'),
    ('db', 'pooler', 'port'), ('studio', 'port'), ('inbucket', 'port'),
    ('inbucket', 'smtp_port'), ('inbucket', 'pop3_port'),
    ('analytics', 'port'), ('edge_runtime', 'inspector_port'),
)


def validate_path(path):
    path = Path(path).resolve()
    lab = path.parent.parent
    if (path.name != 'config.toml' or path.parent.name != 'supabase'
            or lab.parent != Path('/tmp')
            or not lab.name.startswith('ads-capacity-lab-')
            or not lab.name.removeprefix('ads-capacity-lab-').isdigit()):
        raise ValueError('Only /tmp/ads-capacity-lab-<run-id>/supabase/config.toml is allowed')
    return path


def configure(path):
    path = validate_path(path)
    document = tomlkit.parse(path.read_text(encoding='utf-8'))
    for section in ('api', 'db'):
        if not isinstance(document.get(section, {}).get('port'), int):
            raise ValueError('Missing required local port configuration')
    assigned = {}
    # Keep all reservations open until writing, so the OS cannot reuse a port
    # within this allocation. Docker takes ownership immediately after exit.
    with ExitStack() as reservations:
        for keys in PORTS:
            table = document
            for key in keys[:-1]:
                table = table.get(key, {})
            if keys[-1] not in table:
                continue
            sock = reservations.enter_context(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
            sock.bind(('0.0.0.0', 0))
            port = sock.getsockname()[1]
            table[keys[-1]] = port
            assigned['.'.join(keys)] = port
        path.write_text(tomlkit.dumps(document), encoding='utf-8')
    return assigned


if __name__ == '__main__':
    ports = configure(sys.argv[1])
    print('Disposable lab ports: ' + ', '.join(f'{key}={value}' for key, value in ports.items()))
