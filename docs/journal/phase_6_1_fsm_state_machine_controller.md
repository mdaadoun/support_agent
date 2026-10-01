# Session 6.1: Finite State Machine (FSM) Lifecycle Controller
**Date:** 2026-09-29

*Implemented the Finite State Machine (FSM) controller (`AgentFSMController`) and session audit data contracts (`StateTransition`, `AgentSessionState`) in `src/agent/controller.py` and `src/agent/state.py`. The controller enforces deterministic transitions across the full agent lifecycle: `RECEIVED` ──► `ANALYZING` ──► `EXECUTING_TOOL` ──► `OBSERVING` ──► `GENERATING_RESPONSE` ──► `COMPLETED` / `REQUIRES_HUMAN` / `FAILED`, guaranteeing fail-closed boundary security, terminal state immutability, and full transition auditing.*

---

### 1. 🎓 Concepts Introduced
- **Deterministic Finite State Machine (FSM):** A formal mathematical model enforcing valid lifecycle transitions, disallowing out-of-order execution, and guaranteeing that the ReAct agent respects strict operational stages.
- **`AgentLifecycleState` Enumeration:** Strongly typed string enum (`RECEIVED`, `ANALYZING`, `EXECUTING_TOOL`, `OBSERVING`, `GENERATING_RESPONSE`, `COMPLETED`, `REQUIRES_HUMAN`, `FAILED`) declaring all valid session stages.
- **Immutable State Transition Audit Records (`StateTransition`):** A frozen Pydantic V2 DTO (`BaseDTO` derivative) capturing source state, target state, UTC timestamp, and diagnostic reason for every lifecycle change.
- **Absorbing Terminal States (`TERMINAL_STATES`):** Isolated final states (`COMPLETED`, `REQUIRES_HUMAN`, `FAILED`) with an empty outgoing transition set, preventing "zombie sessions" from continuing background execution.
- **Multi-Turn Loop Re-Entrance:** Permitting controlled cycles between `OBSERVING` and `EXECUTING_TOOL` while bounding execution via external iteration counters.
- **Fail-Closed Escalation & Failure Shortcuts:** Dedicated convenience methods (`transition_to_human`, `transition_to_failed`) that record structured escalation reasons and enforce immediate containment.

---

### 2. 🧠 Architecture Decisions (ADR)

#### Decision: Declarative Transition Table vs. Full Gang-of-Four Polymorphic State Pattern
- **Option 1:** Implement the GoF State Pattern with individual concrete classes for each lifecycle state (e.g. `ReceivedState`, `AnalyzingState`) implementing a common interface.
- **Option 2 (Selected):** Use a centralized declarative transition map (`dict[AgentLifecycleState, frozenset[AgentLifecycleState]]`) enforced by `AgentFSMController`.
- **Rationale:** The GoF State pattern distributes transition rules across dozens of disparate classes, creating cognitive overhead and making the global transition graph difficult to inspect or serialize. A centralized declarative transition table provides a single source of truth, allows $O(1)$ membership checks, supports compile-time and runtime type safety via `StrEnum` and `frozenset`, and seamlessly interfaces with external persistence and visualization without object instantiation overhead.

#### Decision: Immutable State Transition Audit Records (StateTransition DTO)
- **Option 1:** Mutate `session.current_state` in-place without preserving transition history.
- **Option 2 (Selected):** Record immutable `StateTransition` DTOs (inheriting from `BaseDTO`) with timestamps and transition reasons into `session.state_history`.
- **Rationale:** Customer support automation in regulated e-commerce environments requires strict auditability. Capturing each transition as an immutable DTO with UTC timestamp and diagnostic reason provides complete forensic visibility into agent trajectories, enables FinOps latency attribution across individual lifecycle phases, and prevents silent state mutations across async boundaries.

#### Decision: Terminal Absorbing States with Zero Outgoing Transitions
- **Option 1:** Allow sessions in terminal states (`COMPLETED`, `REQUIRES_HUMAN`, `FAILED`) to transition back to active states upon retries or re-evaluations.
- **Option 2 (Selected):** Enforce strict absorbing terminal states where any subsequent transition raises `FSMStateError`.
- **Rationale:** Allowing transitions out of terminal states leads to "zombie sessions", where completed tickets or tickets escalated to human queues continue executing background tool calls. Raising `FSMStateError` ensures that terminal states are final and tamper-proof.

---

### 3. 🛠️ Implementation & Code
*Implementation details and validation commands.*

```python
# src/agent/controller.py
class AgentFSMController:
    """Manages verified state transitions within the agent session lifecycle."""

    @classmethod
    def transition(
        cls,
        session: AgentSessionState,
        new_state: AgentLifecycleState,
        reason: str | None = None,
    ) -> None:
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
```

```bash
# Verification commands
make lint
make typecheck
make test
```

---

### 4. 📌 Session Checklist & Deliverables
1. [x] **FSM Controller (`src/agent/controller.py`)**: Implemented `AgentFSMController` enforcing `VALID_TRANSITIONS`, `TERMINAL_STATES`, inspection helpers (`can_transition`, `is_terminal`, `get_allowed_transitions`), and escalation shortcuts (`transition_to_human`, `transition_to_failed`).
2. [x] **Session State & Audit Contracts (`src/agent/state.py`)**: Created immutable `StateTransition` model (`frozen=True, extra="forbid"`), session transition history, terminal state property, and `create_session` factory.
3. [x] **Package Exports (`src/agent/__init__.py`)**: Exported `AgentFSMController`, `AgentLifecycleState`, `AgentSessionState`, `StateTransition`, `TERMINAL_STATES`, `VALID_TRANSITIONS`, and `create_session`.
4. [x] **Comprehensive Test Suite (`tests/unit/test_controller.py`)**: Implemented 24 unit tests covering nominal lifecycle, ReAct multi-turn loop re-entrance, human escalation paths, failure states, forbidden transitions, terminal immutability, and DTO validation.
5. [x] **Quality Gates Verified**: `make lint` passed, `make typecheck` passed (strict across 69 files), `make test` passed (242 tests passing 100%).
