"""Session state management for ReAct autonomous agent."""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from models.email import InboundEmailMessage
from models.enums import AgentLifecycleState
from models.extraction import ExtractedDemand
from models.session import AgentSessionSnapshot, StateTransition
from models.tools import ToolCallTrace

__all__ = [
    "AgentLifecycleState",
    "AgentSessionSnapshot",
    "AgentSessionState",
    "StateTransition",
    "create_session",
]


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
    tenant_id: str = "default_tenant"

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

    def to_snapshot(self) -> AgentSessionSnapshot:
        """Create an immutable serializable snapshot of current session state."""
        return AgentSessionSnapshot(
            session_id=self.session_id,
            inbound_message=self.inbound_message,
            current_state=self.current_state,
            extracted_demand=self.extracted_demand,
            tool_traces=tuple(self.tool_traces),
            state_history=tuple(self.state_history),
            iteration_count=self.iteration_count,
            created_at=self.created_at,
            escalation_reason=self.escalation_reason,
            tenant_id=self.tenant_id,
        )

    @classmethod
    def from_snapshot(cls, snapshot: AgentSessionSnapshot) -> "AgentSessionState":
        """Instantiate mutable session state from an immutable snapshot."""
        return cls(
            session_id=snapshot.session_id,
            inbound_message=snapshot.inbound_message,
            current_state=snapshot.current_state,
            extracted_demand=snapshot.extracted_demand,
            tool_traces=list(snapshot.tool_traces),
            state_history=list(snapshot.state_history),
            iteration_count=snapshot.iteration_count,
            created_at=snapshot.created_at,
            escalation_reason=snapshot.escalation_reason,
            tenant_id=snapshot.tenant_id,
        )


def create_session(
    session_id: str,
    inbound_message: InboundEmailMessage,
    tenant_id: str = "default_tenant",
) -> AgentSessionState:
    """Instantiate a new agent session state initialized to RECEIVED."""
    return AgentSessionState(
        session_id=session_id,
        inbound_message=inbound_message,
        current_state=AgentLifecycleState.RECEIVED,
        tenant_id=tenant_id,
    )
