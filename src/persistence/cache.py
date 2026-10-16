"""Idempotency and session caching layer with memory fallback."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from core.config import get_settings
from models.tools import ToolExecutionResult
from observability.logger import get_logger
from persistence.redis_client import connect_redis, json_serializer
from persistence.session_store import SessionCache, SessionStateStore

logger = get_logger(__name__)

__all__ = [
    "IdempotencyCache",
    "SessionCache",
    "SessionStateStore",
]


class IdempotencyCache:
    """Thread-safe idempotency caching backed by Redis with memory fallback."""

    def __init__(
        self,
        ttl_seconds: int | None = None,
        redis_client: Any | None = None,
        redis_url: str | None = None,
    ) -> None:
        settings = get_settings()
        self.ttl_seconds = ttl_seconds or settings.cache_ttl_seconds
        self._redis_url = redis_url or settings.redis_url
        self._redis = redis_client
        self._redis_initialized = redis_client is not None
        self._in_memory_store: dict[str, tuple[str, float]] = {}

    def _get_redis(self) -> Any | None:
        if self._redis_initialized:
            return self._redis
        self._redis_initialized = True
        self._redis = connect_redis(self._redis_url)
        return self._redis

    @staticmethod
    def compute_key(session_id: str, tool_name: str, arguments: dict[str, Any]) -> str:
        """Derive deterministic SHA-256 hash key for session and tool arguments."""
        normalized_args = json.dumps(arguments, sort_keys=True, default=json_serializer)
        raw_key = f"{session_id}:{tool_name}:{normalized_args}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def get(self, key: str) -> str | None:
        """Retrieve cached output by key from Redis or in-memory store."""
        client = self._get_redis()
        if client is not None:
            try:
                val = client.get(f"idempotency:{key}")
                if val is not None:
                    return str(val)
            except Exception as exc:
                logger.warning("redis_get_error", key=key, error=str(exc))

        entry = self._in_memory_store.get(key)
        if entry is None:
            return None
        payload, expires_at = entry
        if time.time() > expires_at:
            self._in_memory_store.pop(key, None)
            return None
        return payload

    def set(self, key: str, payload: str, ttl_seconds: int | None = None) -> bool:
        """Store output in Redis (with NX and EX) and in-memory store."""
        ttl = ttl_seconds or self.ttl_seconds
        client = self._get_redis()
        if client is not None:
            try:
                client.set(f"idempotency:{key}", payload, ex=ttl, nx=True)
            except Exception as exc:
                logger.warning("redis_set_error", key=key, error=str(exc))

        self._in_memory_store[key] = (payload, time.time() + ttl)
        return True

    def exists(self, key: str) -> bool:
        """Return True if active cache entry exists for key."""
        return self.get(key) is not None

    def clear(self) -> None:
        """Purge internal memory store."""
        self._in_memory_store.clear()

    def get_result(self, key: str) -> ToolExecutionResult | None:
        """Retrieve and deserialize ToolExecutionResult from cache."""
        payload = self.get(key)
        if payload is None:
            return None
        try:
            return ToolExecutionResult.model_validate_json(payload)
        except Exception as exc:
            logger.warning("cache_deserialize_failed", key=key, error=str(exc))
            return None

    def set_result(
        self,
        key: str,
        result: ToolExecutionResult,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Serialize and store ToolExecutionResult in cache."""
        return self.set(key, result.model_dump_json(), ttl_seconds=ttl_seconds)

    async def get_result_async(self, key: str) -> ToolExecutionResult | None:
        """Asynchronously retrieve cached ToolExecutionResult."""
        return self.get_result(key)

    async def set_result_async(
        self,
        key: str,
        result: ToolExecutionResult,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Asynchronously store ToolExecutionResult in cache."""
        return self.set_result(key, result, ttl_seconds=ttl_seconds)
