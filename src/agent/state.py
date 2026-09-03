"""Session state management for ReAct autonomous agent."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum

from models.email import InboundEmailMessage
from models.extraction import ExtractedDemand
from models.tools import ToolCallTrace


class AgentLifecycleState(StrEnum):
    """Finite State Machine states of an active agent support session."""

    RECEIVED = "RECEIVED"
    ANALYZING = "ANALYZING"
    EXECUTING_TOOL = "EXECUTING_TOOL"
    OBSERVING = "OBSERVING"
    GENERATING_RESPONSE = "GENERATING_RESPONSE"
    COMPLETED = "COMPLETED"
    REQUIRES_HUMAN = "REQUIRES_HUMAN"
    FAILED = "FAILED"


@dataclass
class AgentSessionState:
    """Mutable container tracking lifecycle state, traces, and intermediate context."""

    session_id: str
    inbound_message: InboundEmailMessage
    current_state: AgentLifecycleState = AgentLifecycleState.RECEIVED
    extracted_demand: ExtractedDemand | None = None
    tool_traces: list[ToolCallTrace] = field(default_factory=list)
    iteration_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    escalation_reason: str | None = None
