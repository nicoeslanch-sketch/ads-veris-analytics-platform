"""P0-6 (fix/qa-motor-empresarial-024): concurrencia acotada y memoria real.

Cubre los dos ejes del bloque:
- concurrency.heavy_job_slot: semáforo lógico + cola acotada + timeout +
  cancelación segura (el cupo se libera siempre, incluso ante excepción).
- estimate_memory_bytes / presupuesto de _FRAME_CACHE en bytes reales: la
  cantidad de celdas no distingue un archivo de strings largos de uno de
  strings cortos con la misma forma; memory_usage(deep=True) sí.
"""

import threading
import time

import pandas as pd
import pytest
from fastapi import HTTPException

from app import concurrency
from app.engine.loader import estimate_memory_bytes


class FakeSettings:
    max_concurrent_heavy_jobs = 1
    heavy_job_queue_max = 1
    heavy_job_acquire_timeout_s = 0.3


# ── concurrency.heavy_job_slot ───────────────────────────────────────────────


def test_heavy_job_slot_permite_y_libera_el_cupo():
    before = concurrency.snapshot()
    with concurrency.heavy_job_slot(FakeSettings(), label="test"):
        during = concurrency.snapshot()
        assert during.active == before.active + 1
    after = concurrency.snapshot()
    assert after.active == before.active


def test_heavy_job_slot_libera_el_cupo_aunque_el_trabajo_lance_excepcion():
    """Cancelación segura: un error dentro del bloque no deja el cupo huérfano."""
    before = concurrency.snapshot()
    with pytest.raises(ValueError):
        with concurrency.heavy_job_slot(FakeSettings(), label="test"):
            raise ValueError("boom")
    after = concurrency.snapshot()
    assert after.active == before.active


def test_heavy_job_slot_espera_y_luego_entra_cuando_se_libera_el_anterior():
    """Un segundo trabajo espera (no se rechaza de inmediato) y entra en
    cuanto el primero libera su cupo — dentro del timeout configurado."""

    class RoomySettings:
        max_concurrent_heavy_jobs = 1
        heavy_job_queue_max = 4
        heavy_job_acquire_timeout_s = 5.0

    first_in = threading.Event()
    release_first = threading.Event()
    second_result: dict[str, bool] = {}

    def hold_first():
        with concurrency.heavy_job_slot(RoomySettings(), label="primero"):
            first_in.set()
            release_first.wait(timeout=5)

    def try_second():
        first_in.wait(timeout=5)
        started = time.monotonic()
        with concurrency.heavy_job_slot(RoomySettings(), label="segundo"):
            second_result["waited_s"] = time.monotonic() - started
            second_result["entered"] = True

    t1 = threading.Thread(target=hold_first)
    t2 = threading.Thread(target=try_second)
    t1.start()
    t1_started_waiting = first_in.wait(timeout=5)
    assert t1_started_waiting
    t2.start()
    time.sleep(0.2)  # el segundo debe estar esperando, no haber entrado
    assert second_result.get("entered") is None
    release_first.set()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert second_result.get("entered") is True
    assert second_result["waited_s"] >= 0.15  # esperó de verdad al primero


def test_heavy_job_slot_responde_503_por_timeout_sin_dejar_el_cupo_ocupado():
    """Con el cupo único ocupado, un segundo intento con timeout corto
    recibe 503 en vez de esperar indefinidamente o entrar igual."""
    release = threading.Event()
    holder_in = threading.Event()

    def holder():
        with concurrency.heavy_job_slot(FakeSettings(), label="holder"):
            holder_in.set()
            release.wait(timeout=5)

    t = threading.Thread(target=holder)
    t.start()
    assert holder_in.wait(timeout=5)

    before = concurrency.snapshot()
    with pytest.raises(HTTPException) as excinfo:
        with concurrency.heavy_job_slot(FakeSettings(), label="segundo"):
            pytest.fail("no debería haber entrado: el cupo estaba ocupado")
    assert excinfo.value.status_code == 503

    release.set()
    t.join(timeout=5)
    after = concurrency.snapshot()
    # El rechazo por timeout no incrementa 'active' (nunca llegó a entrar).
    assert after.active == before.active - 1  # el holder ya liberó su cupo


