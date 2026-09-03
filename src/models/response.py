"""Certified final agent response and audit payload schemas."""

from pydantic import Field

from models.base import BaseDTO
from models.enums import IntentEnum, ResolutionStatusEnum


class AgentFinalResponse(BaseDTO):
    """Certified final response payload emitted by support agent."""

    session_id: str
    intent: IntentEnum
    confidence_score: float = Field(ge=0.0, le=1.0)
    order_id: str | None = None
    actions_taken: tuple[str, ...] = Field(default_factory=tuple)
    status_resolution: ResolutionStatusEnum
    human_escalation_reason: str | None = None
    internal_technical_summary: str = Field(max_length=250)
    email_response_subject: str
    email_response_body: str
    tokens_prompt: int = Field(default=0, ge=0)
    tokens_completion: int = Field(default=0, ge=0)
    cost_estimation_usd: float = Field(default=0.0, ge=0.0)
    execution_time_seconds: float = Field(default=0.0, ge=0.0)
