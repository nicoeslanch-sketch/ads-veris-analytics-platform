"""Pruebas de la Fase 11: rendimiento con datos grandes y precisión del motor."""

import json

import pandas as pd

from app.engine.mapping import resolve_mapping
from app.engine.standardize import (
    column_date_profile,
    map_unique,
    parse_date,
    parse_number,
)


# ── Números: convención es-CL y US en la misma plataforma (§8.2) ─────────────


def test_parse_number_convencion_chilena():
    assert parse_number("1.234,56") == 1234.56
    assert parse_number("$1.500") == 1500
    assert parse_number("1,5") == 1.5


def test_parse_number_convencion_us():
    """'1,234.56' y '1,234,567' fallaban (None) antes de la Fase 11."""
    assert parse_number("1,234.56") == 1234.56
    assert parse_number("1,234,567") == 1234567
    assert parse_number("US$2,500.75") == 2500.75


# ── Fechas: evidencia por valor y columnas mixtas (§7) ───────────────────────


def test_fecha_evidencia_por_valor():
    """Cada valor inequívoco se interpreta por su propia evidencia, aunque la
    columna tenga otra convención dominante."""
    # 13/05 solo puede ser 13 de mayo; 05/14 solo puede ser 14 de mayo
    assert parse_date("13/05/2026", dayfirst=False).strftime("%Y-%m-%d") == "2026-05-13"
    assert parse_date("05/14/2026", dayfirst=True).strftime("%Y-%m-%d") == "2026-05-14"


def test_column_date_profile_mixta():
    serie = pd.Series(["13/05/2026", "05/14/2026", "01/02/2026"])
    profile = column_date_profile(serie)
    assert profile["mixta"] is True
    assert profile["dmy"] == 1 and profile["mdy"] == 1
    assert profile["ambiguas"] == 1


def test_fechas_mixtas_avisan_en_standardize(client, auth_headers):
    csv = "Fecha;Ventas\n13/05/2026;100\n05/14/2026;200\n01/02/2026;300\n"
    response = client.post(
        "/standardize",
        files={"file": ("mixtas_f11.csv", csv.encode("utf-8"), "text/csv")},
        headers=auth_headers,
    )
    assert response.status_code == 200
    avisos = response.json().get("avisos", [])
    assert any("mezcla formatos de fecha" in a for a in avisos)


# ── map_unique: mismo resultado que map celda a celda (§3) ───────────────────


def test_map_unique_equivale_a_map():
    serie = pd.Series(["1.000", "2.500", "1.000", "", "abc"] * 20)
    esperado = serie.map(lambda v: parse_number(v))
    obtenido = map_unique(serie, lambda v: parse_number(v))
    assert esperado.equals(obtenido)  # equals trata NaN == NaN


# ── Categóricas morfológicas: pagado/pagada (§8.1) ───────────────────────────