def test_heavy_job_slot_responde_503_cuando_la_cola_esta_llena():
    """Con la cola llena, el rechazo es inmediato: no hace esperar a nadie
    a que se agote un timeout para descubrir que no había espacio.

    Se simula la cola llena manipulando el estado del módulo directamente
    (1 activo + 1 esperando) en vez de coordinar hilos reales: el punto a
    probar es la rama de rechazo inmediato, no el paso por _condition.wait."""

    class TinySettings:
        max_concurrent_heavy_jobs = 1
        heavy_job_queue_max = 1
        heavy_job_acquire_timeout_s = 5.0

    with concurrency._condition:
        concurrency._active_jobs += 1
        concurrency._waiting_jobs += 1
    try:
        started = time.monotonic()
        with pytest.raises(HTTPException) as excinfo:
            with concurrency.heavy_job_slot(TinySettings(), label="rechazado"):
                pytest.fail("no debería haber entrado: la cola está llena")
        elapsed = time.monotonic() - started
        assert excinfo.value.status_code == 503
        assert elapsed < 1.0  # rechazo inmediato, no esperó el timeout de 5s
    finally:
        with concurrency._condition:
            concurrency._active_jobs -= 1
            concurrency._waiting_jobs -= 1


# ── estimate_memory_bytes ────────────────────────────────────────────────────


def test_estimate_memory_bytes_distingue_contenido_no_solo_forma():
    """Dos DataFrames con la MISMA cantidad de celdas pueden diferir en
    memoria real por un orden de magnitud según el largo de sus strings —
    la cantidad de celdas no lo distingue, memory_usage(deep=True) sí."""
    short_df = pd.DataFrame({"a": ["x"] * 1000, "b": ["y"] * 1000})
    long_df = pd.DataFrame({"a": ["x" * 500] * 1000, "b": ["y" * 500] * 1000})
    assert len(short_df) * len(short_df.columns) == len(long_df) * len(long_df.columns)

    short_bytes = estimate_memory_bytes(short_df)
    long_bytes = estimate_memory_bytes(long_df)
    assert long_bytes > short_bytes * 10


def test_estimate_memory_bytes_nunca_lanza_con_dataframe_vacio():
    assert estimate_memory_bytes(pd.DataFrame()) >= 0


# ── Presupuesto real de memoria en _FRAME_CACHE ──────────────────────────────


def test_frame_cache_rechaza_entrada_que_supera_el_presupuesto_individual_en_bytes(
    monkeypatch,
):
    """Una entrada con pocas celdas pero strings enormes debe rechazarse por
    el techo de BYTES aunque quepa cómoda en el techo de CELDAS."""
    from app.routes import pipeline as pipeline_module

    monkeypatch.setattr(pipeline_module, "_FRAME_CACHE_MAX_ENTRY_BYTES", 1000)
    huge_text_df = pd.DataFrame({"col": ["z" * 10_000] * 5})  # 5 celdas, ~50KB
    key = ("test-memory-budget", "huge")

    with pipeline_module._FRAME_CACHE_LOCK:
        pipeline_module._FRAME_CACHE.pop(key, None)
    pipeline_module._frame_cache_store(key, huge_text_df, {})

    assert pipeline_module._frame_cache_has(key) is False


def test_frame_cache_desaloja_por_presupuesto_de_bytes_no_solo_por_celdas(
    monkeypatch,
):
    """Con un techo de bytes bajo pero un techo de celdas generoso, agregar
    una tercera entrada debe desalojar la más antigua igual: el presupuesto
    de memoria real manda aunque el de celdas no se haya alcanzado."""
    from app.routes import pipeline as pipeline_module

    monkeypatch.setattr(pipeline_module, "_FRAME_CACHE_CELL_BUDGET", 10_000_000)
    monkeypatch.setattr(pipeline_module, "_FRAME_CACHE_MAX_ENTRY_CELLS", 10_000_000)
    monkeypatch.setattr(pipeline_module, "_FRAME_CACHE_MEMORY_BUDGET_BYTES", 200_000)
    monkeypatch.setattr(pipeline_module, "_FRAME_CACHE_MAX_ENTRY_BYTES", 200_000)

    def make_df(tag: str) -> pd.DataFrame:
        return pd.DataFrame({"col": [f"{tag}-" + "w" * 5_000] * 10})  # ~50KB c/u

    keys = [("test-eviction", i) for i in range(4)]
    with pipeline_module._FRAME_CACHE_LOCK:
        for key in keys:
            pipeline_module._FRAME_CACHE.pop(key, None)

    for i, key in enumerate(keys):
        pipeline_module._frame_cache_store(key, make_df(str(i)), {})

    # El presupuesto de 200KB no alcanza para las 4 entradas de ~50KB más el
    # resto de lo que ya hubiera en caché de otros tests: la primera debe
    # haber sido desalojada por LRU.
    assert pipeline_module._frame_cache_has(keys[0]) is False
    assert pipeline_module._frame_cache_has(keys[-1]) is True
