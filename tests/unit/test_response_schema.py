"""Unit tests verifying AgentFinalResponse schema contracts and boundary validations."""

import pytest
from pydantic import ValidationError

from models.enums import IntentEnum, ResolutionStatusEnum
from models.response import AgentFinalResponse


def test_agent_final_response_resolved_automatically() -> None:
    """Validate nominal certified response with automatic resolution."""
    resp = AgentFinalResponse(
        session_id="session-001",
        intent=IntentEnum.ORDER_STATUS,
        confidence_score=0.95,
        order_id="CMD-10001",
        actions_taken=("get_order_details",),
        status_resolution=ResolutionStatusEnum.RESOLVED_AUTOMATICALLY,
        internal_technical_summary="Order is delivered on time via Colissimo.",
        email_response_subject="Order Update CMD-10001",
        email_response_body="Your order CMD-10001 was delivered.",
        tokens_prompt=450,
        tokens_completion=120,
        cost_estimation_usd=0.0032,
        execution_time_seconds=1.24,
    )
    assert resp.session_id == "session-001"
    assert resp.confidence_score == 0.95
    assert resp.actions_taken == ("get_order_details",)
    assert resp.status_resolution == ResolutionStatusEnum.RESOLVED_AUTOMATICALLY
    assert resp.human_escalation_reason is None
    assert resp.tokens_prompt == 450
    assert resp.cost_estimation_usd == 0.0032


def test_agent_final_response_escalation_requires_reason() -> None:
    """Validate human escalation requires non-empty human_escalation_reason."""
    # Successful escalation when reason is provided
    resp = AgentFinalResponse(
        session_id="session-002",
        intent=IntentEnum.ORDER_STATUS,
        confidence_score=0.40,
        status_resolution=ResolutionStatusEnum.REQUIRES_HUMAN_REVIEW,
        human_escalation_reason="Sender email does not match customer account.",
        internal_technical_summary="PII mismatch detected.",
        email_response_subject="Ticket Escalate",
        email_response_body="Your request has been forwarded to a human representative.",
    )
    assert (
        resp.human_escalation_reason == "Sender email does not match customer account."
    )

    # Missing reason when REQUIRES_HUMAN_REVIEW must raise ValidationError
    with pytest.raises(ValidationError):
        AgentFinalResponse(
            session_id="session-003",
            intent=IntentEnum.ORDER_STATUS,
            confidence_score=0.30,
            status_resolution=ResolutionStatusEnum.REQUIRES_HUMAN_REVIEW,
            human_escalation_reason=None,
            internal_technical_summary="Missing reason.",
            email_response_subject="Escalate",
            email_response_body="Escalating.",
        )

    # Empty string reason must also raise ValidationError
    with pytest.raises(ValidationError):
        AgentFinalResponse(
            session_id="session-004",
            intent=IntentEnum.ORDER_STATUS,
            confidence_score=0.30,
            status_resolution=ResolutionStatusEnum.REQUIRES_HUMAN_REVIEW,
            human_escalation_reason="   ",
            internal_technical_summary="Blank reason.",
            email_response_subject="Escalate",
            email_response_body="Escalating.",
        )


@pytest.mark.parametrize("score", [-0.01, 1.01, 2.5])
def test_agent_final_response_confidence_score_bounds(score: float) -> None:
    """Validate confidence_score is bounded between 0.0 and 1.0."""
    with pytest.raises(ValidationError):
        AgentFinalResponse(
            session_id="session-005",
            intent=IntentEnum.ORDER_STATUS,
            confidence_score=score,
            status_resolution=ResolutionStatusEnum.RESOLVED_AUTOMATICALLY,
            internal_technical_summary="Confidence check.",
            email_response_subject="Sub",
            email_response_body="Body",
        )


def test_agent_final_response_summary_max_length() -> None:
    """Validate internal_technical_summary rejects strings longer than 250 chars."""
    long_summary = "A" * 251
    with pytest.raises(ValidationError):
        AgentFinalResponse(
            session_id="session-006",
            intent=IntentEnum.ORDER_STATUS,
            confidence_score=0.9,
            status_resolution=ResolutionStatusEnum.RESOLVED_AUTOMATICALLY,
            internal_technical_summary=long_summary,
            email_response_subject="Sub",
            email_response_body="Body",
        )

    valid_summary = "A" * 250
    resp = AgentFinalResponse(
        session_id="session-007",
        intent=IntentEnum.ORDER_STATUS,
        confidence_score=0.9,
        status_resolution=ResolutionStatusEnum.RESOLVED_AUTOMATICALLY,
        internal_technical_summary=valid_summary,
        email_response_subject="Sub",
        email_response_body="Body",
    )
    assert len(resp.internal_technical_summary) == 250


@pytest.mark.parametrize(
    ("prompt_tokens", "completion_tokens", "cost_usd", "duration_sec"),
    [
        (-1, 10, 0.01, 1.0),
        (10, -1, 0.01, 1.0),
        (10, 10, -0.01, 1.0),
        (10, 10, 0.01, -0.5),
    ],
)
def test_agent_final_response_finops_negative_constraints(
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
    duration_sec: float,
) -> None:
    """Validate FinOps tokens, cost, and duration cannot be negative."""
    with pytest.raises(ValidationError):
        AgentFinalResponse(
            session_id="session-008",
            intent=IntentEnum.ORDER_STATUS,
            confidence_score=0.9,
            status_resolution=ResolutionStatusEnum.RESOLVED_AUTOMATICALLY,
            internal_technical_summary="FinOps bounds check.",
            email_response_subject="Sub",
            email_response_body="Body",
            tokens_prompt=prompt_tokens,
            tokens_completion=completion_tokens,
            cost_estimation_usd=cost_usd,
            execution_time_seconds=duration_sec,
        )


def test_agent_final_response_immutability_and_extra_forbid() -> None:
    """Validate immutability and attribute injection rejection."""
    resp = AgentFinalResponse(
        session_id="session-009",
        intent=IntentEnum.ORDER_STATUS,
        confidence_score=0.9,
        status_resolution=ResolutionStatusEnum.RESOLVED_AUTOMATICALLY,
        internal_technical_summary="Frozen check.",
        email_response_subject="Sub",
        email_response_body="Body",
    )
    with pytest.raises(ValidationError):
        resp.confidence_score = 0.5

    with pytest.raises(ValidationError):
        AgentFinalResponse(
            session_id="session-010",
            intent=IntentEnum.ORDER_STATUS,
            confidence_score=0.9,
            status_resolution=ResolutionStatusEnum.RESOLVED_AUTOMATICALLY,
            internal_technical_summary="Extra check.",
            email_response_subject="Sub",
            email_response_body="Body",
            injected_field="attack",  # type: ignore[call-arg]
        )
