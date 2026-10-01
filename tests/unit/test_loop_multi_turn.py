"""Unit tests verifying multi-turn tool calling and tool failure shielding in ReActLoopEngine."""

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
        message_id="MSG-MULTI-001",
        sender_email="bob@example.com",
        subject="Delay compensation for CMD-99999",
        body_text="My package CMD-99999 was delayed. Am I eligible for voucher?",
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
            prompt_tokens=80, completion_tokens=30, total_tokens=110, cost_usd=0.00008
        ),
        model="gpt-4o-mini",
        finish_reason="tool_calls" if tool_calls else "stop",
    )


@pytest.mark.asyncio
async def test_react_loop_multi_turn_sequence() -> None:
    """Verify multi-step sequential tool calls across multiple ReAct turns."""
    mock_llm = MagicMock()
    mock_tools = MagicMock()

    call_1 = _make_llm_response(
        tool_calls=(
            LLMToolCall(
                id="call_order",
                name="get_order_details",
                arguments={"order_id": "CMD-99999"},
            ),
        )
    )
    call_2 = _make_llm_response(
        tool_calls=(
            LLMToolCall(
                id="call_delay",
                name="calculate_delivery_delay",
                arguments={"order_id": "CMD-99999"},
            ),
        )
    )
    final_turn = _make_llm_response(content="All necessary data gathered.")

    mock_llm.generate_with_tools = AsyncMock(side_effect=[call_1, call_2, final_turn])
    mock_llm.generate_structured = AsyncMock(
        return_value=ResponseSynthesisOutput(
            intent=IntentEnum.DELIVERY_DELAY,
            confidence_score=0.96,
            order_id="CMD-99999",
            actions_taken=("get_order_details", "calculate_delivery_delay"),
            status_resolution=ResolutionStatusEnum.RESOLVED_AUTOMATICALLY,
            internal_technical_summary="Calculated 6 days delay.",
            email_response_subject="Delay Compensation CMD-99999",
            email_response_body="We have granted you a voucher.",
        )
    )

    mock_tools.get_openai_tools.return_value = []
    mock_tools.execute = AsyncMock(
        side_effect=[
            ToolExecutionResult(
                success=True,
                tool_name="get_order_details",
                data={"order_id": "CMD-99999", "status": "DELIVERED"},
            ),
            ToolExecutionResult(
                success=True,
                tool_name="calculate_delivery_delay",
                data={
                    "delay_days": 6,
                    "is_delayed": True,
                    "delay_compensation_voucher_cents": 599,
                },
            ),
        ]
    )

    session = create_session("SESS-MULTI-01", _make_inbound_message())
    session.extracted_demand = ExtractedDemand(
        intent=IntentEnum.DELIVERY_DELAY,
        customer_email="bob@example.com",
        order_id="CMD-99999",
    )

    engine = ReActLoopEngine(
        llm_client=mock_llm,
        tool_registry=mock_tools,
        max_iterations=3,
    )
    response = await engine.run(session)

    assert session.current_state == AgentLifecycleState.COMPLETED
    assert session.iteration_count == 2
    assert len(session.tool_traces) == 2
    assert response.status_resolution == ResolutionStatusEnum.RESOLVED_AUTOMATICALLY
    assert "calculate_delivery_delay" in response.actions_taken


@pytest.mark.asyncio
async def test_react_loop_tool_failure_observation_handling() -> None:
    """Verify tool failures are recorded and do not crash the agent loop."""
    mock_llm = MagicMock()
    mock_tools = MagicMock()

    call_fail = _make_llm_response(
        tool_calls=(
            LLMToolCall(
                id="call_fail",
                name="get_order_details",
                arguments={"order_id": "CMD-MISSING"},
            ),
        )
    )
    final_turn = _make_llm_response(content="Order not found.")

    mock_llm.generate_with_tools = AsyncMock(side_effect=[call_fail, final_turn])
    mock_llm.generate_structured = AsyncMock(
        return_value=ResponseSynthesisOutput(
            intent=IntentEnum.ORDER_STATUS,
            confidence_score=0.91,
            order_id="CMD-MISSING",
            actions_taken=("get_order_details",),
            status_resolution=ResolutionStatusEnum.REQUIRES_HUMAN_REVIEW,
            human_escalation_reason="Order not found in database.",
            internal_technical_summary="Order lookup returned failure.",
            email_response_subject="Order Issue",
            email_response_body="We could not locate your order.",
        )
    )

    mock_tools.get_openai_tools.return_value = []
    mock_tools.execute = AsyncMock(
        return_value=ToolExecutionResult(
            success=False,
            tool_name="get_order_details",
            error_code="ORDER_NOT_FOUND",
            error_message="Order does not exist",
        )
    )

    session = create_session("SESS-FAIL-01", _make_inbound_message())
    engine = ReActLoopEngine(
        llm_client=mock_llm,
        tool_registry=mock_tools,
    )
    response = await engine.run(session)

    assert session.current_state == AgentLifecycleState.REQUIRES_HUMAN
    assert len(session.tool_traces) == 1
    assert session.tool_traces[0].result.success is False
    assert session.tool_traces[0].result.error_code == "ORDER_NOT_FOUND"
    assert response.status_resolution == ResolutionStatusEnum.REQUIRES_HUMAN_REVIEW
