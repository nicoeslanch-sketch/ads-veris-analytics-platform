import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location('email_setup',
    Path(__file__).resolve().parents[2] / 'scripts/authorize_operational_email.py')
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


def client():
    return {'installed': {'client_id': 'test.apps.googleusercontent.com', 'client_secret': 'fixture-only',
                          'auth_uri': 'https://untrusted.invalid', 'token_uri': 'https://untrusted.invalid'}}


@pytest.mark.parametrize('value', [None, [], {}, {'web': {}}, {'installed': {'client_id': 'evil.invalid'}}])
def test_setup_rejects_invalid_client(value):
    with pytest.raises(ValueError):
        setup.client_configuration(value)


def test_setup_uses_only_fixed_google_endpoints():
    config = setup.client_configuration(client())['installed']
    assert config['auth_uri'] == 'https://accounts.google.com/o/oauth2/auth'
    assert config['token_uri'] == 'https://oauth2.googleapis.com/token'
    assert config['redirect_uris'] == ['http://localhost']


def test_private_outputs_cannot_overwrite_existing_credentials(tmp_path):
    target = tmp_path / 'credential.json'
    setup.write_private(target, 'existing')
    with pytest.raises(FileExistsError):
        setup.write_private(target, 'replacement')
    assert target.read_text() == 'existing'


@pytest.mark.parametrize('seconds', [0, 59, 3601])
def test_setup_rejects_unbounded_authorization_windows(tmp_path, seconds):
    with pytest.raises(ValueError, match='Authorization window'):
        setup.authorize(tmp_path, 'servicios@adsveris.com', seconds)


def test_setup_never_stores_credentials_inside_repository(monkeypatch, tmp_path):
    monkeypatch.setattr(setup, 'ROOT', tmp_path)
    with pytest.raises(ValueError, match='outside the repository'):
        setup.authorize(tmp_path, 'servicios@adsveris.com')


@pytest.mark.parametrize('scopes,refresh,accepted', [([setup.SCOPE], 'fixture-refresh', True),
    ([setup.SCOPE, 'profile'], 'fixture-refresh', False), ([setup.SCOPE], None, False)])
def test_setup_scopes_loopback_pkce_and_no_secret_output(monkeypatch, tmp_path, capsys, scopes, refresh, accepted):
    tmp_path.chmod(0o700)
    (tmp_path / 'client.json').write_text(json.dumps(client()))
    class LibraryFlow:
        @classmethod
        def from_client_config(cls, config, **kwargs):
            assert kwargs == {'scopes': [setup.SCOPE], 'autogenerate_code_verifier': True}
            instance = cls()
            instance.oauth2session = SimpleNamespace()
            return instance
        def authorization_url(self, **kwargs):
            return 'https://accounts.google.com/o/oauth2/auth?fixture-only', 'fixture-state'
        def fetch_token(self, **kwargs):
            assert kwargs['timeout'] == 20
        def run_local_server(self, **kwargs):
            assert kwargs['host'] == kwargs['bind_addr'] == '127.0.0.1'
            assert kwargs['port'] == 0 and kwargs['timeout_seconds'] == 1800
            assert kwargs['open_browser'] is False and kwargs['authorization_prompt_message'] == ''
            assert kwargs['prompt'] == 'consent' and kwargs['include_granted_scopes'] == 'false'
            assert kwargs['login_hint'] == 'servicios@adsveris.com'
            assert self.oauth2session.trust_env is False and self.oauth2session.max_redirects == 0
            self.authorization_url()
            self.fetch_token()
            return SimpleNamespace(granted_scopes=scopes, scopes=[setup.SCOPE], refresh_token=refresh)
    monkeypatch.setitem(sys.modules, 'google_auth_oauthlib.flow', SimpleNamespace(InstalledAppFlow=LibraryFlow))
    if accepted:
        setup.authorize(tmp_path, 'servicios@adsveris.com')
        saved = json.loads((tmp_path / 'render-email.json').read_text())
        assert saved['OPERATIONS_GMAIL_REFRESH_TOKEN'] == refresh
        assert saved['OPERATIONS_EMAIL_TO'] == saved['OPERATIONS_EMAIL_FROM'] == 'servicios@adsveris.com'
    else:
        with pytest.raises(ValueError):
            setup.authorize(tmp_path, 'servicios@adsveris.com')
        assert not (tmp_path / 'render-email.json').exists()
    output = capsys.readouterr()
    assert 'fixture-refresh' not in output.out + output.err
    assert 'fixture-only' not in output.out + output.err
