"""Bound request bodies before multipart/JSON parsing and protect API responses."""

import asyncio
from tempfile import SpooledTemporaryFile
from threading import BoundedSemaphore
from time import monotonic

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class RequestSecurityMiddleware:
    def __init__(self, app: ASGIApp, *, max_body_bytes: int, max_json_bytes: int,
                 max_upload_seconds: float = 120, max_pending_bodies: int = 8) -> None:
        if max_pending_bodies < 1:
            raise ValueError("max_pending_bodies must be positive")
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.max_json_bytes = max_json_bytes
        self.max_upload_seconds = max_upload_seconds
        self._body_slots = BoundedSemaphore(max_pending_bodies)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)

        async def secure_send(message):
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                response_headers.setdefault("X-Content-Type-Options", "nosniff")
                response_headers.setdefault("Referrer-Policy", "no-referrer")
                if headers.get("authorization"):
                    response_headers["Cache-Control"] = "private, no-store"
            await send(message)

        if scope["method"] in {"GET", "HEAD", "OPTIONS"}:
            await self.app(scope, receive, secure_send)
            return
        content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        limit = self.max_json_bytes if content_type == "application/json" or content_type.endswith("+json") else self.max_body_bytes
        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
                if declared < 0:
                    raise ValueError
            except ValueError:
                await JSONResponse({"detail": "Longitud de solicitud invalida."}, 400)(scope, receive, secure_send)
                return
            if declared > limit:
                await self._too_large(scope, receive, secure_send)
                return

        # Bound pre-authentication buffering as well as expensive downstream work.
        # Admission is immediate: waiting uploads must not create another queue.
        if not self._body_slots.acquire(blocking=False):
            await JSONResponse(
                {"detail": "Hay varias cargas en curso. Vuelve a intentar en unos segundos."},
                429, headers={"Retry-After": "5"},
            )(scope, receive, secure_send)
            return
        released = False

        def release_slot():
            nonlocal released
            if not released:
                released = True
                self._body_slots.release()

        try:
            await self._buffer_request(scope, receive, secure_send, limit, release_slot)
        finally:
            release_slot()

    async def _buffer_request(self, scope, receive, send, limit, release_slot):
        # Spill to disk above 1 MB. No unbounded body reaches a parser, including
        # chunked requests and clients lying about Content-Length.
        with SpooledTemporaryFile(max_size=1024 * 1024) as body:
            received = 0
            deadline = monotonic() + self.max_upload_seconds
            while True:
                try:
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        raise TimeoutError
                    message = await asyncio.wait_for(receive(), timeout=min(30, remaining))
                except TimeoutError:
                    await JSONResponse({"detail": "La carga tardo demasiado. Vuelve a intentar."}, 408)(scope, receive, send)
                    return
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                received += len(chunk)
                if received > limit:
                    await self._too_large(scope, receive, send)
                    return
                body.write(chunk)
                if not message.get("more_body", False):
                    break
            body.seek(0)
            replayed = 0
            complete = False

            async def bounded_receive():
                nonlocal replayed, complete
                if complete:
                    return await receive()
                chunk = body.read(256 * 1024)
                replayed += len(chunk)
                complete = replayed >= received
                if complete:
                    body.close()
                    release_slot()
                return {"type": "http.request", "body": chunk, "more_body": not complete}

            await self.app(scope, bounded_receive, send)

    @staticmethod
    async def _too_large(scope: Scope, receive: Receive, send: Send) -> None:
        await JSONResponse({"detail": "La solicitud supera el limite permitido. Reduce su tamano o divide el archivo."}, 413)(scope, receive, send)
