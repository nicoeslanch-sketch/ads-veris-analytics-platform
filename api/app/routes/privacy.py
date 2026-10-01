"""Account privacy requests: authenticated ownership, durable receipts, no fake erasure."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..auth import AuthenticatedUser, get_current_user
from ..commercial_rpc import commercial_rpc
from ..config import Settings, get_settings
from ..account_erasure import execute_account_erasure
from .admin import _require_admin_sync

router = APIRouter(prefix="/privacy", tags=["privacy"])
LEGAL_VERSION = "2026-09-28"


class Acceptance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal["2026-09-28"]
    service_data_consent: Literal[True]

    @field_validator('service_data_consent', mode='before')
    @classmethod
    def explicit_consent(cls, value):
        if value is not True:
            raise ValueError('Explicit consent required')
        return value


class PrivacyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["access", "correction", "erasure", "objection"]
    message: str = Field(default="", max_length=2000)
    confirmed: Literal[True]

    @field_validator('confirmed', mode='before')
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError('Explicit confirmation required')
        return value


class PrivacyResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["reviewing", "resolved", "rejected"]
    response: str = Field(min_length=10, max_length=2000)


class ErasureConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: Literal["ELIMINAR CUENTA"]


@router.get("/account")
async def account(response: Response, user: AuthenticatedUser = Depends(get_current_user),
                  settings: Settings = Depends(get_settings)):
    response.headers["Cache-Control"] = "no-store"
    return await run_in_threadpool(commercial_rpc, "account_privacy_state", {"p_user_id": user.id}, settings)


@router.post("/acceptance")
async def accept(body: Acceptance, user: AuthenticatedUser = Depends(get_current_user),
                 settings: Settings = Depends(get_settings)):
    return await run_in_threadpool(commercial_rpc, "accept_account_legal",
                                  {"p_user_id": user.id, "p_version": body.version}, settings)


@router.post("/requests", status_code=202)
async def request(body: PrivacyRequest, user: AuthenticatedUser = Depends(get_current_user),
                  settings: Settings = Depends(get_settings)):
    return await run_in_threadpool(commercial_rpc, "create_privacy_request",
                                  {"p_user_id": user.id, "p_kind": body.kind, "p_message": body.message.strip()}, settings)


@router.get("/admin/requests")
async def admin_requests(response: Response, user: AuthenticatedUser = Depends(get_current_user),
                         settings: Settings = Depends(get_settings)):
    response.headers["Cache-Control"] = "no-store"
    await run_in_threadpool(_require_admin_sync, user.id, settings)
    return await run_in_threadpool(commercial_rpc, "admin_privacy_requests", {"p_admin_id": user.id}, settings)


@router.post("/admin/requests/{request_id}")
async def resolve(request_id: UUID, body: PrivacyResolution, user: AuthenticatedUser = Depends(get_current_user),
                  settings: Settings = Depends(get_settings)):
    await run_in_threadpool(_require_admin_sync, user.id, settings)
    return await run_in_threadpool(commercial_rpc, "resolve_privacy_request",
                                  {"p_admin_id": user.id, "p_request_id": str(request_id),
                                   "p_status": body.status, "p_response": body.response.strip()}, settings)


@router.post("/admin/requests/{request_id}/erase")
async def erase_account(
    request_id: UUID,
    body: ErasureConfirmation,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Execute a confirmed erasure request; safe to retry after partial failure."""
    await run_in_threadpool(_require_admin_sync, user.id, settings)
    return await run_in_threadpool(
        execute_account_erasure,
        user.id,
        str(request_id),
        settings,
    )
