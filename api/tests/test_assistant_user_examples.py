"""Regressions from user screenshots, with synthetic, independently known data."""

import pytest

from app.support_knowledge import answer_for
from tests.assistant_scenarios import screenshot_metrics


@pytest.mark.parametrize('question', [
    'que hace esta plataforma', 'para que sirve ADS Veris',
    'quehacestaplataforma', 'quehaceestaplataforma',
])
def test_platform_purpose_is_not_capacity(question):
    reply = answer_for(question, metrics=screenshot_metrics(), history=[
        {'role': 'user', 'content': 'cuantos usuarios soporta la plataforma'},
    ])
    assert reply['matched_key'] == 'platform_purpose', reply
    assert 'Limpieza' in reply['answer'] and 'Explorar' in reply['answer']
    assert 'usuarios simult' not in reply['answer']


@pytest.mark.parametrize('question', [
    'cual fue la peor categoria', 'que categoria vendio menos',
    'cual fue la categoria mas baja',
])
def test_worst_category_is_lowest_not_leader(question):
    reply = answer_for(question, metrics=screenshot_metrics())
    assert 'Ferreteria' in reply['answer'] and '$2.000.000' in reply['answer'], reply
    assert 'Retail' not in reply['answer']
    assert 'grupos publicados' in reply['answer']


@pytest.mark.parametrize('question', [
    'Dime la suma de los ingresos de categorias por Distribucion y Ferreteria',
    'cuanto suman Distribucion y Ferreteria',
    'ingresos de Distribucion y Ferreteria juntos',
])
def test_sum_two_groups_is_not_first_group(question):
    reply = answer_for(question, metrics=screenshot_metrics())
    assert '$10.160.000' in reply['answer'], reply
    assert 'Distribucion' in reply['answer'] and 'Ferreteria' in reply['answer']


@pytest.mark.parametrize('connector', ['vs', 'versus', 'y'])
def test_two_distinct_metrics_are_both_answered(connector):
    reply = answer_for(f'Dime el total de unidades vendidas {connector} la utilidad operacional',
                       metrics=screenshot_metrics())
    assert '201.323' in reply['answer'] and '$147.140.533' in reply['answer'], reply
    assert 'unidades' in reply['answer'] and 'Resultado operacional' in reply['answer']


@pytest.mark.parametrize('question', [
    'En unidades vendidas, a que te refieres con las devoluciones conservan su signo?',
    'las unidades vendidas incluyen las devoluciones?',
    'y las devoluciones se restan de las unidades?',
])
def test_units_returns_explain_sign_and_limit(question):
    reply = answer_for(question, metrics=screenshot_metrics())
    assert 'negativ' in reply['answer'] and 'positiv' in reply['answer'], reply
    assert '201.323' in reply['answer']
    assert 'no puedo confirmar' in reply['answer'].lower()


@pytest.mark.parametrize('question', [
    'cual fue el mes en donde mas se vendio en Retail',
    'mejor mes de Retail', 'peor mes de Retail',
])
def test_segment_month_never_uses_global_month(question):
    reply = answer_for(question, metrics=screenshot_metrics())
    assert reply['matched_key'] == 'metric_cross_scope_unavailable', reply
    assert '$300' not in reply['answer'] and '$100' not in reply['answer']


def test_published_matrix_can_answer_segment_best_month():
    metrics = screenshot_metrics()
    metrics['matriz_mes_dimension'] = {'dimension': 'categoria', 'valores': [
        {'mes': '2026-01', 'nombre': 'Retail', 'ingresos': 60},
        {'mes': '2026-02', 'nombre': 'Retail', 'ingresos': 150},
        {'mes': '2026-03', 'nombre': 'Retail', 'ingresos': 40},
    ]}
    reply = answer_for('cual fue el mes en donde mas se vendio en Retail', metrics=metrics)
    assert 'Retail' in reply['answer'] and '2026-02' in reply['answer'] and '$150' in reply['answer'], reply
    assert '$300' not in reply['answer']


def test_missing_group_in_sum_is_not_silently_dropped():
    reply = answer_for('suma los ingresos de Distribucion y Desconocido', metrics=screenshot_metrics())
    assert '$8.160.000' not in reply['answer'], reply
    assert reply['confidence'] != 'high'


def test_followup_changes_ranking_dimension_instead_of_keeping_prior_month():
    history = []
    for question, expected in [
        ('cual fue el mes en donde mas se vendio en Retail', 'cruce compatible'),
        ('cual fue la peor categoria', 'Ferreteria'),
        ('Dime la suma de los ingresos de categorias por Distribucion y Ferreteria', '$10.160.000'),
        ('que hace esta plataforma', 'Limpieza'),
        ('como puedo conseguir ayuda de un humano', 'servicios@adsveris.com'),
        ('Dime el total de unidades vendidas vs la utilidad operacional', '201.323'),
        ('las unidades vendidas incluyen las devoluciones', 'negativas restan'),
    ]:
        reply = answer_for(question, metrics=screenshot_metrics(), history=history[-12:])
        assert expected in reply['answer'], (question, reply)
        history += [{'role': 'user', 'content': question}, {'role': 'assistant', 'content': reply['answer']}]


