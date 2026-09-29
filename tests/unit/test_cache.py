"""Unit tests verifying IdempotencyCache hashing, Redis integration, and memory fallback."""

import time
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from models.tools import ToolExecutionResult
from persistence.cache import IdempotencyCache


def test_idempotency_cache_compute_key_deterministic() -> None:
    """Validate that argument dictionary key ordering does not alter the hash."""
    args_a = {"b": 2, "a": 1, "c": [3, 4]}
    args_b = {"a": 1, "c": [3, 4], "b": 2}

    key_a = IdempotencyCache.compute_key("sess-1", "test_tool", args_a)
    key_b = IdempotencyCache.compute_key("sess-1", "test_tool", args_b)
    assert key_a == key_b
    assert len(key_a) == 64  # SHA-256 hex digest

    # Different session yields different key
    key_other_sess = IdempotencyCache.compute_key("sess-2", "test_tool", args_a)
    assert key_a != key_other_sess

    # Different tool name yields different key
    key_other_tool = IdempotencyCache.compute_key("sess-1", "other_tool", args_a)
    assert key_a != key_other_tool


def test_idempotency_cache_compute_key_with_datetime() -> None:
    """Validate serialization of datetime and complex objects during hashing."""
    dt = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)
    key = IdempotencyCache.compute_key("sess-1", "tool", {"date": dt})
    assert isinstance(key, str)
    assert len(key) == 64


def test_idempotency_cache_in_memory_get_set_clear() -> None:
    """Validate basic in-memory caching operations."""
    cache = IdempotencyCache(ttl_seconds=60)
    assert cache.get("missing_key") is None
    assert cache.exists("missing_key") is False

    cache.set("k1", "payload_1")
    assert cache.get("k1") == "payload_1"
    assert cache.exists("k1") is True

    cache.clear()
    assert cache.get("k1") is None


def test_idempotency_cache_in_memory_ttl_expiration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validate that expired entries are evicted upon access."""
    cache = IdempotencyCache(ttl_seconds=10)
    current_time = 1000.0
    monkeypatch.setattr(time, "time", lambda: current_time)

    cache.set("k1", "temp_payload", ttl_seconds=5)
    assert cache.get("k1") == "temp_payload"

    # Advance time past TTL
    current_time = 1006.0
    assert cache.get("k1") is None
    assert cache.exists("k1") is False


@pytest.mark.asyncio
async def test_idempotency_cache_tool_execution_result_roundtrip() -> None:
    """Validate serialization and deserialization of ToolExecutionResult."""
    cache = IdempotencyCache(ttl_seconds=60)
    result = ToolExecutionResult(
        success=True,
        tool_name="get_order_details",
        data={"order_id": "CMD-10001", "status": "DELIVERED"},
    )

    await cache.set_result_async("key_res", result)
    cached = await cache.get_result_async("key_res")

    assert cached is not None
    assert cached.success is True
    assert cached.tool_name == "get_order_details"
    assert cached.data == {"order_id": "CMD-10001", "status": "DELIVERED"}
    assert cached.error_code is None


def test_idempotency_cache_corrupt_payload_graceful_handling() -> None:
    """Validate corrupted cache values return None instead of raising exceptions."""
    cache = IdempotencyCache(ttl_seconds=60)
    cache.set("corrupt_key", "{invalid json...")

    assert cache.get_result("corrupt_key") is None


def test_idempotency_cache_mock_redis_integration() -> None:
    """Validate interaction with Redis backend including NX and EX options."""
    mock_redis = MagicMock()
    mock_redis.get.return_value = '{"cached": true}'
    mock_redis.set.return_value = True

    cache = IdempotencyCache(ttl_seconds=900, redis_client=mock_redis)

    # Test set
    cache.set("hash123", '{"cached": true}')
    mock_redis.set.assert_called_once_with(
        "idempotency:hash123", '{"cached": true}', ex=900, nx=True
    )

    # Test get
    res = cache.get("hash123")
    assert res == '{"cached": true}'
    mock_redis.get.assert_called_once_with("idempotency:hash123")


def test_idempotency_cache_redis_error_falls_back_to_memory() -> None:
    """Validate that Redis connection exceptions fall back gracefully to memory store."""
    mock_redis = MagicMock()
    mock_redis.get.side_effect = ConnectionError("Redis connection dropped")
    mock_redis.set.side_effect = TimeoutError("Redis timed out")

    cache = IdempotencyCache(ttl_seconds=900, redis_client=mock_redis)

    # Set should fail Redis and fall back to in-memory store
    cache.set("hash_err", "fallback_data")
    # Get should fail Redis and retrieve from in-memory store
    assert cache.get("hash_err") == "fallback_data"
