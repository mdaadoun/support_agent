"""Domain models and DTOs for audit logs and execution traces."""

from datetime import datetime, timezone
from typing import Any

from pydantic import ConfigDict, Field

from models.base import BaseDTO
from models.enums import IntentEnum, ResolutionStatusEnum
from models.response import AgentFinalResponse

__all__ = ["AuditLogRecord"]


class AuditLogRecord(BaseDTO):
    """Immutable audit trail record capturing certified agent execution results."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str
    tenant_id: str = "default_tenant"
    intent: IntentEnum
    status_resolution: ResolutionStatusEnum
    confidence_score: float = Field(ge=0.0, le=1.0)
    duration_ms: float = Field(default=0.0, ge=0.0)
    tokens_prompt: int = Field(default=0, ge=0)
    tokens_completion: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    message_id: str | None = None
    customer_email: str | None = None
    order_id: str | None = None
    human_escalation_reason: str | None = None
    internal_technical_summary: str = Field(default="", max_length=250)
    trace_data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def from_response(
        cls,
        response: AgentFinalResponse,
        tenant_id: str = "default_tenant",
        message_id: str | None = None,
        customer_email: str | None = None,
        trace_data: dict[str, Any] | None = None,
    ) -> "AuditLogRecord":
        """Instantiate immutable audit record from certified agent response."""
        return cls(
            session_id=response.session_id,
            tenant_id=tenant_id,
            intent=response.intent,
            status_resolution=response.status_resolution,
            confidence_score=response.confidence_score,
            duration_ms=round(response.execution_time_seconds * 1000.0, 2),
            tokens_prompt=response.tokens_prompt,
            tokens_completion=response.tokens_completion,
            cost_usd=response.cost_estimation_usd,
            message_id=message_id,
            customer_email=customer_email,
            order_id=response.order_id,
            human_escalation_reason=response.human_escalation_reason,
            internal_technical_summary=response.internal_technical_summary,
            trace_data=trace_data or {},
        )
