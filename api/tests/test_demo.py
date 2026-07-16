"""Contrato de regeneración de la demo ficticia (Fase 14).

Los snapshots que consume el frontend (frontend/src/demo/data/*.json) nacen
del motor REAL vía scripts/generate_demo.py. Este test los regenera y compara:
si el esquema o los resultados cambian, falla RUIDOSAMENTE — la demo no puede
quedar desincronizada en silencio (un prospecto la vería rota antes que nadie).

Si el cambio de esquema es intencional:  cd api && python scripts/generate_demo.py
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from generate_demo import CSV_PATH, OUT_DIR, build_snapshots  # noqa: E402


def test_fixture_de_demo_existe_y_es_ficticio():
    assert CSV_PATH.exists(), "Falta api/demo/demo_empresa_ficticia.csv"
    text = CSV_PATH.read_text(encoding="utf-8")
    assert "Comercial" not in text.splitlines()[0]  # sin encabezados raros
    # Guardas de contenido: la demo es 100% ficticia — jamás debe contener
    # datos con pinta de archivo real de un cliente (REQ, RUT, correos).
    assert "REQ" not in text
    assert "@" not in text


@pytest.mark.parametrize(
    "name", ["demo_standardization.json", "demo_cleaning.json", "demo_metrics.json"]
)
def test_snapshots_de_demo_coinciden_con_el_motor(name):
    path = OUT_DIR / name
    assert path.exists(), (
        f"Falta {path.name}: corre `python scripts/generate_demo.py` desde api/."
    )
    committed = json.loads(path.read_text(encoding="utf-8"))
    regenerated = build_snapshots()[name]
    # Normalización por JSON: el snapshot pasó por json.dumps (tuplas→listas).
    regenerated = json.loads(json.dumps(regenerated))
    assert regenerated == committed, (
        f"{name} quedó desactualizado respecto del motor. Si el cambio es "
        "intencional, regenera con `python scripts/generate_demo.py` y "
        "revisa la demo en el frontend."
    )


def test_demo_congela_lo_que_la_ui_condiciona():
    """La UI bifurca rutas enteras según estos campos: deben estar en el snapshot."""
    metrics = json.loads((OUT_DIR / "demo_metrics.json").read_text(encoding="utf-8"))
    assert metrics["moneda"] == "CLP"
    assert metrics["dimensiones"]["monto"] is True
    assert metrics["dimensiones"]["costo"] is True
    assert metrics["periodo"]["meses_disponibles"]
    assert metrics["advertencias"]
    # La demo exhibe la parcialidad: junio llega hasta el día 15 a propósito.
    ultimo = metrics["evolucion_mensual"][-1]
    assert ultimo["parcial"] is True
    assert ultimo["cobertura_hasta_dia"] == 15
    # La proyección excluye el mes parcial y arranca DESPUÉS del final real.
    assert metrics["proyeccion"]["meses"][0]["mes"] == "2026-07"
    # Y la limpieza tiene problemas REALES que mostrar (duplicados, nulos).
    cleaning = json.loads((OUT_DIR / "demo_cleaning.json").read_text(encoding="utf-8"))
    assert cleaning["problemas"]["duplicados"] >= 2
    assert cleaning["problemas"]["valores_nulos"] > 0
