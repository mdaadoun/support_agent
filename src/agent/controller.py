"""Finite State Machine (FSM) controller managing agent lifecycle transitions."""

from datetime import datetime, timezone

from agent.state import AgentLifecycleState, AgentSessionState, StateTransition
from core.exceptions import FSMStateError
from observability.logger import get_logger

logger = get_logger(__name__)

TERMINAL_STATES: frozenset[AgentLifecycleState] = frozenset(
    {
        AgentLifecycleState.COMPLETED,
        AgentLifecycleState.REQUIRES_HUMAN,
        AgentLifecycleState.FAILED,
    }
)

VALID_TRANSITIONS: dict[AgentLifecycleState, frozenset[AgentLifecycleState]] = {
    AgentLifecycleState.RECEIVED: frozenset(
        {
            AgentLifecycleState.ANALYZING,
            AgentLifecycleState.FAILED,
        }
    ),
    AgentLifecycleState.ANALYZING: frozenset(
        {
            AgentLifecycleState.EXECUTING_TOOL,
            AgentLifecycleState.GENERATING_RESPONSE,
            AgentLifecycleState.REQUIRES_HUMAN,
            AgentLifecycleState.FAILED,
        }
    ),
    AgentLifecycleState.EXECUTING_TOOL: frozenset(
        {
            AgentLifecycleState.OBSERVING,
            AgentLifecycleState.REQUIRES_HUMAN,
            AgentLifecycleState.FAILED,
        }
    ),
    AgentLifecycleState.OBSERVING: frozenset(
        {
            AgentLifecycleState.EXECUTING_TOOL,
            AgentLifecycleState.GENERATING_RESPONSE,
            AgentLifecycleState.REQUIRES_HUMAN,
            AgentLifecycleState.FAILED,
        }
    ),
    AgentLifecycleState.GENERATING_RESPONSE: frozenset(
        {
            AgentLifecycleState.COMPLETED,
            AgentLifecycleState.REQUIRES_HUMAN,
            AgentLifecycleState.FAILED,
        }
    ),
    AgentLifecycleState.COMPLETED: frozenset(),
    AgentLifecycleState.REQUIRES_HUMAN: frozenset(),
    AgentLifecycleState.FAILED: frozenset(),
}


class AgentFSMController:
    """Manages verified state transitions within the agent session lifecycle."""

    @classmethod
    def can_transition(
        cls,
        current: AgentLifecycleState | AgentSessionState,
        target: AgentLifecycleState,
    ) -> bool:
        """Evaluate if transition from current state to target state is permissible."""
        state = (
            current.current_state if isinstance(current, AgentSessionState) else current
        )
        allowed = VALID_TRANSITIONS.get(state, frozenset())
        return target in allowed

    @classmethod
    def is_terminal(cls, state: AgentLifecycleState | AgentSessionState) -> bool:
        """Check whether given lifecycle state or session is in a terminal state."""
        current = state.current_state if isinstance(state, AgentSessionState) else state
        return current in TERMINAL_STATES

    @classmethod
    def get_allowed_transitions(
        cls, state: AgentLifecycleState | AgentSessionState
    ) -> frozenset[AgentLifecycleState]:
        """Return the immutable set of allowed target states from current state."""
        current = state.current_state if isinstance(state, AgentSessionState) else state
        return VALID_TRANSITIONS.get(current, frozenset())

    @classmethod
    def transition(
        cls,
        session: AgentSessionState,
        new_state: AgentLifecycleState,
        reason: str | None = None,
    ) -> None:
        """Advance session state verifying transition validity and updating audit history.

        Args:
            session: Active agent session state container.
            new_state: Target lifecycle state to transition into.
            reason: Optional explanation or diagnostic rationale for transition.

        Raises:
            FSMStateError: If the requested transition is forbidden by state machine rules.
        """
        current = session.current_state
        allowed = VALID_TRANSITIONS.get(current, frozenset())

        if new_state not in allowed:
            logger.error(
                "fsm_invalid_transition",
                session_id=session.session_id,
                current_state=current.value,
                requested_state=new_state.value,
                reason=reason,
            )
            raise FSMStateError(
                f"Forbidden state transition from {current.value} to {new_state.value}"
            )

        logger.info(
            "fsm_transition",
            session_id=session.session_id,
            previous_state=current.value,
            new_state=new_state.value,
            reason=reason,
        )

        transition_record = StateTransition(
            from_state=current,
            to_state=new_state,
            timestamp=datetime.now(timezone.utc),
            reason=reason,
        )
        session.record_transition(transition_record)

        if (
            reason is not None
            and new_state == AgentLifecycleState.REQUIRES_HUMAN
            and session.escalation_reason is None
        ):
            session.escalation_reason = reason

        session.current_state = new_state

    @classmethod
    def transition_to_human(cls, session: AgentSessionState, reason: str) -> None:
        """Transition session to REQUIRES_HUMAN with escalation reason."""
        cls.transition(session, AgentLifecycleState.REQUIRES_HUMAN, reason=reason)

    @classmethod
    def transition_to_failed(cls, session: AgentSessionState, reason: str) -> None:
        """Transition session to FAILED with failure reason."""
        cls.transition(session, AgentLifecycleState.FAILED, reason=reason)
