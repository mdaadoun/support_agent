"""Thread-safe session state store backed by Redis with memory fallback."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from core.config import get_settings
from models.session import AgentSessionSnapshot
from observability.logger import get_logger
from persistence.redis_client import connect_redis

if TYPE_CHECKING:
    from agent.state import AgentSessionState

logger = get_logger(__name__)

__all__ = [
    "SessionCache",
    "SessionStateStore",
]


class SessionStateStore:
    """Thread-safe session state store backed by Redis with memory fallback."""

    def __init__(
        self,
        ttl_seconds: int | None = None,
        redis_client: Any | None = None,
        redis_url: str | None = None,
        default_tenant_id: str | None = None,
    ) -> None:
        settings = get_settings()
        self.ttl_seconds = ttl_seconds or settings.cache_ttl_seconds
        self._redis_url = redis_url or settings.redis_url
        self._redis = redis_client
        self._redis_initialized = redis_client is not None
        self._in_memory_store: dict[str, tuple[str, float]] = {}
        self.default_tenant_id = default_tenant_id or settings.default_tenant_id

    def _get_redis(self) -> Any | None:
        if self._redis_initialized:
            return self._redis
        self._redis_initialized = True
        self._redis = connect_redis(self._redis_url)
        return self._redis

    def build_key(self, session_id: str, tenant_id: str | None = None) -> str:
        """Derive namespaced tenant partition key for session state."""
        tid = tenant_id or self.default_tenant_id
        return f"session:{tid}:{session_id}"

    def save(
        self,
        session: AgentSessionState | AgentSessionSnapshot,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Persist session state snapshot to Redis and in-memory fallback."""
        ttl = ttl_seconds or self.ttl_seconds
        snapshot = session.to_snapshot() if hasattr(session, "to_snapshot") else session
        if not isinstance(snapshot, AgentSessionSnapshot):
            snapshot = AgentSessionSnapshot.model_validate(snapshot)

        payload = snapshot.model_dump_json()
        key = self.build_key(snapshot.session_id, snapshot.tenant_id)

        client = self._get_redis()
        if client is not None:
            try:
                client.set(key, payload, ex=ttl)
            except Exception as exc:
                logger.warning("redis_session_save_error", key=key, error=str(exc))

        self._in_memory_store[key] = (payload, time.time() + ttl)
        return True

    def get_snapshot(
        self, session_id: str, tenant_id: str | None = None
    ) -> AgentSessionSnapshot | None:
        """Retrieve and reconstruct immutable AgentSessionSnapshot."""
        payload = self.get_raw(session_id, tenant_id)
        if payload is None:
            return None
        try:
            return AgentSessionSnapshot.model_validate_json(payload)
        except Exception as exc:
            logger.warning(
                "session_deserialize_failed", session_id=session_id, error=str(exc)
            )
            return None

    def get(
        self, session_id: str, tenant_id: str | None = None
    ) -> AgentSessionSnapshot | None:
        """Retrieve immutable AgentSessionSnapshot from state store."""
        return self.get_snapshot(session_id, tenant_id)

    def get_session(
        self, session_id: str, tenant_id: str | None = None
    ) -> AgentSessionState | None:
        """Retrieve and reconstruct mutable AgentSessionState container."""
        snapshot = self.get_snapshot(session_id, tenant_id)
        if snapshot is None:
            return None
        from agent.state import AgentSessionState

        return AgentSessionState.from_snapshot(snapshot)

    def get_raw(self, session_id: str, tenant_id: str | None = None) -> str | None:
        """Retrieve raw serialized session JSON string from Redis or memory."""
        key = self.build_key(session_id, tenant_id)
        client = self._get_redis()
        if client is not None:
            try:
                val = client.get(key)
                if val is not None:
                    return str(val)
            except Exception as exc:
                logger.warning("redis_session_get_error", key=key, error=str(exc))

        entry = self._in_memory_store.get(key)
        if entry is None:
            return None
        payload, expires_at = entry
        if time.time() > expires_at:
            self._in_memory_store.pop(key, None)
            return None
        return payload

    def exists(self, session_id: str, tenant_id: str | None = None) -> bool:
        """Check whether active session state exists."""
        return self.get_raw(session_id, tenant_id) is not None

    def delete(self, session_id: str, tenant_id: str | None = None) -> bool:
        """Evict session state from Redis and memory store."""
        key = self.build_key(session_id, tenant_id)
        client = self._get_redis()
        if client is not None:
            try:
                client.delete(key)
            except Exception as exc:
                logger.warning("redis_session_delete_error", key=key, error=str(exc))
        self._in_memory_store.pop(key, None)
        return True

    def clear(self) -> None:
        """Purge internal in-memory session store."""
        self._in_memory_store.clear()

    async def save_async(
        self,
        session: AgentSessionState | AgentSessionSnapshot,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Asynchronously persist session state."""
        return self.save(session, ttl_seconds=ttl_seconds)

    async def get_snapshot_async(
        self, session_id: str, tenant_id: str | None = None
    ) -> AgentSessionSnapshot | None:
        """Asynchronously retrieve AgentSessionSnapshot."""
        return self.get_snapshot(session_id, tenant_id)

    async def get_async(
        self, session_id: str, tenant_id: str | None = None
    ) -> AgentSessionSnapshot | None:
        """Asynchronously retrieve AgentSessionSnapshot."""
        return self.get_snapshot(session_id, tenant_id)

    async def get_session_async(
        self, session_id: str, tenant_id: str | None = None
    ) -> AgentSessionState | None:
        """Asynchronously retrieve AgentSessionState."""
        return self.get_session(session_id, tenant_id)

    async def delete_async(self, session_id: str, tenant_id: str | None = None) -> bool:
        """Asynchronously delete session state."""
        return self.delete(session_id, tenant_id)


SessionCache = SessionStateStore
