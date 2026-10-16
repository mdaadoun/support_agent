"""Unit tests verifying Step 7.1 SessionStateStore, Redis integration, and TTL expiry."""

import time
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from agent.state import (
    AgentLifecycleState,
    AgentSessionState,
    StateTransition,
    create_session,
)
from models.email import InboundEmailMessage
from models.enums import IntentEnum
from models.extraction import ExtractedDemand
from models.session import AgentSessionSnapshot
from models.tools import ToolCallTrace, ToolExecutionResult
from persistence.session_store import SessionStateStore


def _sample_inbound() -> InboundEmailMessage:
    return InboundEmailMessage(
        message_id="MSG-100",
        sender_email="customer@example.com",
        subject="Where is my parcel?",
        body_text="Order CMD-10001 status please.",
        received_at=datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc),
    )


def test_session_snapshot_immutability_and_forbid_extra() -> None:
    """Validate that AgentSessionSnapshot is immutable and forbids extra fields."""
    inbound = _sample_inbound()
    snapshot = AgentSessionSnapshot(
        session_id="SESS-001",
        tenant_id="tenant_x",
        inbound_message=inbound,
        current_state=AgentLifecycleState.RECEIVED,
    )
    assert snapshot.session_id == "SESS-001"
    assert snapshot.tenant_id == "tenant_x"

    with pytest.raises(ValidationError):
        snapshot.session_id = "MUTATED"

    with pytest.raises(ValidationError):
        AgentSessionSnapshot(
            session_id="SESS-002",
            inbound_message=inbound,
            current_state=AgentLifecycleState.RECEIVED,
            unexpected_field="forbidden",  # type: ignore[call-arg]
        )


def test_session_state_snapshot_roundtrip() -> None:
    """Validate lossless conversion between mutable AgentSessionState and immutable AgentSessionSnapshot."""
    session = create_session("SESS-ROUNDTRIP", _sample_inbound(), tenant_id="tenant_rt")
    session.extracted_demand = ExtractedDemand(
        intent=IntentEnum.ORDER_STATUS,
        order_id="CMD-10001",
        customer_email="customer@example.com",
    )
    trace = ToolCallTrace(
        tool_call_id="call-1",
        tool_name="get_order_details",
        arguments={"order_id": "CMD-10001"},
        result=ToolExecutionResult(success=True, tool_name="get_order_details"),
        timestamp=datetime.now(timezone.utc),
        duration_ms=45.2,
    )
    session.record_trace(trace)
    session.record_transition(
        StateTransition(
            from_state=AgentLifecycleState.RECEIVED,
            to_state=AgentLifecycleState.ANALYZING,
            reason="Analysis started",
        )
    )

    snapshot = session.to_snapshot()
    assert isinstance(snapshot, AgentSessionSnapshot)
    assert snapshot.session_id == "SESS-ROUNDTRIP"
    assert snapshot.tenant_id == "tenant_rt"
    assert len(snapshot.tool_traces) == 1
    assert len(snapshot.state_history) == 1

    restored = AgentSessionState.from_snapshot(snapshot)
    assert restored.session_id == session.session_id
    assert restored.tenant_id == session.tenant_id
    assert restored.current_state == session.current_state
    assert len(restored.tool_traces) == 1
    assert len(restored.state_history) == 1
    assert restored.tool_traces[0].tool_name == "get_order_details"


def test_session_store_in_memory_save_and_get() -> None:
    """Validate storing and retrieving sessions in memory fallback store."""
    store = SessionStateStore(ttl_seconds=60)
    session = create_session("SESS-MEM-01", _sample_inbound(), tenant_id="tenant_test")

    assert store.get("SESS-MEM-01", tenant_id="tenant_test") is None
    assert store.exists("SESS-MEM-01", tenant_id="tenant_test") is False

    saved = store.save(session)
    assert saved is True
    assert store.exists("SESS-MEM-01", tenant_id="tenant_test") is True

    snapshot = store.get_snapshot("SESS-MEM-01", tenant_id="tenant_test")
    assert snapshot is not None
    assert snapshot.session_id == "SESS-MEM-01"

    reconstructed = store.get_session("SESS-MEM-01", tenant_id="tenant_test")
    assert reconstructed is not None
    assert reconstructed.session_id == "SESS-MEM-01"
    assert reconstructed.current_state == AgentLifecycleState.RECEIVED