def test_pagado_pagada_se_unifican(client, auth_headers):
    filas = "\n".join(
        [f"0{d}/05/2026;100;Pagado" for d in range(1, 9)]
        + ["09/05/2026;200;Pagada", "10/05/2026;300;Pagada"]
    )
    csv = "Fecha;Ventas;Estado\n" + filas
    response = client.post(
        "/clean",
        files={"file": ("estados_f11.csv", csv.encode("utf-8"), "text/csv")},
        data={"apply": "true"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    columnas = body["preview"]["columnas"]
    idx = columnas.index("Estado")
    valores = {fila[idx] for fila in body["preview"]["filas"] if fila[idx]}
    assert valores == {"Pagado"}


def test_categorias_equilibradas_no_se_fusionan(client, auth_headers):
    """'Venta'/'Ventas' 50/50 son categorías legítimas: fusionarlas sería
    destruir información (la guarda exige minoría ≤ 1/4 de la dominante)."""
    filas = "\n".join(
        [f"0{d}/05/2026;100;Boleta" for d in range(1, 6)]
        + [f"0{d}/05/2026;200;Boletas" for d in range(1, 6)]
    )
    csv = "Fecha;Ventas;Tipo\n" + filas
    response = client.post(
        "/clean",
        files={"file": ("equilibradas_f11.csv", csv.encode("utf-8"), "text/csv")},
        data={"apply": "true"},
        headers=auth_headers,
    )
    body = response.json()
    idx = body["preview"]["columnas"].index("Tipo")
    valores = {fila[idx] for fila in body["preview"]["filas"] if fila[idx]}
    assert valores == {"Boleta", "Boletas"}


# ── Mapeo parcial: el override NO borra los roles detectados (§9.1) ──────────


def test_resolve_mapping_fusiona_override_parcial():
    columns = ["fecha", "ventas", "tipo"]
    resolved = resolve_mapping(columns, {"categoria": "tipo"})
    assert resolved.get("fecha") == "fecha"
    assert resolved.get("monto") == "ventas"
    assert resolved.get("categoria") == "tipo"


def test_metrics_con_mapping_parcial_conserva_ingresos(client, auth_headers):
    """Antes de la Fase 11, enviar un mapping con UN rol reemplazaba el mapeo
    completo: el dashboard quedaba en $0 tras corregir una sola columna."""
    csv = (
        "Fecha;Ventas;Tipo\n"
        "01/05/2026;1000;Retail\n"
        "02/05/2026;2000;Mayorista\n"
    )
    response = client.post(
        "/metrics",
        files={"file": ("map_parcial_f11.csv", csv.encode("utf-8"), "text/csv")},
        data={"mapping": json.dumps({"categoria": "Tipo"})},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["kpis"]["ingresos_totales"]["valor"] == 3000.0
    categorias = {c["nombre"] for c in body.get("por_categoria", [])}
    assert categorias == {"Retail", "Mayorista"}


# ── Caché del pipeline: el segundo módulo NO reprocesa el archivo (§2) ───────


def test_cache_reutiliza_el_pipeline_entre_llamadas(client, auth_headers, monkeypatch):
    from app.routes import pipeline as pl

    llamadas = {"n": 0}
    real = pl.analyze_and_clean

    def contado(*args, **kwargs):
        llamadas["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(pl, "analyze_and_clean", contado)
    # Contenido único: garantiza una clave de caché que no existe todavía.
    csv = "Fecha;Ventas\n01/05/2026;111\n02/05/2026;222\n03/05/2026;333\n"
    for _ in range(2):
        response = client.post(
            "/metrics",
            files={"file": ("cache_f11.csv", csv.encode("utf-8"), "text/csv")},
            headers=auth_headers,
        )
        assert response.status_code == 200
    assert llamadas["n"] == 1


def test_standardize_y_clean_reutilizan_carga_y_estandarizacion(
    client, auth_headers, monkeypatch
):
    from app.routes import pipeline as pl

    with pl._CACHE_LOCK:
        pl._CLEAN_CACHE.clear()
    with pl._FRAME_CACHE_LOCK:
        pl._FRAME_CACHE.clear()

    calls = {"load": 0, "standardize": 0}
    real_load = pl.load_dataframe_with_report
    real_standardize = pl.standardize_dataframe

    def counted_load(*args, **kwargs):
        calls["load"] += 1
        return real_load(*args, **kwargs)

    def counted_standardize(*args, **kwargs):
        calls["standardize"] += 1
        return real_standardize(*args, **kwargs)

    monkeypatch.setattr(pl, "load_dataframe_with_report", counted_load)
    monkeypatch.setattr(pl, "standardize_dataframe", counted_standardize)
    csv = "Fecha;Ventas\n01/05/2026;9181\n02/05/2026;9182\n".encode()
    files = {"file": ("etapas-cache.csv", csv, "text/csv")}

    standardized = client.post("/standardize", files=files, headers=auth_headers)
    cleaned = client.post("/clean", files=files, headers=auth_headers)

    assert standardized.status_code == cleaned.status_code == 200
    assert calls == {"load": 1, "standardize": 1}


def test_reglas_default_explicitas_comparten_cache_con_metricas(
    client, auth_headers, monkeypatch
):
    from app.engine.clean import DEFAULT_RULES
    from app.routes import pipeline as pl

    with pl._CACHE_LOCK:
        pl._CLEAN_CACHE.clear()
    with pl._FRAME_CACHE_LOCK:
        pl._FRAME_CACHE.clear()
    calls = {"analyze": 0}
    real_analyze = pl.analyze_and_clean

    def counted(*args, **kwargs):
        calls["analyze"] += 1
        return real_analyze(*args, **kwargs)

    monkeypatch.setattr(pl, "analyze_and_clean", counted)
    csv = "Fecha;Ventas\n01/05/2026;771\n02/05/2026;772\n".encode()
    files = {"file": ("defaults-cache.csv", csv, "text/csv")}

    cleaned = client.post(
        "/clean",
        files=files,
        data={"apply": "true", "rules": json.dumps(DEFAULT_RULES)},
        headers=auth_headers,
    )
    metrics = client.post("/metrics", files=files, headers=auth_headers)

    assert cleaned.status_code == metrics.status_code == 200
    assert calls["analyze"] == 1


def test_cache_storage_tiene_ttl_y_se_invalida_al_eliminar(monkeypatch):
    from app import storage
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "supabase_url", "https://cache-test.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "service-role-test")
    with storage._CACHE_LOCK:
        storage._DOWNLOAD_CACHE.clear()
    calls = {"stream": 0}

    class FakeResponse:
        status_code = 200
        headers = {"content-length": "4"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_bytes(self):
            yield b"data"

    def fake_stream(*args, **kwargs):
        calls["stream"] += 1
        return FakeResponse()

    monkeypatch.setattr(storage.httpx, "stream", fake_stream)
    path = "user-test-123/cache-performance.csv"

    assert storage.download_from_storage(path) == b"data"
    assert storage.download_from_storage(path) == b"data"
    assert calls["stream"] == 1

    storage.invalidate_storage_cache(path)
    assert storage.download_from_storage(path) == b"data"
    assert calls["stream"] == 2
