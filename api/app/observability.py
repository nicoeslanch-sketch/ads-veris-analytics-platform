"""Low-overhead request tracing without query strings, tokens or payloads."""

import json
import logging
from time import perf_counter
from uuid import uuid4

from starlette.datastructures import MutableHeaders
from .operational_health import request_window

logger = logging.getLogger("uvicorn.error")


class RequestObservabilityMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        started = perf_counter()
        status_code = 500

        async def traced_send(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, traced_send)
        finally:
            elapsed = round((perf_counter() - started) * 1000, 1)
            if scope.get('path') not in ('/health', '/version', '/admin/operations'):
                request_window.record(status_code, elapsed)
            # Fast successful polls need no log line. Retain failures and slow
            # requests, with parameterized routes instead of dataset/user IDs.
            if status_code >= 400 or elapsed >= 1000:
                route = getattr(scope.get("route"), "path", "unmatched")
                logger.info(json.dumps({"event": "http_request", "request_id": request_id,
                    "method": scope["method"], "route": route, "status": status_code,
                    "duration_ms": elapsed}, separators=(",", ":")))
