"""Unit tests verifying Zero LLM Authority validation guard."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.loop import ReActLoopEngine
from agent.state import AgentLifecycleState, create_session
from agent.validator import ZeroLLMAuthorityGuard
from agent.validator_rules import (
    detect_approval_claims,
    extract_certified_amounts,
    extract_monetary_amounts,
)
from core.exceptions import LLMAuthorityViolationError
from models.email import InboundEmailMessage
from models.enums import IntentEnum, ResolutionStatusEnum
from models.extraction import ExtractedDemand
from models.llm import LLMResponse, LLMUsage
from models.response import AgentFinalResponse, ResponseSynthesisOutput
from models.tools import ToolCallTrace, ToolExecutionResult


def _make_inbound() -> InboundEmailMessage:
    return InboundEmailMessage(
        message_id="MSG-AUTH-01",
        sender_email="alice@example.com",
        subject="Refund inquiry for CMD-12345",
        body_text="I want a refund for my order CMD-12345.",
        received_at=datetime.now(timezone.utc),
    )


def _make_trace(
    tool_name: str,
    data: dict[str, object] | None = None,
    success: bool = True,
    error_code: str | None = None,
) -> ToolCallTrace:
    return ToolCallTrace(
        tool_call_id="call-01",
        tool_name=tool_name,
        arguments={},
        result=ToolExecutionResult(
            success=success,
            tool_name=tool_name,
            data=data,
            error_code=error_code,
        ),
        timestamp=datetime.now(timezone.utc),
        duration_ms=12.5,
    )


def _make_final_response(
    subject: str = "Order Update",
    body: str = "Standard inquiry response.",
    status: ResolutionStatusEnum = ResolutionStatusEnum.RESOLVED_AUTOMATICALLY,
    reason: str | None = None,
) -> AgentFinalResponse:
    return AgentFinalResponse(
        session_id="SESS-01",
        intent=IntentEnum.ORDER_STATUS,
        confidence_score=0.95,
        actions_taken=("get_order_details",),
        status_resolution=status,
        human_escalation_reason=reason,
        internal_technical_summary="Internal trace summary.",
        email_response_subject=subject,
        email_response_body=body,
    )


def test_monetary_amount_extraction() -> None:
    """Test extracting currency symbols, words, and cents."""
    text = "Refund of €150.00 and shipping 5€ or $50.25 and 500 cents."
    extracted = extract_monetary_amounts(text)
    cents_list = [c for _, c in extracted]
    assert 15000 in cents_list
    assert 500 in cents_list
    assert 5025 in cents_list
    assert extract_monetary_amounts("Order CMD-12345 with 14 days delay.") == []


def test_approval_claims_negation_vs_affirmative() -> None:
    """Test affirmative approval detection and negation filtering."""
    affirmative = "Your refund of €150 has been approved."
    assert "refund_approval" in detect_approval_claims(affirmative)

    negated = "Your return cannot be approved because the deadline expired."
    assert detect_approval_claims(negated) == []


def test_certified_amounts_extraction() -> None:
    """Test extracting certified numbers and sums from tool traces."""
    trace = _make_trace(
        "calculate_refund_eligibility",
        {
            "refundable_items_total_cents": 12000,
            "delay_compensation_voucher_cents": 500,
        },
    )
    certified = extract_certified_amounts([trace])
    assert 12000 in certified
    assert 500 in certified
    assert 12500 in certified
    assert 0 in certified


def test_guard_validates_certified_monetary_amount() -> None:
    """Verify response matching certified amount passes validation."""
    guard = ZeroLLMAuthorityGuard()
    trace = _make_trace(
        "calculate_refund_eligibility",
        {"refundable_items_total_cents": 15000, "is_eligible_for_return": True},
    )
    resp = _make_final_response(
        body="Your return has been approved. A refund of €150.00 is issued."
    )
    res = guard.validate(resp, [trace])
    assert res.is_valid is True
    assert len(res.violations) == 0


def test_guard_rejects_uncertified_monetary_amount() -> None:
    """Verify hallucinated or injection-driven amounts are blocked."""
    guard = ZeroLLMAuthorityGuard()
    trace = _make_trace(
        "calculate_refund_eligibility",
        {"refundable_items_total_cents": 5000, "is_eligible_for_return": True},
    )
    resp = _make_final_response(body="We have approved your refund of €500.00.")
    res = guard.validate(resp, [trace])
    assert res.is_valid is False
    assert any("Uncertified monetary figure" in v for v in res.violations)


def test_guard_rejects_unauthorized_refund_approval() -> None:
    """Verify refund approval claim without tool eligibility is blocked."""
    guard = ZeroLLMAuthorityGuard()
    trace = _make_trace(
        "calculate_refund_eligibility",
        {"refundable_items_total_cents": 0, "is_eligible_for_return": False},
    )
    resp = _make_final_response(body="Your refund has been approved.")
    res = guard.validate(resp, [trace])
    assert res.is_valid is False
    assert any("Unauthorized refund approval" in v for v in res.violations)


def test_guard_rejects_mutation_and_security_breach() -> None:
    """Verify operational mutations and unhandled security breaches are blocked."""
    guard = ZeroLLMAuthorityGuard()
    resp = _make_final_response(body="We have cancelled your order for you.")
    res = guard.validate(resp, [])
    assert res.is_valid is False
    assert any("Unauthorized operational mutation" in v for v in res.violations)

    sec_trace = _make_trace(
        "get_order_details", success=False, error_code="SECURITY_UNAUTHORIZED_ACCESS"
    )
    normal_resp = _make_final_response(body="Everything is fine.")
    sec_res = guard.validate(normal_resp, [sec_trace])
    assert sec_res.is_valid is False
    assert any("Security violation" in v for v in sec_res.violations)


def test_verify_authority_raises_exception() -> None:
    """Verify verify_authority raises LLMAuthorityViolationError on violation."""
    guard = ZeroLLMAuthorityGuard()
    resp = _make_final_response(body="We will refund €999.00.")
    with pytest.raises(LLMAuthorityViolationError) as exc_info:
        guard.verify_authority(resp, [])
    assert "LLM Authority validation failed" in str(exc_info.value)
    assert len(exc_info.value.violations) > 0


def test_guard_response_safely_downgrades() -> None:
    """Verify guard_response escalates to human review with safe body."""
    guard = ZeroLLMAuthorityGuard()
    resp = _make_final_response(body="We have processed your €500 refund.")
    escalated, res = guard.guard_response(resp, [])
    assert res.is_valid is False
    assert escalated.status_resolution == ResolutionStatusEnum.REQUIRES_HUMAN_REVIEW
    assert "AUTHORITY_VIOLATION" in (escalated.human_escalation_reason or "")
    assert "€500" not in escalated.email_response_body


@pytest.mark.asyncio
async def test_react_loop_escalates_on_authority_breach() -> None:
    """Verify end-to-end ReAct loop escalates FSM when model hallucinates unauthorized refund."""
    mock_llm = MagicMock()
    mock_tools = MagicMock()
    mock_llm.generate_with_tools = AsyncMock(
        return_value=LLMResponse(
            content="Direct resolution without tools.",
            tool_calls=(),
            usage=LLMUsage(
                prompt_tokens=50,
                completion_tokens=20,
                total_tokens=70,
                cost_usd=0.00005,
            ),
            model="gpt-4o-mini",
        )
    )
    mock_llm.generate_structured = AsyncMock(
        return_value=ResponseSynthesisOutput(
            intent=IntentEnum.REFUND_REQUEST,
            confidence_score=0.95,
            status_resolution=ResolutionStatusEnum.RESOLVED_AUTOMATICALLY,
            internal_technical_summary="Hallucinated uncertified refund.",
            email_response_subject="Refund Update",
            email_response_body="We have approved your refund of €500.",
        )
    )

    session = create_session("SESS-BREACH", _make_inbound())
    session.extracted_demand = ExtractedDemand(
        intent=IntentEnum.REFUND_REQUEST,
        customer_email="alice@example.com",
    )
    engine = ReActLoopEngine(llm_client=mock_llm, tool_registry=mock_tools)
    response = await engine.run(session)

    assert session.current_state == AgentLifecycleState.REQUIRES_HUMAN
    assert response.status_resolution == ResolutionStatusEnum.REQUIRES_HUMAN_REVIEW
    assert "AUTHORITY_VIOLATION" in (response.human_escalation_reason or "")
    assert "€500" not in response.email_response_body
