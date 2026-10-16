"""Unit tests for AuditLogRecord and AuditLogRepository."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from models.audit import AuditLogRecord
from models.enums import IntentEnum, ResolutionStatusEnum
from models.response import AgentFinalResponse
from persistence.postgres_client import INSERT_AUDIT_LOG_SQL, ensure_audit_table_exists
from persistence.repository import AuditLogRepository


@pytest.fixture
def sample_response() -> AgentFinalResponse:
    return AgentFinalResponse(
        session_id="SESS-AUDIT-01",
        intent=IntentEnum.ORDER_STATUS,
        status_resolution=ResolutionStatusEnum.RESOLVED_AUTOMATICALLY,
        confidence_score=0.95,
        execution_time_seconds=0.45,
        tokens_prompt=120,
        tokens_completion=60,
        cost_estimation_usd=0.0035,
        order_id="CMD-12345",
        email_response_subject="Order Update",
        email_response_body="Your order is in transit.",
        internal_technical_summary="Lookup succeeded.",
    )


def test_audit_log_record_immutability(sample_response: AgentFinalResponse) -> None:
    """Verify AuditLogRecord enforces frozen and extra='forbid' constraints."""
    record = AuditLogRecord.from_response(sample_response, tenant_id="tenant_a")
    assert record.session_id == "SESS-AUDIT-01"
    assert record.duration_ms == 450.0

    with pytest.raises(ValidationError):
        setattr(record, "session_id", "NEW-ID")  # noqa: B010

    with pytest.raises(ValidationError):
        AuditLogRecord(
            session_id="SESS-02",
            intent=IntentEnum.ORDER_STATUS,
            status_resolution=ResolutionStatusEnum.RESOLVED_AUTOMATICALLY,
            confidence_score=0.9,
            unexpected_field="disallowed",  # type: ignore[call-arg]
        )


def test_repository_save_and_retrieve_jsonl(
    tmp_path: Path, sample_response: AgentFinalResponse
) -> None:
    """Validate persistence to and query from JSON Lines fallback."""
    log_file = tmp_path / "traces.jsonl"
    repo = AuditLogRepository(fallback_path=log_file, postgres_dsn=None)

    record = AuditLogRecord.from_response(
        sample_response,
        tenant_id="tenant_test",
        message_id="MSG-100",
        trace_data={"step": "tool_executed"},
    )
    assert repo.save(record) is True
    assert log_file.exists()

    with open(log_file, encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]
    assert len(lines) == 1
    assert lines[0]["session_id"] == "SESS-AUDIT-01"
    assert lines[0]["trace_data"] == {"step": "tool_executed"}

    retrieved = repo.get_by_session_id("SESS-AUDIT-01", tenant_id="tenant_test")
    assert len(retrieved) == 1
    assert retrieved[0].session_id == "SESS-AUDIT-01"
    assert retrieved[0].tenant_id == "tenant_test"


def test_repository_tenant_isolation(
    tmp_path: Path, sample_response: AgentFinalResponse
) -> None:
    """Validate records from different tenants are isolated."""
    log_file = tmp_path / "traces.jsonl"
    repo = AuditLogRepository(fallback_path=log_file, postgres_dsn=None)

    repo.save_response(sample_response, tenant_id="tenant_alpha")
    repo.save_response(sample_response, tenant_id="tenant_beta")

    alpha_records = repo.get_by_session_id("SESS-AUDIT-01", tenant_id="tenant_alpha")
    beta_records = repo.get_by_session_id("SESS-AUDIT-01", tenant_id="tenant_beta")
    gamma_records = repo.get_by_session_id("SESS-AUDIT-01", tenant_id="tenant_gamma")

    assert len(alpha_records) == 1
    assert alpha_records[0].tenant_id == "tenant_alpha"
    assert len(beta_records) == 1
    assert beta_records[0].tenant_id == "tenant_beta"
    assert len(gamma_records) == 0


def test_repository_postgres_save_and_query(
    tmp_path: Path, sample_response: AgentFinalResponse
) -> None:
    """Validate SQL execution and row deserialization when DB connection is active."""
    log_file = tmp_path / "traces.jsonl"
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    repo = AuditLogRepository(fallback_path=log_file, db_connection=mock_conn)
    record = AuditLogRecord.from_response(sample_response, tenant_id="tenant_pg")

    assert repo.save(record) is True
    assert mock_cursor.execute.call_count >= 1
    call_sql, call_params = mock_cursor.execute.call_args[0]
    assert call_sql == INSERT_AUDIT_LOG_SQL
    assert call_params["session_id"] == "SESS-AUDIT-01"
    assert call_params["tenant_id"] == "tenant_pg"
    mock_conn.commit.assert_called()

    # Query path with mocked rows
    mock_cursor.fetchall.return_value = [
        {
            "session_id": "SESS-AUDIT-01",
            "tenant_id": "tenant_pg",
            "message_id": None,
            "customer_email": "user@example.com",
            "order_id": "CMD-12345",
            "intent": "ORDER_STATUS",
            "status_resolution": "RESOLVED_AUTOMATICALLY",
            "confidence_score": 0.95,
            "duration_ms": 450.0,
            "tokens_prompt": 120,
            "tokens_completion": 60,
            "cost_usd": 0.0035,
            "human_escalation_reason": None,
            "internal_technical_summary": "Lookup succeeded.",
            "trace_data": json.dumps({"db": True}),
            "created_at": datetime.now(timezone.utc),
        }
    ]
    results = repo.get_by_session_id("SESS-AUDIT-01", tenant_id="tenant_pg")
    assert len(results) == 1
    assert results[0].session_id == "SESS-AUDIT-01"
    assert results[0].trace_data == {"db": True}


def test_repository_resilience_on_postgres_failure(
    tmp_path: Path, sample_response: AgentFinalResponse
) -> None:
    """Validate postgres exceptions fall back to JSONL without crashing."""
    log_file = tmp_path / "traces.jsonl"
    broken_conn = MagicMock()
    broken_cursor = MagicMock()
    broken_cursor.execute.side_effect = RuntimeError("Postgres pool exhausted")
    broken_conn.cursor.return_value.__enter__.return_value = broken_cursor

    repo = AuditLogRepository(fallback_path=log_file, db_connection=broken_conn)
    record = AuditLogRecord.from_response(sample_response, tenant_id="tenant_resilient")

    # Should not raise exception
    assert repo.save(record) is True
    assert log_file.exists()

    # Query fallback works
    retrieved = repo.get_by_session_id("SESS-AUDIT-01", tenant_id="tenant_resilient")
    assert len(retrieved) == 1
    assert retrieved[0].session_id == "SESS-AUDIT-01"


def test_repository_clear(tmp_path: Path, sample_response: AgentFinalResponse) -> None:
    """Validate clearing in-memory records and truncating fallback file."""
    log_file = tmp_path / "traces.jsonl"
    repo = AuditLogRepository(fallback_path=log_file, postgres_dsn=None)
    repo.save_response(sample_response)
    assert len(repo.get_by_session_id("SESS-AUDIT-01")) == 1

    repo.clear()
    assert len(repo.get_by_session_id("SESS-AUDIT-01")) == 0
    assert log_file.read_text(encoding="utf-8") == ""


def test_ensure_audit_table_exists_success_and_failure() -> None:
    """Test ensure_audit_table_exists helper under normal and failure modes."""
    mock_conn = MagicMock()
    assert ensure_audit_table_exists(mock_conn) is True

    failing_conn = MagicMock()
    failing_conn.cursor.side_effect = RuntimeError("DDL execute failed")
    assert ensure_audit_table_exists(failing_conn) is False


@pytest.mark.asyncio
async def test_repository_async_methods(
    tmp_path: Path, sample_response: AgentFinalResponse
) -> None:
    """Validate async wrapper methods work asynchronously."""
    log_file = tmp_path / "traces.jsonl"
    repo = AuditLogRepository(fallback_path=log_file, postgres_dsn=None)

    saved = await repo.save_response_async(sample_response, tenant_id="tenant_async")
    assert saved is True

    records = await repo.get_by_session_id_async(
        "SESS-AUDIT-01", tenant_id="tenant_async"
    )
    assert len(records) == 1
    assert records[0].tenant_id == "tenant_async"
