import random
import string

import pytest

from app.language_normalization import _edit_distance, normalize_query
from app.support_knowledge import answer_for
from tests.assistant_scenarios import sales_metrics


@pytest.mark.parametrize('question,key,expected', [
    ('como puedo unir varios excel en uno', 'workbook_bundle', 'todas sus hojas'),
    ('consolidar archivos', 'workbook_bundle', 'no cruza tablas'),
    ('juntar excels', 'workbook_bundle', 'No elimina duplicados'),
    ('consolidararchivos', 'workbook_bundle', 'No elimina duplicados'),
    ('consoliddar archivos', 'workbook_bundle', 'No elimina duplicados'),
    ('al unir excel se borran duplicados', 'workbook_bundle', 'No elimina duplicados'),
    ('se conservan las formulas al unir archivos', 'workbook_bundle', 'no formulas'),
    ('por que tarda buscando conexiones seguras entre las hojas', 'relationship_wait', 'no se explica solo'),
    ('las relaciones estan lentas', 'relationship_wait', 'tiempo transcurrido'),
    ('para que son los recuadros grises de carga', 'loading_skeleton', 'no representan tus valores'),
])
def test_workflow_questions_do_not_become_financial_answers(question, key, expected):
    response = answer_for(question, metrics=sales_metrics())
    assert response['matched_key'] == key, response
    assert expected in response['answer']


def test_multi_turn_bundle_questions_preserve_then_release_context():
    history = []
    for question, key in [('quiero unir varios excel', 'workbook_bundle'),
                          ('y conserva las formulas', 'workbook_bundle'),
                          ('cuanto vendi', None), ('necesito un humano', 'human_support')]:
        response = answer_for(question, metrics=sales_metrics(), history=history)
        if key:
            assert response['matched_key'] == key, response
        else:
            assert response['matched_key'] != 'workbook_bundle'
        history.extend([{'role': 'user', 'content': question}, {'role': 'assistant', 'content': response['answer']}])


@pytest.mark.parametrize('question', ['consolidar ventas', 'unir ventas de distintos periodos'])
def test_sales_analysis_not_confused_with_copying_files(question):
    assert answer_for(question, metrics=sales_metrics())['matched_key'] != 'workbook_bundle'


def test_real_words_are_not_changed_into_missing_values_or_split_connections():
    assert normalize_query('varios archivos conexiones formulas') == 'varios archivos conexiones formulas'


def test_fast_distance_matches_reference_with_cutoff():
    def reference(a, b):
        previous = list(range(len(b) + 1))
        for i, char in enumerate(a, 1):
            current = [i]
            for j, other in enumerate(b, 1):
                current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (char != other)))
            previous = current
        return previous[-1]
    rng = random.Random(43)
    for _ in range(1000):
        a = ''.join(rng.choices(string.ascii_lowercase, k=rng.randrange(25)))
        b = a[:rng.randrange(len(a) + 1)] + rng.choice(string.ascii_lowercase)
        for cutoff in [1, 2]:
            assert _edit_distance(a, b, cutoff) == min(reference(a, b), cutoff + 1)
