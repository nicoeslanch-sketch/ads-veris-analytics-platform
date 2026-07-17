"""Genera los snapshots de la DEMO FICTICIA con el motor REAL (Fase 14).

Contrato de regeneración: los JSON que consume el frontend
(frontend/src/demo/data/*.json) NO se escriben a mano — nacen de pasar
api/demo/demo_empresa_ficticia.csv por el MISMO pipeline que un archivo
subido (_standardize_sync → _clean_sync → _metrics_sync). Si el esquema de
respuestas cambia, `pytest api/tests/test_demo.py` falla ruidosamente y este
script se vuelve a correr — la demo no puede desincronizarse en silencio.

Uso:  cd api && python scripts/generate_demo.py

Los snapshots incluyen moneda, dimensiones, periodo, parcialidad,
advertencias, mapeo, KPIs, evolución y agrupaciones: todo lo que la UI
condiciona debe quedar congelado para que la demo sea determinista.
"""

import json
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR))

from app.engine.clean import DEFAULT_RULES  # noqa: E402
from app.routes.pipeline import (  # noqa: E402
    _clean_sync,
    _metrics_sync,
    _standardize_sync,
)

CSV_PATH = API_DIR / "demo" / "demo_empresa_ficticia.csv"
OUT_DIR = API_DIR.parent / "frontend" / "src" / "demo" / "data"
FILENAME = "demo_empresa_ficticia.csv"


def build_snapshots() -> dict[str, dict]:
    content = CSV_PATH.read_bytes()
    standardization = _standardize_sync(FILENAME, content)
    cleaning = _clean_sync(FILENAME, content, dict(DEFAULT_RULES), apply=True)
    metrics = _metrics_sync(FILENAME, content, None, None, None)
    return {
        "demo_standardization.json": standardization,
        "demo_cleaning.json": cleaning,
        "demo_metrics.json": metrics,
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, payload in build_snapshots().items():
        path = OUT_DIR / name
        with path.open("w", encoding="utf-8", newline="\n") as output:
            output.write(
                json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
            )
        print(f"✓ {path.relative_to(API_DIR.parent)}")


if __name__ == "__main__":
    main()
