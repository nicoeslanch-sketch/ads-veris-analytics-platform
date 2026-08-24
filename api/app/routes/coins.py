"""Billetera ADS Coins.

La billetera y el ledger ya son funcionales. Las compras y el consumo del chat
avanzado permanecen apagados por feature flag hasta integrar pago e IA.
"""

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from ..auth import AuthenticatedUser, get_current_user
from ..capabilities import get_profile_flags
from ..config import Settings, get_settings

router = APIRouter(prefix="/coins")
_TIMEOUT = 10


def _headers(settings: Settings) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }


def _rest(settings: Settings, path: str) -> str:
    return f"{settings.supabase_url.rstrip('/')}/rest/v1/{path}"


def monthly_allowance(plan: str, is_admin: bool = False) -> int:
    if is_admin:
        return 2500
    return {
        "sin_plan": 0,
        "basico": 100,
        "analista": 500,
        "gold": 1200,
    }.get(plan, 0)


def _wallet_sync(user_id: str, settings: Settings) -> dict:
    defaults = {
        "available": False,
        "balance": 0,
        "monthly_allowance": 0,
        "advanced_chat_cost": settings.ads_coins_advanced_message_cost,
        "advanced_chat_enabled": settings.advanced_ai_enabled,
        "purchases_enabled": settings.ads_coin_purchases_enabled,
        "transactions": [],
    }
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return defaults
    try:
        plan, is_admin = get_profile_flags(user_id, settings)
        allowance = monthly_allowance(plan, is_admin)
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        if allowance > 0:
            httpx.post(
                _rest(settings, "rpc/adjust_ads_coins"),
                json={
                    "p_user_id": user_id,
                    "p_amount": allowance,
                    "p_reason": "plan_monthly_allowance",
                    "p_reference_key": f"plan:{plan}:{month}",
                    "p_metadata": {"plan": plan, "month": month},
                },
                headers=_headers(settings),
                timeout=_TIMEOUT,
            ).raise_for_status()
        else:
            httpx.post(
                _rest(settings, "ads_coin_wallets"),
                json={"user_id": user_id},
                headers={**_headers(settings), "Prefer": "resolution=ignore-duplicates,return=minimal"},
                timeout=_TIMEOUT,
            ).raise_for_status()
        wallet_response = httpx.get(
            _rest(settings, "ads_coin_wallets"),
            params={"user_id": f"eq.{user_id}", "select": "balance,lifetime_earned,lifetime_spent", "limit": "1"},
            headers=_headers(settings),
            timeout=_TIMEOUT,
        )
        wallet_response.raise_for_status()
        rows = wallet_response.json()
        transactions_response = httpx.get(
            _rest(settings, "ads_coin_transactions"),
            params={
                "user_id": f"eq.{user_id}",
                "select": "id,amount,reason,balance_after,created_at",
                "order": "created_at.desc",
                "limit": "10",
            },
            headers=_headers(settings),
            timeout=_TIMEOUT,
        )
        transactions_response.raise_for_status()
        wallet = rows[0] if rows else {}
        return {
            **defaults,
            "available": True,
            "plan": plan,
            "balance": int(wallet.get("balance") or 0),
            "lifetime_earned": int(wallet.get("lifetime_earned") or 0),
            "lifetime_spent": int(wallet.get("lifetime_spent") or 0),
            "monthly_allowance": allowance,
            "transactions": transactions_response.json(),
        }
    except httpx.HTTPError:
        # Despliegue compatible: si la migracion todavia no llego, el resto de
        # la plataforma sigue funcionando y la UI informa que la billetera se
        # encuentra en preparacion.
        return defaults


@router.get("/me")
async def my_ads_coins(
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    return await run_in_threadpool(_wallet_sync, user.id, settings)
