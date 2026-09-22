"""Shared abuse limits for account writes, with no raw identities in buckets."""

import hashlib

from fastapi import HTTPException

from .commercial_rpc import commercial_rpc
from .config import Settings


def consume_budget(bucket: str, settings: Settings, *, limit: int, window: int) -> None:
    result = commercial_rpc('consume_request_budget', {
        'p_bucket_hash': hashlib.sha256(bucket.encode('utf-8')).hexdigest(),
        'p_limit': limit, 'p_window_seconds': window,
    }, settings)
    if not isinstance(result, dict) or type(result.get('allowed')) is not bool:
        raise HTTPException(503, 'No se pudo verificar el limite de solicitudes. Reintenta mas tarde.')
    if not result['allowed']:
        retry = result.get('retry_after')
        if type(retry) is not int or not 1 <= retry <= 3600:
            raise HTTPException(503, 'No se pudo verificar el limite de solicitudes.')
        raise HTTPException(429, 'Demasiados intentos. Espera antes de volver a intentar.',
                            headers={'Retry-After': str(retry)})
