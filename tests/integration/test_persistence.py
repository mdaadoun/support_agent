"""Integration tests verifying Step 7.1 Redis persistence, session states, and idempotency."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agent.controller import AgentFSMController
from agent.state import AgentLifecycleState, create_session
from models.email import InboundEmailMessage
from models.enums import IntentEnum, ResolutionStatusEnum
from models.extraction import ExtractedDemand
from models.response import AgentFinalResponse
from models.tools import ToolCallTrace, ToolExecutionResult
from persistence.cache import IdempotencyCache
from persistence.repository import AuditLogRepository
from persistence.session_store import SessionStateStore


@pytest.fixture
def sample_inbound() -> InboundEmailMessage:
    return InboundEmailMessage(
        message_id="MSG-INT-001",
        sender_email="customer.int@example.com",
        subject="Order inquiry CMD-55555",
        body_text="Where is my order CMD-55555?",
        received_at=datetime.now(timezone.utc),
    )


def test_persistence_session_state_lifecycle_progression(
    sample_inbound: InboundEmailMessage,
) -> None:
    """Validate state store persistence across full FSM lifecycle transitions."""
    store = SessionStateStore(ttl_seconds=900)
    session = create_session(
        "SESS-LIFECYCLE-01", sample_inbound, tenant_id="tenant_int"
    )

    # Step 1: Initial RECEIVED state
    store.save(session)
    stored = store.get_snapshot("SESS-LIFECYCLE-01", tenant_id="tenant_int")
    assert stored is not None and stored.current_state == AgentLifecycleState.RECEIVED

    # Step 2: Transition to ANALYZING
    AgentFSMController.transition(
        session, AgentLifecycleState.ANALYZING, reason="Demand parsed"
    )
    session.extracted_demand = ExtractedDemand(
        intent=IntentEnum.ORDER_STATUS,
        order_id="CMD-55555",
        customer_email="customer.int@example.com",
    )
    store.save(session)

    # Step 3: Transition to EXECUTING_TOOL and record trace
    AgentFSMController.transition(
        session, AgentLifecycleState.EXECUTING_TOOL, reason="Calling order status"
    )
    trace = ToolCallTrace(
        tool_call_id="call-lookup-1",
        tool_name="get_order_details",
        arguments={"order_id": "CMD-55555"},
        result=ToolExecutionResult(
            success=True,
            tool_name="get_order_details",
            data={"status": "IN_TRANSIT"},
        ),
        timestamp=datetime.now(timezone.utc),
        duration_ms=120.5,
    )
    session.record_trace(trace)
    session.iteration_count += 1
    store.save(session)

    # Step 4: Transition to OBSERVING and GENERATING_RESPONSE
    AgentFSMController.transition(
        session, AgentLifecycleState.OBSERVING, reason="Outcome inspected"
    )
    AgentFSMController.transition(
        session, AgentLifecycleState.GENERATING_RESPONSE, reason="Generating response"
    )
    AgentFSMController.transition(
        session, AgentLifecycleState.COMPLETED, reason="Response delivered"
    )
    store.save(session)

    # Reconstruct from storage and verify fidelity
    restored = store.get_session("SESS-LIFECYCLE-01", tenant_id="tenant_int")
    assert restored is not None
    assert restored.current_state == AgentLifecycleState.COMPLETED
    assert restored.is_terminal is True
    assert restored.iteration_count == 1
    assert len(restored.tool_traces) == 1
    assert restored.tool_traces[0].tool_name == "get_order_details"
    assert len(restored.state_history) == 5
    assert restored.state_history[-1].to_state == AgentLifecycleState.COMPLETED


def test_persistence_idempotency_and_session_coexistence(
    sample_inbound: InboundEmailMessage,
) -> None:
    """Validate concurrent operation of IdempotencyCache and SessionStateStore."""
    cache = IdempotencyCache(ttl_seconds=900)
    store = SessionStateStore(ttl_seconds=900)

    session_id = "SESS-COEXIST-01"
    session = create_session(session_id, sample_inbound)
    store.save(session)

    # Tool execution caching
    tool_args = {"order_id": "CMD-55555", "customer_email": "customer.int@example.com"}
    cache_key = cache.compute_key(session_id, "get_order_details", tool_args)
    tool_result = ToolExecutionResult(
        success=True,
        tool_name="get_order_details",
        data={"order_id": "CMD-55555", "status": "DELIVERED"},
    )
    cache.set_result(cache_key, tool_result)

    # Assert both stores maintain their independent state correctly
    assert store.exists(session_id) is True
    assert cache.exists(cache_key) is True

    cached_result = cache.get_result(cache_key)
    assert cached_result is not None
    assert cached_result.data == {"order_id": "CMD-55555", "status": "DELIVERED"}

    stored_session = store.get_session(session_id)
    assert stored_session is not None
    assert stored_session.session_id == session_id


def test_persistence_multi_tenant_cross_boundary_isolation(
    sample_inbound: InboundEmailMessage,
) -> None:
    """Validate multi-tenancy isolation between two distinct tenants sharing session ID."""
    store = SessionStateStore(ttl_seconds=900)
    shared_session_id = "SESS-COLLISION-CANDIDATE"

    session_t1 = create_session(
        shared_session_id, sample_inbound, tenant_id="org_alpha"
    )
    session_t2 = create_session(shared_session_id, sample_inbound, tenant_id="org_beta")

    session_t1.iteration_count = 10
    session_t2.iteration_count = 20

    store.save(session_t1)
    store.save(session_t2)

    res_t1 = store.get_snapshot(shared_session_id, tenant_id="org_alpha")
    res_t2 = store.get_snapshot(shared_session_id, tenant_id="org_beta")

    assert res_t1 is not None and res_t1.iteration_count == 10
    assert res_t2 is not None and res_t2.iteration_count == 20
    assert store.get_snapshot(shared_session_id, tenant_id="org_gamma") is None


def test_persistence_resilience_under_redis_outage(
    sample_inbound: InboundEmailMessage,
) -> None:
    """Validate that storage gracefully falls back to in-memory mode under Redis failures."""
    mock_redis = MagicMock()
    mock_redis.set.side_effect = TimeoutError("Redis socket timeout")
    mock_redis.get.side_effect = ConnectionError("Redis host unreachable")

    store = SessionStateStore(ttl_seconds=900, redis_client=mock_redis)
    session = create_session("SESS-FAIL-RESILIENT", sample_inbound)

    # Save and retrieve should not raise raw third-party exceptions
    saved = store.save(session)
    assert saved is True

    snapshot = store.get_snapshot("SESS-FAIL-RESILIENT")
    assert snapshot is not None
    assert snapshot.session_id == "SESS-FAIL-RESILIENT"


def test_persistence_session_state_and_audit_log_integration(
    tmp_path: Path, sample_inbound: InboundEmailMessage
) -> None:
    """Validate end-to-end integration of SessionStateStore and AuditLogRepository."""
    store = SessionStateStore(ttl_seconds=900)
    audit_file = tmp_path / "test_traces.jsonl"
    audit_repo = AuditLogRepository(fallback_path=audit_file, postgres_dsn=None)

    session_id = "SESS-INTEG-AUDIT-01"
    tenant_id = "tenant_e2e"
    session = create_session(session_id, sample_inbound, tenant_id=tenant_id)
    store.save(session)

    # Simulate completed agent response
    AgentFSMController.transition(
        session, AgentLifecycleState.ANALYZING, reason="Parsed"
    )
    AgentFSMController.transition(
        session, AgentLifecycleState.GENERATING_RESPONSE, reason="Synthesizing"
    )
    AgentFSMController.transition(session, AgentLifecycleState.COMPLETED, reason="Done")
    store.save(session)

    final_resp = AgentFinalResponse(
        session_id=session_id,
        intent=IntentEnum.ORDER_STATUS,
        status_resolution=ResolutionStatusEnum.RESOLVED_AUTOMATICALLY,
        confidence_score=0.98,
        execution_time_seconds=0.35,
        tokens_prompt=250,
        tokens_completion=85,
        cost_estimation_usd=0.0052,
        order_id="CMD-55555",
        email_response_subject="Order Update CMD-55555",
        email_response_body="Your package is arriving tomorrow.",
        internal_technical_summary="Tracking retrieved from carrier.",
    )

    saved = audit_repo.save_response(
        response=final_resp,
        tenant_id=tenant_id,
        customer_email=sample_inbound.sender_email,
        trace_data={"transitions": len(session.state_history)},
    )
    assert saved is True

    # Validate state in both stores
    persisted_session = store.get_session(session_id, tenant_id=tenant_id)
    assert persisted_session is not None
    assert persisted_session.current_state == AgentLifecycleState.COMPLETED

    audit_records = audit_repo.get_by_session_id(session_id, tenant_id=tenant_id)
    assert len(audit_records) == 1
    record = audit_records[0]
    assert record.session_id == session_id
    assert record.tenant_id == tenant_id
    assert record.tokens_prompt == 250
    assert record.tokens_completion == 85
    assert record.cost_usd == 0.0052
    assert record.trace_data == {"transitions": 3}
