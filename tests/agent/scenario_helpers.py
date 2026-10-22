"""Shared scenario fixtures and helper builders for qualification test matrix."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from agent.loop import ReActLoopEngine
from api.service import AgentService
from clients.erp_client import MockERPClient
from models.email import InboundEmailMessage
from models.enums import IntentEnum, ResolutionStatusEnum
from models.llm import LLMResponse, LLMToolCall, LLMUsage
from models.response import ResponseSynthesisOutput
from persistence.repository import AuditLogRepository
from persistence.session_store import SessionStateStore
from tools.registry import create_default_registry

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "mock_orders.json"


def make_email(
    sender: str,
    subject: str,
    body: str,
    message_id: str = "MSG-TC-001",
    received_at: datetime | None = None,
) -> InboundEmailMessage:
    """Create an immutable InboundEmailMessage for testing."""
    return InboundEmailMessage(
        message_id=message_id,
        sender_email=sender,
        subject=subject,
        body_text=body,
        received_at=received_at or datetime.now(timezone.utc),
    )


def llm_tool_call_response(
    tool_calls: list[tuple[str, str, dict[str, Any]]],
    content: str | None = None,
) -> LLMResponse:
    """Create an LLMResponse containing tool call descriptors."""
    calls = tuple(
        LLMToolCall(id=call_id, name=name, arguments=args)
        for call_id, name, args in tool_calls
    )
    return LLMResponse(
        content=content,
        tool_calls=calls,
        usage=LLMUsage(
            prompt_tokens=120, completion_tokens=35, total_tokens=155, cost_usd=0.0001
        ),
        model="gpt-4o-mini",
        finish_reason="tool_calls",
    )


def order_tool_call(call_id: str, order_id: str, email: str) -> LLMResponse:
    """Create an LLMResponse requesting get_order_details tool execution."""
    return llm_tool_call_response(
        [
            (
                call_id,
                "get_order_details",
                {"order_id": order_id, "customer_email": email},
            )
        ]
    )


def llm_text_response(content: str) -> LLMResponse:
    """Create an LLMResponse containing final text content without tool calls."""
    return LLMResponse(
        content=content,
        tool_calls=(),
        usage=LLMUsage(
            prompt_tokens=90, completion_tokens=45, total_tokens=135, cost_usd=0.00009
        ),
        model="gpt-4o-mini",
        finish_reason="stop",
    )


def make_synthesis(
    intent: IntentEnum,
    subject: str,
    body: str,
    order_id: str | None = None,
    resolution: ResolutionStatusEnum = ResolutionStatusEnum.RESOLVED_AUTOMATICALLY,
    escalation_reason: str | None = None,
    confidence: float = 0.95,
) -> ResponseSynthesisOutput:
    """Create a structured ResponseSynthesisOutput object."""
    return ResponseSynthesisOutput(
        intent=intent,
        confidence_score=confidence,
        order_id=order_id,
        status_resolution=resolution,
        human_escalation_reason=escalation_reason,
        internal_technical_summary=f"Processed {intent.value} for {order_id or 'ticket'}",
        email_response_subject=subject,
        email_response_body=body,
    )


def build_scenario_service(
    mock_llm: MagicMock,
    erp_client: MockERPClient | None = None,
    max_iterations: int = 3,
) -> tuple[AgentService, MockERPClient]:
    """Assemble a configured AgentService wired with mock LLM and test ERP data."""
    erp = erp_client or MockERPClient(data_path=FIXTURE_PATH)
    registry = create_default_registry(erp_client=erp)
    engine = ReActLoopEngine(
        llm_client=mock_llm,
        tool_registry=registry,
        max_iterations=max_iterations,
    )
    session_store = SessionStateStore(redis_client=None)
    audit_repo = AuditLogRepository(
        fallback_path=Path("/tmp/traces_scenario_test.jsonl")
    )
    service = AgentService(
        engine=engine,
        session_store=session_store,
        audit_repo=audit_repo,
    )
    return service, erp
