"""Finite State Machine (FSM) controller managing agent lifecycle transitions."""

from agent.state import AgentLifecycleState, AgentSessionState
from core.exceptions import FSMStateError
from observability.logger import get_logger

logger = get_logger(__name__)

VALID_TRANSITIONS: dict[AgentLifecycleState, set[AgentLifecycleState]] = {
    AgentLifecycleState.RECEIVED: {
        AgentLifecycleState.ANALYZING,
        AgentLifecycleState.FAILED,
    },
    AgentLifecycleState.ANALYZING: {
        AgentLifecycleState.EXECUTING_TOOL,
        AgentLifecycleState.REQUIRES_HUMAN,
        AgentLifecycleState.FAILED,
    },
    AgentLifecycleState.EXECUTING_TOOL: {
        AgentLifecycleState.OBSERVING,
        AgentLifecycleState.REQUIRES_HUMAN,
        AgentLifecycleState.FAILED,
    },
    AgentLifecycleState.OBSERVING: {
        AgentLifecycleState.EXECUTING_TOOL,
        AgentLifecycleState.GENERATING_RESPONSE,
        AgentLifecycleState.REQUIRES_HUMAN,
        AgentLifecycleState.FAILED,
    },
    AgentLifecycleState.GENERATING_RESPONSE: {
        AgentLifecycleState.COMPLETED,
        AgentLifecycleState.REQUIRES_HUMAN,
        AgentLifecycleState.FAILED,
    },
    AgentLifecycleState.COMPLETED: set(),
    AgentLifecycleState.REQUIRES_HUMAN: set(),
    AgentLifecycleState.FAILED: set(),
}


class AgentFSMController:
    """Manages verified state transitions within the agent session lifecycle."""

    @staticmethod
    def transition(session: AgentSessionState, new_state: AgentLifecycleState) -> None:
        """Advance session state verifying transition validity.

        Raises:
            FSMStateError: If transition is forbidden.
        """
        current = session.current_state
        allowed = VALID_TRANSITIONS.get(current, set())

        if new_state not in allowed:
            logger.error(
                "fsm_invalid_transition",
                session_id=session.session_id,
                current_state=current.value,
                requested_state=new_state.value,
            )
            raise FSMStateError(
                f"Forbidden state transition from {current.value} to {new_state.value}"
            )

        logger.info(
            "fsm_transition",
            session_id=session.session_id,
            previous_state=current.value,
            new_state=new_state.value,
        )
        session.current_state = new_state
