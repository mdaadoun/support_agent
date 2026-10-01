"""Zero LLM Authority validation guard enforcing deterministic business rules."""

from collections.abc import Sequence

from agent.validator_rules import (
    MUTATION_RE,
    check_refund_tool_authorization,
    check_voucher_tool_authorization,
    detect_approval_claims,
    extract_certified_amounts,
    extract_monetary_amounts,
)
from core.exceptions import LLMAuthorityViolationError
from models.enums import ResolutionStatusEnum
from models.response import (
    AgentFinalResponse,
    AuthorityValidationResult,
    ResponseSynthesisOutput,
)
from models.tools import ToolCallTrace

__all__ = ["ZeroLLMAuthorityGuard"]


class ZeroLLMAuthorityGuard:
    """Validation guard enforcing Zero LLM Authority on synthesized customer communications."""

    def validate(
        self,
        response: AgentFinalResponse | ResponseSynthesisOutput,
        traces: Sequence[ToolCallTrace],
    ) -> AuthorityValidationResult:
        """Validate response against certified tool traces and business authority constraints."""
        violations: list[str] = []
        combined_text = (
            f"{response.email_response_subject} {response.email_response_body}"
        )

        # 1. Monetary Figures Validation
        detected_amounts = extract_monetary_amounts(combined_text)
        detected_cents = tuple(c for _, c in detected_amounts)
        certified_cents = extract_certified_amounts(traces)

        for raw_str, cents in detected_amounts:
            if cents not in certified_cents:
                violations.append(
                    f"Uncertified monetary figure: '{raw_str}' ({cents} cents) "
                    "not found in certified tool results."
                )

        # 2. Approval Claims Validation
        claims = detect_approval_claims(combined_text)
        if "refund_approval" in claims and not check_refund_tool_authorization(traces):
            violations.append(
                "Unauthorized refund approval: Model claimed refund approval without "
                "certified tool authorization."
            )

        if "voucher_approval" in claims and not check_voucher_tool_authorization(
            traces
        ):
            violations.append(
                "Unauthorized voucher approval: Model claimed compensation voucher without "
                "certified tool authorization."
            )

        # 3. Operational Mutation Claims
        if MUTATION_RE.search(combined_text):
            violations.append(
                "Unauthorized operational mutation: Model claimed database/order modifications."
            )

        # 4. Security Access Failure Guard
        has_security_breach = any(
            t.result.error_code == "SECURITY_UNAUTHORIZED_ACCESS" for t in traces
        )
        if (
            has_security_breach
            and response.status_resolution
            == ResolutionStatusEnum.RESOLVED_AUTOMATICALLY
        ):
            violations.append(
                "Security violation: Session encountered SECURITY_UNAUTHORIZED_ACCESS "
                "but attempted automatic resolution."
            )

        return AuthorityValidationResult(
            is_valid=len(violations) == 0,
            violations=tuple(violations),
            detected_amounts_cents=detected_cents,
            certified_amounts_cents=tuple(sorted(certified_cents)),
            detected_approval_claims=tuple(claims),
        )

    def verify_authority(
        self,
        response: AgentFinalResponse | ResponseSynthesisOutput,
        traces: Sequence[ToolCallTrace],
    ) -> None:
        """Assert zero authority violations, raising LLMAuthorityViolationError on breach."""
        result = self.validate(response=response, traces=traces)
        if not result.is_valid:
            raise LLMAuthorityViolationError(
                message=f"Zero LLM Authority validation failed: {'; '.join(result.violations)}",
                violations=result.violations,
            )

    def guard_response(
        self,
        response: AgentFinalResponse,
        traces: Sequence[ToolCallTrace],
    ) -> tuple[AgentFinalResponse, AuthorityValidationResult]:
        """Validate response and safely downgrade/escalate if violations are detected."""
        result = self.validate(response=response, traces=traces)
        if result.is_valid:
            return response, result

        summary = "; ".join(result.violations)
        reason = f"AUTHORITY_VIOLATION: {summary}"[:250]
        safe_body = (
            "Your inquiry has been forwarded to our customer support team for manual review. "
            "A customer support representative will follow up with you shortly."
        )
        actions = list(response.actions_taken)
        actions.append(f"Blocked uncertified commitment: {result.violations[0]}")

        escalated = AgentFinalResponse(
            session_id=response.session_id,
            intent=response.intent,
            confidence_score=0.0,
            order_id=response.order_id,
            actions_taken=tuple(actions),
            status_resolution=ResolutionStatusEnum.REQUIRES_HUMAN_REVIEW,
            human_escalation_reason=reason,
            internal_technical_summary=f"Authority guard tripped: {summary}"[:250],
            email_response_subject=response.email_response_subject,
            email_response_body=safe_body,
            tokens_prompt=response.tokens_prompt,
            tokens_completion=response.tokens_completion,
            cost_estimation_usd=response.cost_estimation_usd,
            execution_time_seconds=response.execution_time_seconds,
        )
        return escalated, result
