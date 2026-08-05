"""Caché y coordinación opcional compartida para análisis pesados.

Redis/Render Key Value se usa cuando ``ANALYSIS_REDIS_URL`` está configurada.
Desarrollo y despliegues de una sola instancia conservan un fallback local; un
fallo transitorio de Redis degrada capacidad de reutilización, no los cálculos.
"""

from __future__ import annotations

import hashlib
import json
import logging
from functools import lru_cache
from typing import Any
from uuid import uuid4

from redis import Redis
from redis.exceptions import RedisError

from .config import Settings

logger = logging.getLogger(__name__)


def shared_key_digest(key: tuple[Any, ...]) -> str:
    def serializable(value: Any) -> Any:
        if isinstance(value, bytes):
            return {"bytes_sha256": hashlib.sha256(value).hexdigest()}
        if isinstance(value, tuple):
            return [serializable(item) for item in value]
        return value

    payload = json.dumps(
        serializable(key),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class SharedAnalysisCoordinator:
    def __init__(
        self,
        url: str,
        *,
        cache_ttl_seconds: int,
        lock_ttl_seconds: int,
        client: Any | None = None,
    ) -> None:
        self.url = url.strip()
        self.cache_ttl_seconds = cache_ttl_seconds
        self.lock_ttl_seconds = lock_ttl_seconds
        self.client = client or (
            Redis.from_url(
                self.url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=3,
                health_check_interval=30,
            )
            if self.url
            else None
        )

    @property
    def configured(self) -> bool:
        return self.client is not None

    def _cache_key(self, key: tuple[Any, ...]) -> str:
        return f"ads:analysis:result:{shared_key_digest(key)}"

    def _lock_key(self, key: tuple[Any, ...]) -> str:
        return f"ads:analysis:lock:{shared_key_digest(key)}"

    def _job_key(self, user_id: str, job_id: str) -> str:
        return f"ads:analysis:job:{user_id}:{job_id}"

    def get(self, key: tuple[Any, ...]) -> dict[str, Any] | None:
        if self.client is None:
            return None
        try:
            payload = self.client.get(self._cache_key(key))
            return json.loads(payload) if isinstance(payload, str) else None
        except (RedisError, ValueError, TypeError) as exc:
            logger.warning("shared_analysis_get_failed error=%s", exc.__class__.__name__)
            return None

    def store(self, key: tuple[Any, ...], value: dict[str, Any]) -> None:
        if self.client is None:
            return
        try:
            self.client.set(
                self._cache_key(key),
                json.dumps(value, separators=(",", ":"), default=str),
                ex=self.cache_ttl_seconds,
            )
        except (RedisError, TypeError, ValueError) as exc:
            logger.warning("shared_analysis_store_failed error=%s", exc.__class__.__name__)

    def acquire(self, key: tuple[Any, ...]) -> str | bool | None:
        """Devuelve token, False si otra instancia trabaja, None sin Redis."""
        if self.client is None:
            return None
        token = uuid4().hex
        try:
            acquired = self.client.set(
                self._lock_key(key),
                token,
                nx=True,
                ex=self.lock_ttl_seconds,
            )
            return token if acquired else False
        except RedisError as exc:
            logger.warning("shared_analysis_lock_failed error=%s", exc.__class__.__name__)
            return None

    def release(self, key: tuple[Any, ...], token: str | bool | None) -> None:
        if self.client is None or not isinstance(token, str):
            return
        script = (
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end"
        )
        try:
            self.client.eval(script, 1, self._lock_key(key), token)
        except RedisError as exc:
            logger.warning("shared_analysis_unlock_failed error=%s", exc.__class__.__name__)

    def get_job(self, user_id: str, job_id: str) -> dict[str, Any] | None:
        if self.client is None:
            return None
        try:
            payload = self.client.get(self._job_key(user_id, job_id))
            return json.loads(payload) if isinstance(payload, str) else None
        except (RedisError, ValueError, TypeError) as exc:
            logger.warning("shared_analysis_job_get_failed error=%s", exc.__class__.__name__)
            return None

    def store_job(self, user_id: str, job_id: str, value: dict[str, Any]) -> None:
        if self.client is None:
            return
        try:
            self.client.set(
                self._job_key(user_id, job_id),
                json.dumps(value, separators=(",", ":"), default=str),
                ex=self.cache_ttl_seconds,
            )
        except (RedisError, TypeError, ValueError) as exc:
            logger.warning("shared_analysis_job_store_failed error=%s", exc.__class__.__name__)


@lru_cache(maxsize=4)
def _coordinator(
    url: str,
    cache_ttl_seconds: int,
    lock_ttl_seconds: int,
) -> SharedAnalysisCoordinator:
    return SharedAnalysisCoordinator(
        url,
        cache_ttl_seconds=cache_ttl_seconds,
        lock_ttl_seconds=lock_ttl_seconds,
    )


def coordinator_for(settings: Settings) -> SharedAnalysisCoordinator:
    return _coordinator(
        settings.analysis_redis_url,
        settings.analysis_cache_ttl_seconds,
        settings.analysis_lock_ttl_seconds,
    )
