"""Response builder constructing certified AgentFinalResponse payloads."""

import time

from agent.prompts import PromptManager
from agent.protocols import LLMClientProtocol
from agent.state import AgentSessionState
from agent.validator import ZeroLLMAuthorityGuard
from models.enums import IntentEnum, ResolutionStatusEnum
from models.response import AgentFinalResponse, ResponseSynthesisOutput

__all__ = ["build_escalated_response", "synthesize_certified_response"]


def build_escalated_response(
    session: AgentSessionState,
    reason: str,
    intent: IntentEnum,
    start_time: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cost_usd: float = 0.0,
) -> AgentFinalResponse:
    """Construct a standardized human escalation response."""
    actions = [t.tool_name for t in session.tool_traces]
    actions.append(f"Escalated to human review: {reason}")
    order_id = session.extracted_demand.order_id if session.extracted_demand else None

    return AgentFinalResponse(
        session_id=session.session_id,
        intent=intent,
        confidence_score=0.0,
        order_id=order_id,
        actions_taken=tuple(actions),
        status_resolution=ResolutionStatusEnum.REQUIRES_HUMAN_REVIEW,
        human_escalation_reason=reason,
        internal_technical_summary=f"Escalated session {session.session_id}: {reason}"[
            :250
        ],
        email_response_subject=f"Re: {session.inbound_message.subject}",
        email_response_body=(
            "Your request has been forwarded to our human support team for review. "
            "A customer support representative will follow up with you shortly."
        ),
        tokens_prompt=prompt_tokens,
        tokens_completion=completion_tokens,
        cost_estimation_usd=round(cost_usd, 6),
        execution_time_seconds=round(time.perf_counter() - start_time, 4),
    )


async def synthesize_certified_response(
    llm_client: LLMClientProtocol,
    session: AgentSessionState,
    confidence_threshold: float,
    start_time: float,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
    authority_guard: ZeroLLMAuthorityGuard | None = None,
) -> AgentFinalResponse:
    """Synthesize certified final response grounded in tool observations."""
    system_prompt = PromptManager.get_response_system_prompt()
    final_prompt = PromptManager.build_final_response_prompt(session)

    synthesis: ResponseSynthesisOutput = await llm_client.generate_structured(
        system_prompt=system_prompt,
        user_prompt=final_prompt,
        response_schema=ResponseSynthesisOutput,
    )

    is_low_confidence = synthesis.confidence_score < confidence_threshold
    human_escalation_reason: str | None
    email_response_body = synthesis.email_response_body

    # Zero LLM Authority validation check
    guard = authority_guard or ZeroLLMAuthorityGuard()
    auth_result = guard.validate(synthesis, session.tool_traces)

    if not auth_result.is_valid:
        status_resolution = ResolutionStatusEnum.REQUIRES_HUMAN_REVIEW
        human_escalation_reason = (
            f"AUTHORITY_VIOLATION: {'; '.join(auth_result.violations)}"
        )[:250]
        email_response_body = (
            "Your inquiry has been forwarded to our customer support team for manual review. "
            "A customer support representative will follow up with you shortly."
        )
    elif is_low_confidence:
        status_resolution = ResolutionStatusEnum.REQUIRES_HUMAN_REVIEW
        human_escalation_reason = (
            f"Confidence score {synthesis.confidence_score:.2f} below "
            f"threshold {confidence_threshold:.2f}."
        )
    else:
        status_resolution = synthesis.status_resolution
        human_escalation_reason = synthesis.human_escalation_reason

    if (
        status_resolution == ResolutionStatusEnum.REQUIRES_HUMAN_REVIEW
        and not human_escalation_reason
    ):
        human_escalation_reason = "Human review required by synthesis policy."

    actions = list(
        dict.fromkeys(
            [t.tool_name for t in session.tool_traces] + list(synthesis.actions_taken)
        )
    )
    if not actions and session.extracted_demand:
        actions.append(
            f"Analyzed demand for intent: {session.extracted_demand.intent.value}"
        )

    order_id = synthesis.order_id or (
        session.extracted_demand.order_id if session.extracted_demand else None
    )

    return AgentFinalResponse(
        session_id=session.session_id,
        intent=synthesis.intent,
        confidence_score=synthesis.confidence_score,
        order_id=order_id,
        actions_taken=tuple(actions),
        status_resolution=status_resolution,
        human_escalation_reason=human_escalation_reason,
        internal_technical_summary=synthesis.internal_technical_summary[:250],
        email_response_subject=synthesis.email_response_subject,
        email_response_body=email_response_body,
        tokens_prompt=prompt_tokens,
        tokens_completion=completion_tokens,
        cost_estimation_usd=round(cost_usd, 6),
        execution_time_seconds=round(time.perf_counter() - start_time, 4),
    )
