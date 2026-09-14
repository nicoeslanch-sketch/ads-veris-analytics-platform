"""One heavy computation per process, including legacy synchronous routes."""

import re
import threading

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

HEAVY_WORK_SLOT = threading.BoundedSemaphore(1)
SYNC_HEAVY_PATHS = frozenset({
    "/restore/latest", "/restore/dataset", "/restore/refresh",
    "/standardize", "/standardize/preload", "/standardize/batch",
    "/clean", "/clean/batch", "/clean/assisted", "/clean/download",
    "/metrics", "/sheets/relationships", "/sheets/relationship-catalog",
    "/sheets/relationship-dashboard", "/consolidation/detect",
})
_CONSOLIDATION_HEAVY = re.compile(
    r"^/consolidation/(?:datasets/[^/]+/inspect|projects/[^/]+/(?:validate|preview))$"
)


def is_synchronous_heavy_request(scope: Scope) -> bool:
    path = scope.get("path", "").rstrip("/")
    method = scope.get("method", "")
    return (method == "POST" and path in SYNC_HEAVY_PATHS) or (
        method in {"POST", "GET"} and bool(_CONSOLIDATION_HEAVY.fullmatch(path))
    )


class ProcessingCapacityMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not is_synchronous_heavy_request(scope):
            await self.app(scope, receive, send)
            return
        if not HEAVY_WORK_SLOT.acquire(blocking=False):
            await JSONResponse(
                {
                    "detail": "Hay un calculo en curso. Espera a que termine o vuelve a intentar en unos segundos.",
                    "code": "PROCESSING_BUSY",
                },
                status_code=429,
                headers={"Retry-After": "10"},
            )(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        finally:
            HEAVY_WORK_SLOT.release()