def test_matrix_partial_month_is_not_the_best_complete_month():
    metrics = screenshot_metrics()
    metrics['evolucion_mensual'][-1]['parcial'] = True
    metrics['matriz_mes_dimension'] = {'dimension': 'categoria', 'valores': [
        {'mes': '2026-01', 'nombre': 'Retail', 'ingresos': 60},
        {'mes': '2026-02', 'nombre': 'Retail', 'ingresos': 150},
        {'mes': '2026-03', 'nombre': 'Retail', 'ingresos': 9999},
    ]}
    reply = answer_for('mejor mes de Retail', metrics=metrics)
    assert '2026-02' in reply['answer'] and '$150' in reply['answer']
    assert '9999' not in reply['answer'] and '9.999' not in reply['answer']


@pytest.mark.parametrize('question', ['unidades en Retail vs utilidad operacional',
                                    'total unidades vendidas y utilidad operacional en Retail'])
def test_two_metrics_do_not_discard_shared_segment(question):
    reply = answer_for(question, metrics=screenshot_metrics())
    assert '201.323' not in reply['answer'] and '147.140.533' not in reply['answer'], reply


def test_quantity_provenance_matches_engine_without_changing_signs():
    import pandas as pd
    from app.engine.metrics import compute_metrics
    frame = pd.DataFrame({'Fecha': ['2026-01-01'] * 4,
                          'Venta': [100, -20, -10, 30], 'Cantidad': [10, -2, 1, None]})
    metrics = compute_metrics(frame, mapping={'monto': 'Venta', 'cantidad': 'Cantidad', 'fecha': 'Fecha'})
    assert metrics['kpis']['unidades_totales'] == 9
    assert metrics['kpis']['unidades_detalle'] == {
        'positivas': 11, 'negativas': -2, 'filas_sin_cantidad': 1,
        'filas_monto_negativo_cantidad_positiva': 1,
    }
    reply = answer_for('las unidades vendidas incluyen las devoluciones', metrics=metrics)
    assert '9 unidades' in reply['answer'] and 'positivas suman 11' in reply['answer']
    assert 'importe negativo y cantidad positiva' in reply['answer']
    assert '1 filas no tienen cantidad' in reply['answer']


def test_high_confidence_support_does_not_wait_for_remote_catalog(client, auth_headers, monkeypatch):
    from app.routes import assistant
    def forbidden(*args):
        raise AssertionError('Known support answers must not fetch the catalog')
    monkeypatch.setattr(assistant, '_cached_catalog', forbidden)
    monkeypatch.setattr(assistant, '_guard_rate', lambda _: None)
    for question in ['que hace esta plataforma', 'olvide mi contrasena', 'necesito ayuda de un humano']:
        response = client.post('/assistant/bot', headers=auth_headers, json={'message': question})
        assert response.status_code == 200
        assert response.json()['coins_charged'] == 0


def test_slow_catalog_refresh_does_not_block_other_conversations(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from app.config import Settings
    from app.routes import assistant
    entered, release = Event(), Event()
    def loader(_):
        entered.set()
        assert release.wait(5)
        return assistant.ARTICLES
    monkeypatch.setattr(assistant, '_load_catalog', loader)
    monkeypatch.setattr(assistant, '_catalog_cache', assistant.OrderedDict())
    settings = Settings(_env_file=None, supabase_url='https://catalog.test', supabase_service_role_key='test-only')
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(assistant._cached_catalog, settings)
        try:
            assert entered.wait(2)
            second = executor.submit(assistant._cached_catalog, settings)
            assert second.result(timeout=1) is assistant.ARTICLES
        finally:
            release.set()
        assert first.result(timeout=2) is assistant.ARTICLES


@pytest.mark.parametrize('metrics', [
    {'kpis': {'unidades_detalle': []}}, {'kpis': {'unidades_totales': float('inf')}},
    {'kpis': {'unidades_totales': float('nan')}}, {'columna': 'x' * 4001}, {'x' * 257: 1},
])
def test_adversarial_context_rejected_before_answering(metrics):
    from pydantic import ValidationError
    from app.routes.assistant import BotRequest
    with pytest.raises(ValidationError):
        BotRequest(message='cuanto vendi', metrics=metrics)


def test_catalog_lookup_never_writes_to_database(monkeypatch):
    from unittest.mock import Mock
    from app.config import Settings
    from app.routes import assistant
    monkeypatch.setattr(assistant.httpx, 'get', lambda *a, **kw: Mock(json=lambda: [], raise_for_status=lambda: None))
    write = Mock(side_effect=AssertionError('Read-only operation'))
    monkeypatch.setattr(assistant.httpx, 'post', write)
    assert assistant._load_catalog(Settings(_env_file=None, supabase_url='https://catalog.test',
                                           supabase_service_role_key='test-only')) is assistant.ARTICLES
    assert not write.called


@pytest.mark.parametrize('question,previous', [
    ('y la peor categoria', 'cual fue mi mejor mes'),
    ('y la peor', 'cual fue la mejor categoria'),
    ('y la mejor categoria', 'cual fue mi peor mes'),
    ('y la mejor', 'cual fue la peor categoria'),
])
def test_followup_ranking_uses_the_current_dimension(question, previous):
    reply = answer_for(question, metrics=screenshot_metrics(), history=[{'role': 'user', 'content': previous}])
    assert ('Ferreteria' if 'peor' in question else 'Retail') in reply['answer'], reply
    assert '2026-' not in reply['answer']


@pytest.mark.parametrize('question', ['suma los ingresos de Desconocido y Distribucion',
                                    'suma ingresos de Retail y Desconocido y Ferreteria'])
def test_unknown_member_in_any_position_prevents_partial_sum(question):
    reply = answer_for(question, metrics=screenshot_metrics())
    assert '$' not in reply['answer'] and reply['confidence'] != 'high', reply
