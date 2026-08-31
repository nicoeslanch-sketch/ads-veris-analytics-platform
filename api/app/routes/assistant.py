"""Asistente gratuito determinista y configuracion del chat avanzado."""

import json
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from ..auth import AuthenticatedUser, get_current_user
from ..config import Settings, get_settings
from ..support_knowledge import ARTICLES, answer_for

router = APIRouter(prefix="/assistant")
_TIMEOUT = 10
_requests: dict[str, deque[datetime]] = defaultdict(deque)
_request_lock = Lock()


class BotMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class BotRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1200)
    metrics: dict | None = None
    historial: list[BotMessage] = Field(default_factory=list, max_length=12)


def _headers(settings: Settings) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }


def _rest(settings: Settings, table: str) -> str:
    return f"{settings.supabase_url.rstrip('/')}/rest/v1/{table}"


def _guard_rate(user_id: str) -> None:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=1)
    with _request_lock:
        entries = _requests[user_id]
        while entries and entries[0] < cutoff:
            entries.popleft()
        if len(entries) >= 20:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Enviaste muchas preguntas seguidas. Espera un minuto y vuelve a intentar.",
            )
        entries.append(now)


def _load_catalog(settings: Settings) -> list[dict]:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return ARTICLES
    try:
        response = httpx.get(
            _rest(settings, "support_bot_articles"),
            params={
                "active": "eq.true",
                "select": "key,category,title,triggers,response,follow_up,priority,active",
                "order": "priority.desc",
                "limit": "500",
            },
            headers=_headers(settings),
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        rows = response.json()
        if rows:
            rows_by_key = {str(row.get("key")): row for row in rows}
            merged = {
                str(item.get("key")): item
                for item in ARTICLES
            }
            merged.update(rows_by_key)
            missing = [
                item for item in ARTICLES if str(item.get("key")) not in rows_by_key
            ]
            if missing:
                try:
                    httpx.post(
                        _rest(settings, "support_bot_articles"),
                        json=missing,
                        headers={
                            **_headers(settings),
                            "Prefer": "resolution=merge-duplicates,return=minimal",
                        },
                        timeout=_TIMEOUT,
                    ).raise_for_status()
                except httpx.HTTPError:
                    pass
            return sorted(
                merged.values(),
                key=lambda item: int(item.get("priority") or 0),
                reverse=True,
            )
        # Primer uso: poblar la base editable con el catalogo versionado.
        seed = httpx.post(
            _rest(settings, "support_bot_articles"),
            json=ARTICLES,
            headers={
                **_headers(settings),
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            timeout=_TIMEOUT,
        )
        seed.raise_for_status()
        return ARTICLES
    except httpx.HTTPError:
        return ARTICLES


@router.get("/config")
async def assistant_config(
    _: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    return {
        "quick_help_enabled": True,
        "advanced_enabled": settings.advanced_ai_enabled,
        "advanced_message_cost": settings.ads_coins_advanced_message_cost,
        "purchases_enabled": settings.ads_coin_purchases_enabled,
        "knowledge_articles": len(ARTICLES),
    }


@router.post("/bot")
async def ask_quick_help(
    body: BotRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    _guard_rate(user.id)
    if body.metrics is not None and len(json.dumps(body.metrics)) > 200_000:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="El contexto de métricas es demasiado grande.",
        )
    catalog = await run_in_threadpool(_load_catalog, settings)
    result = answer_for(
        body.message.strip(),
        catalog,
        body.metrics,
        [item.model_dump(mode="json") for item in body.historial],
    )
    return {
        **result,
        "mode": "deterministic",
        "coins_charged": 0,
        "knowledge_articles": len(catalog),
    }
