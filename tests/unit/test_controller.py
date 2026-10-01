"""Unit tests verifying Step 6.1 FSM State Machine Controller and state transitions."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from agent.controller import TERMINAL_STATES, VALID_TRANSITIONS, AgentFSMController
from agent.state import AgentLifecycleState, StateTransition, create_session
from core.exceptions import AppBaseError, FSMStateError
from models.email import InboundEmailMessage
from models.tools import ToolCallTrace, ToolExecutionResult

S = AgentLifecycleState


def test_terminal_states_and_graph_completeness() -> None:
    """Validate terminal states definition and absence of outgoing transitions."""
    assert {S.COMPLETED, S.REQUIRES_HUMAN, S.FAILED} == TERMINAL_STATES
    for terminal_state in TERMINAL_STATES:
        assert len(VALID_TRANSITIONS[terminal_state]) == 0
        assert AgentFSMController.is_terminal(terminal_state)


def test_nominal_lifecycle_path(sample_inbound_email: InboundEmailMessage) -> None:
    """Validate full nominal lifecycle path from RECEIVED to COMPLETED."""
    session = create_session("SESS-NOMINAL-01", sample_inbound_email)
    assert session.current_state == S.RECEIVED and not session.is_terminal

    nominal_steps = (
        (S.ANALYZING, "Sanitized and entity extracted"),
        (S.EXECUTING_TOOL, "Dispatching order status tool"),
        (S.OBSERVING, "Observing tool response"),
        (S.GENERATING_RESPONSE, "Context sufficient for response"),
        (S.COMPLETED, "Final response verified and delivered"),
    )
    for target_state, reason in nominal_steps:
        assert AgentFSMController.can_transition(session, target_state)
        AgentFSMController.transition(session, target_state, reason=reason)
        assert session.current_state == target_state

    assert session.is_terminal and len(session.state_history) == 5
    assert session.state_history[-1].to_state == S.COMPLETED


def test_multi_turn_react_loop(sample_inbound_email: InboundEmailMessage) -> None:
    """Validate multi-turn ReAct loop cycle between OBSERVING and EXECUTING_TOOL."""
    session = create_session("SESS-REACT-01", sample_inbound_email)
    for state in (S.ANALYZING, S.EXECUTING_TOOL, S.OBSERVING):
        AgentFSMController.transition(session, state)

    assert AgentFSMController.can_transition(session, S.EXECUTING_TOOL)
    AgentFSMController.transition(
        session, S.EXECUTING_TOOL, reason="Second tool needed"
    )
    assert session.current_state == S.EXECUTING_TOOL
    AgentFSMController.transition(session, S.OBSERVING)

    AgentFSMController.transition(session, S.GENERATING_RESPONSE)
    AgentFSMController.transition(session, S.COMPLETED)
    assert session.is_terminal


@pytest.mark.parametrize(
    ("origin_state", "escalation_reason"),
    [
        (S.ANALYZING, "PROMPT_INJECTION_DETECTED"),
        (S.EXECUTING_TOOL, "PII_UNAUTHORIZED_ACCESS"),
        (S.OBSERVING, "LOOP_LIMIT_EXCEEDED"),
        (S.GENERATING_RESPONSE, "RESPONSE_VALIDATION_FAILED"),
    ],
)
def test_escalation_to_human_from_states(
    sample_inbound_email: InboundEmailMessage,
    origin_state: AgentLifecycleState,
    escalation_reason: str,
) -> None:
    """Validate escalation to REQUIRES_HUMAN from any active processing state."""
    session = create_session(f"SESS-ESC-{origin_state.value}", sample_inbound_email)
    session.current_state = origin_state

    assert AgentFSMController.can_transition(session, S.REQUIRES_HUMAN)
    AgentFSMController.transition_to_human(session, reason=escalation_reason)
    assert session.current_state == S.REQUIRES_HUMAN
    assert session.escalation_reason == escalation_reason and session.is_terminal


@pytest.mark.parametrize(
    "active_state",
    [S.RECEIVED, S.ANALYZING, S.EXECUTING_TOOL, S.OBSERVING, S.GENERATING_RESPONSE],
)
def test_failure_from_active_states(
    sample_inbound_email: InboundEmailMessage,
    active_state: AgentLifecycleState,
) -> None:
    """Validate transitioning to FAILED from any active state."""
    session = create_session(f"SESS-FAIL-{active_state.value}", sample_inbound_email)
    session.current_state = active_state

    assert AgentFSMController.can_transition(session, S.FAILED)
    AgentFSMController.transition_to_failed(session, reason="Fatal unhandled fault")
    assert session.current_state == S.FAILED and session.is_terminal
    assert (
        len(session.state_history) == 1
        and session.state_history[0].to_state == S.FAILED
    )


@pytest.mark.parametrize(
    ("from_state", "invalid_target"),
    [
        (S.RECEIVED, S.COMPLETED),
        (S.RECEIVED, S.EXECUTING_TOOL),
        (S.ANALYZING, S.COMPLETED),
        (S.EXECUTING_TOOL, S.GENERATING_RESPONSE),
        (S.OBSERVING, S.RECEIVED),
        (S.ANALYZING, S.ANALYZING),
    ],
)
def test_forbidden_transitions_raise_fsm_state_error(
    sample_inbound_email: InboundEmailMessage,
    from_state: AgentLifecycleState,
    invalid_target: AgentLifecycleState,
) -> None:
    """Validate that invalid transitions raise FSMStateError and preserve state."""
    session = create_session("SESS-FORBIDDEN", sample_inbound_email)
    session.current_state = from_state

    assert not AgentFSMController.can_transition(session, invalid_target)
    with pytest.raises(FSMStateError) as exc_info:
        AgentFSMController.transition(session, invalid_target)

    assert issubclass(FSMStateError, AppBaseError)
    assert exc_info.value.error_code == "FSM_STATE_INVALID"
    assert session.current_state == from_state


@pytest.mark.parametrize("terminal_state", [S.COMPLETED, S.REQUIRES_HUMAN, S.FAILED])
def test_transitions_from_terminal_states_rejected(
    sample_inbound_email: InboundEmailMessage,
    terminal_state: AgentLifecycleState,
) -> None:
    """Validate that terminal states reject any further transitions."""
    session = create_session("SESS-TERMINAL", sample_inbound_email)
    session.current_state = terminal_state
    assert session.is_terminal

    for target in AgentLifecycleState:
        assert not AgentFSMController.can_transition(session, target)
        with pytest.raises(FSMStateError):
            AgentFSMController.transition(session, target)


def test_inspection_helpers_and_allowed_transitions(
    sample_inbound_email: InboundEmailMessage,
) -> None:
    """Validate can_transition, is_terminal, and get_allowed_transitions."""
    session = create_session("SESS-HELP", sample_inbound_email)
    assert AgentFSMController.can_transition(S.RECEIVED, S.ANALYZING)
    assert AgentFSMController.can_transition(session, S.ANALYZING)
    assert not AgentFSMController.can_transition(S.RECEIVED, S.COMPLETED)
    assert not AgentFSMController.can_transition(session, S.COMPLETED)

    allowed = AgentFSMController.get_allowed_transitions(S.RECEIVED)
    assert allowed == frozenset({S.ANALYZING, S.FAILED})
    assert AgentFSMController.get_allowed_transitions(session) == allowed
    assert AgentFSMController.is_terminal(S.COMPLETED)
    assert not AgentFSMController.is_terminal(session)


def test_state_transition_immutability_and_extra_forbid() -> None:
    """Validate StateTransition model immutability and rejection of extra fields."""
    record = StateTransition(
        from_state=S.RECEIVED, to_state=S.ANALYZING, reason="Initial parse"
    )
    assert record.from_state == S.RECEIVED and record.to_state == S.ANALYZING
    assert isinstance(record.timestamp, datetime)

    with pytest.raises(ValidationError):
        record.reason = "Mutated"

    with pytest.raises(ValidationError):
        StateTransition(
            from_state=S.RECEIVED, to_state=S.ANALYZING, extra_field="disallowed"
        )  # type: ignore[call-arg]


def test_session_state_trace_recording(
    sample_inbound_email: InboundEmailMessage,
) -> None:
    """Validate session recording of tool traces and initialization defaults."""
    session = create_session("SESS-TRACE-01", sample_inbound_email)
    assert len(session.tool_traces) == 0

    trace = ToolCallTrace(
        tool_call_id="call-01",
        tool_name="get_order_details",
        arguments={"order_id": "CMD-10001"},
        result=ToolExecutionResult(
            success=True, tool_name="get_order_details", data={"status": "DELIVERED"}
        ),
        timestamp=datetime.now(timezone.utc),
        duration_ms=42.5,
    )
    session.record_trace(trace)
    assert len(session.tool_traces) == 1
    assert session.tool_traces[0].tool_name == "get_order_details"
