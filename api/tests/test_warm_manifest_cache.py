from copy import deepcopy
from unittest.mock import Mock

import pandas as pd
import pytest

from app.routes import pipeline


@pytest.fixture
def warm(monkeypatch):
    entry = {'nombre': 'Ventas', 'procesar': True, 'rules': {}, 'mapping': {},
             'scope': {}, 'eliminar_duplicados': False, 'revision': 7}
    frame = pd.DataFrame({'ID': ['001', '001'], 'Total': [12.25, -1.25]})
    result = {'_df_limpio': frame, 'mapeo': {'monto': 'Total'}}
    key = pipeline._cache_key(b'content', {}, True, None, None, 'Ventas', False, 'dataset-a', 7)
    with pipeline._CACHE_LOCK:
        pipeline._CLEAN_CACHE.clear()
        pipeline._CLEAN_CACHE[key] = result
    yield entry, result
    with pipeline._CACHE_LOCK:
        pipeline._CLEAN_CACHE.clear()


def test_just_cleaned_manifest_skips_download_and_xlsx_open(warm, monkeypatch):
    entry, result = warm
    for name in ['_load_metrics_clean_artifact', '_load_batch_frames_cached', '_analyze_cached']:
        monkeypatch.setattr(pipeline, name, Mock(side_effect=AssertionError(f'Redundant {name}')))
    persist = Mock()
    monkeypatch.setattr(pipeline, '_store_metrics_clean_artifact', persist)
    frames, mappings, results = pipeline._processed_manifest_frames(
        'data.xlsx', b'content', {'hojas': [entry]}, 'dataset-a', None, 'user-a')
    pd.testing.assert_frame_equal(frames['Ventas'], result['_df_limpio'])
    frames['Ventas'].iloc[0, 1] = 999
    assert result['_df_limpio'].iloc[0, 1] == 12.25
    assert mappings['Ventas'] == {'monto': 'Total'}
    assert persist.call_count == 1


@pytest.mark.parametrize('change', ['revision', 'rules', 'mapping', 'scope', 'duplicates', 'dataset', 'content'])
def test_other_configuration_never_reuses_stale_frame(warm, monkeypatch, change):
    entry, result = warm
    entry = deepcopy(entry)
    dataset, content = 'dataset-a', b'content'
    if change == 'revision': entry['revision'] = 8
    elif change == 'rules': entry['rules'] = {'trim': False}
    elif change == 'mapping': entry['mapping'] = {'monto': 'Total'}
    elif change == 'scope': entry['scope'] = {'columns': ['ID']}
    elif change == 'duplicates': entry['eliminar_duplicados'] = True
    elif change == 'dataset': dataset = 'dataset-b'
    else: content = b'new-content'
    fallback = Mock(return_value=result)
    monkeypatch.setattr(pipeline, '_load_metrics_clean_artifact', fallback)
    pipeline._processed_manifest_frames('data.xlsx', content, {'hojas': [entry]}, dataset, None, 'user-a')
    assert fallback.call_count == 1
