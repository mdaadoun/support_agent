"""Idempotency and session caching layer with memory fallback."""

import hashlib
import json
from typing import Any

from core.config import get_settings
from observability.logger import get_logger

logger = get_logger(__name__)


class IdempotencyCache:
    """Provides key hashing and storage for tool calls preventing duplicate runs."""

    def __init__(self, ttl_seconds: int | None = None) -> None:
        settings = get_settings()
        self.ttl_seconds = ttl_seconds or settings.cache_ttl_seconds
        self._in_memory_store: dict[str, str] = {}

    @staticmethod
    def compute_key(session_id: str, tool_name: str, arguments: dict[str, Any]) -> str:
        """Derive deterministic SHA-256 hash key for session and tool arguments."""
        normalized_args = json.dumps(arguments, sort_keys=True)
        raw_key = f"{session_id}:{tool_name}:{normalized_args}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def get(self, key: str) -> str | None:
        """Retrieve cached output by key."""
        return self._in_memory_store.get(key)

    def set(self, key: str, payload: str) -> None:
        """Store output in cache."""
        self._in_memory_store[key] = payload
