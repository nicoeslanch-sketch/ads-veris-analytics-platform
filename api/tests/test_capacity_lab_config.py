"""The capacity harness must never rewrite a real project or reuse its ports."""

import importlib.util
from pathlib import Path
import socket

import pytest
import tomlkit


SPEC = importlib.util.spec_from_file_location(
    'capacity_config', Path(__file__).resolve().parents[2] / 'scripts/configure_capacity_lab.py')
config = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(config)


@pytest.mark.parametrize('path', [
    '/tmp/ads-capacity-lab-123/supabase/config.toml.bak',
    '/tmp/ads-capacity-lab-/supabase/config.toml',
    '/tmp/ads-capacity-lab-production/supabase/config.toml',
    '/tmp/project/supabase/config.toml',
    '/tmp/ads-capacity-lab-123/other/config.toml',
    '/tmp/ads-capacity-lab-123/supabase/../../config.toml',
])
def test_rejects_paths_outside_disposable_lab(path):
    with pytest.raises(ValueError):
        config.validate_path(path)


def test_ports_are_unique_and_other_settings_survive(tmp_path, monkeypatch):
    path = tmp_path / 'config.toml'
    with socket.socket() as occupied:
        occupied.bind(('0.0.0.0', 0))
        used = occupied.getsockname()[1]
        source = {'project_id': 'synthetic', 'api': {'port': used, 'max_rows': 1000},
                  'db': {'port': used, 'shadow_port': used, 'major_version': 17},
                  'auth': {'site_url': 'http://localhost:3000', 'enable_signup': True},
                  'inbucket': {'port': used, 'smtp_port': used}}
        path.write_text(tomlkit.dumps(source), encoding='utf-8')
        monkeypatch.setattr(config, 'validate_path', lambda value: path)
        assigned = config.configure(path)
        assert len(set(assigned.values())) == len(assigned) == 5
        assert used not in assigned.values()
        result = tomlkit.parse(path.read_text(encoding='utf-8'))
        assert result['auth'] == source['auth']
        assert result['api']['max_rows'] == 1000
        assert result['db']['major_version'] == 17
        assert result['project_id'] == 'synthetic'
        assert result['db']['port'] == assigned['db.port']


def test_missing_required_port_does_not_write(tmp_path, monkeypatch):
    path = tmp_path / 'config.toml'
    original = '[api]\nport = 54321\n'
    path.write_text(original, encoding='utf-8')
    monkeypatch.setattr(config, 'validate_path', lambda value: path)
    with pytest.raises(ValueError):
        config.configure(path)
    assert path.read_text(encoding='utf-8') == original
