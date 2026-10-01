"""Session state management for ReAct autonomous agent."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import ConfigDict, Field

from models.base import BaseDTO
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


class StateTransition(BaseDTO):
    """Immutable record of an agent state machine transition."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    from_state: AgentLifecycleState
    to_state: AgentLifecycleState
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reason: str | None = None


@dataclass
class AgentSessionState:
    """Mutable container tracking lifecycle state, traces, and intermediate context."""

    session_id: str
    inbound_message: InboundEmailMessage
    current_state: AgentLifecycleState = AgentLifecycleState.RECEIVED
    extracted_demand: ExtractedDemand | None = None
    tool_traces: list[ToolCallTrace] = field(default_factory=list)
    state_history: list[StateTransition] = field(default_factory=list)
    iteration_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    escalation_reason: str | None = None

    @property
    def is_terminal(self) -> bool:
        """Check whether the current lifecycle state is terminal."""
        return self.current_state in {
            AgentLifecycleState.COMPLETED,
            AgentLifecycleState.REQUIRES_HUMAN,
            AgentLifecycleState.FAILED,
        }

    def record_trace(self, trace: ToolCallTrace) -> None:
        """Record a completed tool call trace."""
        self.tool_traces.append(trace)

    def record_transition(self, transition: StateTransition) -> None:
        """Record a verified state transition in audit history."""
        self.state_history.append(transition)


def create_session(
    session_id: str,
    inbound_message: InboundEmailMessage,
) -> AgentSessionState:
    """Instantiate a new agent session state initialized to RECEIVED."""
    return AgentSessionState(
        session_id=session_id,
        inbound_message=inbound_message,
        current_state=AgentLifecycleState.RECEIVED,
    )
