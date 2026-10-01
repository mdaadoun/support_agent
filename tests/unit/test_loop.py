"""Unit tests verifying Step 6.4 ReAct Execution Loop Engine."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.loop import ReActLoopEngine
from agent.state import AgentLifecycleState, create_session
from models.email import InboundEmailMessage
from models.enums import IntentEnum, ResolutionStatusEnum
from models.extraction import ExtractedDemand
from models.llm import LLMResponse, LLMToolCall, LLMUsage
from models.response import ResponseSynthesisOutput
from models.tools import ToolExecutionResult


def _make_inbound_message() -> InboundEmailMessage:
    return InboundEmailMessage(
        message_id="MSG-TEST-001",
        sender_email="alice@example.com",
        subject="Where is my order CMD-12345?",
        body_text="Hello, I would like to know the status of my order CMD-12345.",
        received_at=datetime.now(timezone.utc),
    )


def _make_llm_response(
    content: str | None = None,
    tool_calls: tuple[LLMToolCall, ...] = (),
) -> LLMResponse:
    return LLMResponse(
        content=content,
        tool_calls=tool_calls,
        usage=LLMUsage(
            prompt_tokens=100, completion_tokens=40, total_tokens=140, cost_usd=0.0001
        ),
        model="gpt-4o-mini",
        finish_reason="tool_calls" if tool_calls else "stop",
    )


@pytest.fixture
def mock_llm_client() -> MagicMock:
    client = MagicMock()
    client.generate_with_tools = AsyncMock()
    client.generate_structured = AsyncMock()
    return client


@pytest.fixture
def mock_tool_registry() -> MagicMock:
    registry = MagicMock()
    registry.get_openai_tools.return_value = [
        {"type": "function", "function": {"name": "get_order_details"}}
    ]
    registry.execute = AsyncMock(
        return_value=ToolExecutionResult(
            success=True,
            tool_name="get_order_details",
            data={"order_id": "CMD-12345", "status": "DELIVERED"},
        )
    )
    return registry


@pytest.mark.asyncio
async def test_react_loop_single_tool_execution(
    mock_llm_client: MagicMock,
    mock_tool_registry: MagicMock,
) -> None:
    """Verify single tool execution nominal path through ReAct loop to COMPLETED."""
    session = create_session("SESS-01", _make_inbound_message())
    session.extracted_demand = ExtractedDemand(
        intent=IntentEnum.ORDER_STATUS,
        customer_email="alice@example.com",
        order_id="CMD-12345",
    )

    call_tool = _make_llm_response(
        tool_calls=(
            LLMToolCall(
                id="call_1",
                name="get_order_details",
                arguments={"order_id": "CMD-12345"},
            ),
        )
    )
    finish_loop = _make_llm_response(content="I have obtained the order details.")
    mock_llm_client.generate_with_tools.side_effect = [call_tool, finish_loop]

    mock_llm_client.generate_structured.return_value = ResponseSynthesisOutput(
        intent=IntentEnum.ORDER_STATUS,
        confidence_score=0.95,
        order_id="CMD-12345",
        actions_taken=("get_order_details",),
        status_resolution=ResolutionStatusEnum.RESOLVED_AUTOMATICALLY,
        internal_technical_summary="Order status retrieved successfully.",
        email_response_subject="Order CMD-12345 Status",
        email_response_body="Your order CMD-12345 has been delivered.",
    )

    engine = ReActLoopEngine(
        llm_client=mock_llm_client,
        tool_registry=mock_tool_registry,
        max_iterations=3,
    )
    response = await engine.run(session)

    assert session.current_state == AgentLifecycleState.COMPLETED
    assert response.status_resolution == ResolutionStatusEnum.RESOLVED_AUTOMATICALLY
    assert len(session.tool_traces) == 1
    assert session.iteration_count == 1
    assert response.tokens_prompt > 0


@pytest.mark.asyncio
async def test_react_loop_recursion_ceiling_escalates(
    mock_llm_client: MagicMock,
    mock_tool_registry: MagicMock,
) -> None:
    """Verify exceeding max iterations forces immediate transition to REQUIRES_HUMAN."""
    session = create_session("SESS-RECURSION", _make_inbound_message())
    loop_call = _make_llm_response(
        tool_calls=(
            LLMToolCall(
                id="call_loop",
                name="get_order_details",
                arguments={"order_id": "CMD-12345"},
            ),
        )
    )
    mock_llm_client.generate_with_tools.return_value = loop_call

    engine = ReActLoopEngine(
        llm_client=mock_llm_client,
        tool_registry=mock_tool_registry,
        max_iterations=2,
    )
    response = await engine.run(session)

    assert session.current_state == AgentLifecycleState.REQUIRES_HUMAN
    assert session.escalation_reason == "LOOP_LIMIT_EXCEEDED"
    assert response.status_resolution == ResolutionStatusEnum.REQUIRES_HUMAN_REVIEW
    assert response.human_escalation_reason is not None
    assert "Exceeded maximum tool iterations" in response.human_escalation_reason
    assert session.iteration_count == 2


@pytest.mark.asyncio
async def test_react_loop_low_confidence_escalation(
    mock_llm_client: MagicMock,
    mock_tool_registry: MagicMock,
) -> None:
    """Verify synthesis confidence score below threshold triggers human escalation."""
    session = create_session("SESS-CONF", _make_inbound_message())
    finish_loop = _make_llm_response(content="Uncertain conclusion.")
    mock_llm_client.generate_with_tools.return_value = finish_loop

    mock_llm_client.generate_structured.return_value = ResponseSynthesisOutput(
        intent=IntentEnum.ORDER_STATUS,
        confidence_score=0.60,
        order_id="CMD-12345",
        status_resolution=ResolutionStatusEnum.RESOLVED_AUTOMATICALLY,
        internal_technical_summary="Ambiguous inquiry.",
        email_response_subject="Order Update",
        email_response_body="We need additional human review.",
    )

    engine = ReActLoopEngine(
        llm_client=mock_llm_client,
        tool_registry=mock_tool_registry,
        confidence_threshold=0.85,
    )
    response = await engine.run(session)

    assert session.current_state == AgentLifecycleState.REQUIRES_HUMAN
    assert response.status_resolution == ResolutionStatusEnum.REQUIRES_HUMAN_REVIEW
    assert response.human_escalation_reason is not None
    assert "below threshold" in response.human_escalation_reason


@pytest.mark.asyncio
async def test_react_loop_hostile_tone_fast_escalation(
    mock_llm_client: MagicMock,
    mock_tool_registry: MagicMock,
) -> None:
    """Verify aggressive threats trigger immediate escalation without calling tools."""
    session = create_session("SESS-THREAT", _make_inbound_message())
    session.extracted_demand = ExtractedDemand(
        intent=IntentEnum.REFUND_REQUEST,
        customer_email="alice@example.com",
        is_legal_threat_or_aggressive=True,
    )

    engine = ReActLoopEngine(
        llm_client=mock_llm_client,
        tool_registry=mock_tool_registry,
    )
    response = await engine.run(session)

    assert session.current_state == AgentLifecycleState.REQUIRES_HUMAN
    assert session.escalation_reason == "HOSTILE_OR_LEGAL_THREAT"
    assert response.status_resolution == ResolutionStatusEnum.REQUIRES_HUMAN_REVIEW
    mock_llm_client.generate_with_tools.assert_not_called()


@pytest.mark.asyncio
async def test_react_loop_zero_tool_direct_resolution(
    mock_llm_client: MagicMock,
    mock_tool_registry: MagicMock,
) -> None:
    """Verify inquiry that needs no tools transitions directly to response synthesis."""
    session = create_session("SESS-ZERO-TOOL", _make_inbound_message())
    mock_llm_client.generate_with_tools.return_value = _make_llm_response(
        content="General FAQ answered directly."
    )
    mock_llm_client.generate_structured.return_value = ResponseSynthesisOutput(
        intent=IntentEnum.ORDER_INFORMATION,
        confidence_score=0.92,
        status_resolution=ResolutionStatusEnum.RESOLVED_AUTOMATICALLY,
        internal_technical_summary="Resolved via FAQ.",
        email_response_subject="Order Info",
        email_response_body="Standard delivery takes 3 business days.",
    )

    engine = ReActLoopEngine(
        llm_client=mock_llm_client,
        tool_registry=mock_tool_registry,
    )
    response = await engine.run(session)

    assert session.current_state == AgentLifecycleState.COMPLETED
    assert session.iteration_count == 0
    assert len(session.tool_traces) == 0
    assert response.status_resolution == ResolutionStatusEnum.RESOLVED_AUTOMATICALLY
