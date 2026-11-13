"""Bound pre-auth body buffering without blocking reads or streaming responses."""

import asyncio

import pytest

from app.config import Settings
from app.request_security import RequestSecurityMiddleware


def test_saturated_uploads_reject_without_reading_but_allow_get_and_release_on_cancel():
    async def scenario():
        waiting = asyncio.Event()
        never = asyncio.Event()

        async def app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})

        async def slow_receive():
            waiting.set()
            await never.wait()

        async def forbidden_receive():
            pytest.fail("Rejected uploads and GET requests must not be buffered")

        sent = []

        async def send(message):
            sent.append(message)

        middleware = RequestSecurityMiddleware(app, max_body_bytes=20, max_json_bytes=10, max_pending_bodies=1)
        scope = {"type": "http", "method": "POST", "headers": []}
        first = asyncio.create_task(middleware(scope, slow_receive, send))
        await waiting.wait()
        await middleware(scope, forbidden_receive, send)
        assert sent[-2]["status"] == 429
        assert dict(sent[-2]["headers"])[b"retry-after"] == b"5"
        await middleware({**scope, "method": "GET"}, forbidden_receive, send)
        assert sent[-1]["status"] == 200
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert middleware._body_slots.acquire(blocking=False)
        middleware._body_slots.release()

    asyncio.run(scenario())


@pytest.mark.parametrize("outcome", ["disconnect", "oversize", "timeout", "receive_error", "app_error", "unread", "consumed"])
def test_buffer_slots_are_reclaimed_on_every_exit(outcome):
    async def scenario():
        sent = []

        async def send(message):
            sent.append(message)

        async def receive():
            if outcome == "receive_error":
                raise RuntimeError("synthetic receive failure")
            if outcome == "disconnect":
                return {"type": "http.disconnect"}
            return {"type": "http.request", "body": b"x" * (21 if outcome == "oversize" else 5)}

        async def app(scope, receive, send):
            if outcome == "app_error":
                raise RuntimeError("synthetic application failure")
            if outcome == "consumed":
                assert (await receive())["body"] == b"xxxxx"
                # Long-lived responses must not retain body admission slots.
                assert middleware._body_slots.acquire(blocking=False)
                middleware._body_slots.release()

        middleware = RequestSecurityMiddleware(
            app, max_body_bytes=20, max_json_bytes=10, max_pending_bodies=1,
            max_upload_seconds=-1 if outcome == "timeout" else 120,
        )
        call = middleware({"type": "http", "method": "POST", "headers": []}, receive, send)
        if outcome in {"receive_error", "app_error"}:
            with pytest.raises(RuntimeError):
                await call
        else:
            await call
        if outcome in {"oversize", "timeout"}:
            assert sent[0]["status"] == (413 if outcome == "oversize" else 408)
        assert middleware._body_slots.acquire(blocking=False)
        assert not middleware._body_slots.acquire(blocking=False)
        middleware._body_slots.release()

    asyncio.run(scenario())


@pytest.mark.parametrize("limit", [0, -1, 65])
def test_invalid_body_admission_settings_are_rejected(limit):
    with pytest.raises(ValueError, match="recepciones HTTP"):
        Settings(_env_file=None, request_max_pending_bodies=limit)
