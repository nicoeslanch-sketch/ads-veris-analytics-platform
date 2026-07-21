"""Identidad de versión del motor (Fase 16).

Fuente ÚNICA para: el endpoint GET /version (identidad de despliegue), el
versionado de snapshots de restauración (un snapshot generado por un motor
distinto se invalida y se recalcula) y los metadatos de exportación.

Actualizar ENGINE_VERSION en cada release que cambie resultados del motor
(estandarización, limpieza o métricas). El SHA del commit llega por entorno
(Render expone RENDER_GIT_COMMIT; también se acepta GIT_SHA genérico).
"""

import os

ENGINE_VERSION = "0.21.2"
LATEST_MIGRATION = "0021"


def commit_sha() -> str:
    return (
        os.environ.get("RENDER_GIT_COMMIT")
        or os.environ.get("GIT_SHA")
        or "desconocido"
    )
