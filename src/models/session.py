"""Domain models and DTOs for agent session snapshots and state transitions."""

from datetime import datetime, timezone

from pydantic import ConfigDict, Field

from models.base import BaseDTO
from models.email import InboundEmailMessage
from models.enums import AgentLifecycleState
from models.extraction import ExtractedDemand
from models.tools import ToolCallTrace

__all__ = [
    "AgentSessionSnapshot",
    "StateTransition",
]


class StateTransition(BaseDTO):
    """Immutable record of an agent state machine transition."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    from_state: AgentLifecycleState
    to_state: AgentLifecycleState
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reason: str | None = None


class AgentSessionSnapshot(BaseDTO):
    """Immutable serializable snapshot of an active agent session."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str
    inbound_message: InboundEmailMessage
    current_state: AgentLifecycleState
    extracted_demand: ExtractedDemand | None = None
    tool_traces: tuple[ToolCallTrace, ...] = Field(default_factory=tuple)
    state_history: tuple[StateTransition, ...] = Field(default_factory=tuple)
    iteration_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    escalation_reason: str | None = None
    tenant_id: str = "default_tenant"