def test_session_store_ttl_expiration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Validate TTL expiration and eviction of cached session state."""
    store = SessionStateStore(ttl_seconds=10)
    current_time = 2000.0
    monkeypatch.setattr(time, "time", lambda: current_time)

    session = create_session("SESS-TTL-01", _sample_inbound())
    store.save(session, ttl_seconds=5)
    assert store.exists("SESS-TTL-01") is True

    current_time = 2006.0
    assert store.get("SESS-TTL-01") is None
    assert store.get_session("SESS-TTL-01") is None
    assert store.exists("SESS-TTL-01") is False


def test_session_store_multi_tenant_isolation() -> None:
    """Validate cross-tenant isolation preventing state leakage across tenants."""
    store = SessionStateStore(ttl_seconds=60)
    sess_a = create_session("SESS-SHARED-ID", _sample_inbound(), tenant_id="tenant_a")
    sess_b = create_session("SESS-SHARED-ID", _sample_inbound(), tenant_id="tenant_b")

    sess_a.iteration_count = 1
    sess_b.iteration_count = 2

    store.save(sess_a)
    store.save(sess_b)

    retrieved_a = store.get_snapshot("SESS-SHARED-ID", tenant_id="tenant_a")
    retrieved_b = store.get_snapshot("SESS-SHARED-ID", tenant_id="tenant_b")

    assert retrieved_a is not None and retrieved_a.iteration_count == 1
    assert retrieved_b is not None and retrieved_b.iteration_count == 2
    assert store.get_snapshot("SESS-SHARED-ID", tenant_id="tenant_c") is None


def test_session_store_delete_and_clear() -> None:
    """Validate session eviction via delete and clear."""
    store = SessionStateStore(ttl_seconds=60)
    session = create_session("SESS-DEL-01", _sample_inbound())

    store.save(session)
    assert store.exists("SESS-DEL-01") is True

    store.delete("SESS-DEL-01")
    assert store.exists("SESS-DEL-01") is False

    store.save(session)
    store.clear()
    assert store.exists("SESS-DEL-01") is False


def test_session_store_corrupt_payload_graceful_handling() -> None:
    """Validate corrupted state payloads return None without raising raw exceptions."""
    store = SessionStateStore(ttl_seconds=60)
    key = store.build_key("SESS-CORRUPT")
    store._in_memory_store[key] = ("{invalid json...", time.time() + 60)

    assert store.get_snapshot("SESS-CORRUPT") is None
    assert store.get_session("SESS-CORRUPT") is None


def test_session_store_mock_redis_integration() -> None:
    """Validate Redis backend interaction with tenant-aware keys and TTL."""
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True

    store = SessionStateStore(
        ttl_seconds=900, redis_client=mock_redis, default_tenant_id="tenant_prod"
    )
    session = create_session(
        "SESS-REDIS-01", _sample_inbound(), tenant_id="tenant_prod"
    )

    store.save(session)
    expected_key = "session:tenant_prod:SESS-REDIS-01"
    assert mock_redis.set.call_count == 1
    args, kwargs = mock_redis.set.call_args
    assert args[0] == expected_key
    assert kwargs.get("ex") == 900

    store.delete("SESS-REDIS-01")
    mock_redis.delete.assert_called_once_with(expected_key)


def test_session_store_redis_failure_falls_back_to_memory() -> None:
    """Validate that Redis connection exceptions fall back gracefully to memory store."""
    mock_redis = MagicMock()
    mock_redis.get.side_effect = ConnectionError("Redis connection dropped")
    mock_redis.set.side_effect = TimeoutError("Redis timed out")

    store = SessionStateStore(ttl_seconds=900, redis_client=mock_redis)
    session = create_session("SESS-FALLBACK-01", _sample_inbound())

    store.save(session)
    retrieved = store.get_session("SESS-FALLBACK-01")
    assert retrieved is not None
    assert retrieved.session_id == "SESS-FALLBACK-01"


@pytest.mark.asyncio
async def test_session_store_async_methods() -> None:
    """Validate async wrapper methods for SessionStateStore."""
    store = SessionStateStore(ttl_seconds=60)
    session = create_session("SESS-ASYNC-01", _sample_inbound())

    await store.save_async(session)
    snapshot = await store.get_snapshot_async("SESS-ASYNC-01")
    assert snapshot is not None

    reconstructed = await store.get_session_async("SESS-ASYNC-01")
    assert reconstructed is not None

    deleted = await store.delete_async("SESS-ASYNC-01")
    assert deleted is True
    assert await store.get_snapshot_async("SESS-ASYNC-01") is None
