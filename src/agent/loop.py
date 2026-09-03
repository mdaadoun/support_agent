"""ReAct decision-action-observation execution loop engine for 8_support_agent."""

from agent.controller import AgentFSMController
from agent.state import AgentLifecycleState, AgentSessionState
from core.config import get_settings
from observability.logger import get_logger

logger = get_logger(__name__)


class ReActLoopEngine:
    """Orchestrates multi-turn ReAct cycles with hard recursion limits."""

    def __init__(self, max_iterations: int | None = None) -> None:
        settings = get_settings()
        self.max_iterations = max_iterations or settings.agent_max_iterations

    async def step(self, session: AgentSessionState) -> None:
        """Execute a single ReAct cycle step enforcing iteration ceilings."""
        if session.iteration_count >= self.max_iterations:
            logger.warning(
                "loop_ceiling_reached",
                session_id=session.session_id,
                iterations=session.iteration_count,
                max_iterations=self.max_iterations,
            )
            session.escalation_reason = "LOOP_LIMIT_EXCEEDED"
            AgentFSMController.transition(session, AgentLifecycleState.REQUIRES_HUMAN)
            return

        session.iteration_count += 1
