# Session 2.5: Standardized Exception Shielding Hierarchy
**Date:** 2026-09-10

*Established the standardized domain exception shielding hierarchy in `src/core/exceptions.py`, providing a unified error taxonomy rooted in `SupportAgentBaseError` (aliased as `AppBaseError`), normalized machine-readable `error_code` identifiers, contextual attributes, and strict exception shielding to guarantee the "Zero Naked Crash" policy.*

---

### 1. 🎓 Concepts Introduced
- **Standardized Error Taxonomy:** Exception hierarchy rooted in `SupportAgentBaseError` establishing normalized, machine-readable `error_code` attributes across all domain sub-exceptions.
- **Zero Naked Crash Policy:** Architectural mandate ensuring raw third-party infrastructure exceptions (`httpx`, `redis`, `psycopg2`) never escape layer boundaries unwrapped.
- **Universal Architecture Alias (`AppBaseError`):** Cross-workspace standard alias pointing directly to `SupportAgentBaseError` for uniform error catching across system modules.
- **Contextual Exception Metadata:** Equipping domain exceptions with typed attributes (`tool_name` on `ToolExecutionError`, `order_id` on `OrderNotFoundError`) for structured observability without regex message parsing.

---

### 2. 🧠 Architecture Decisions (ADR)

#### Decision: Root Domain Exception with Normalized Machine-Readable `error_code`
- **Option 1:** Standard Python string-based exceptions without error codes.
- **Option 2 (Selected):** `SupportAgentBaseError(message: str, error_code: str)`.
- **Rationale:** Normalizes error categories for structured JSON logging, FinOps telemetry, and automated FSM recovery transitions without relying on string message parsing.

#### Decision: Universal Architecture Alias (`AppBaseError = SupportAgentBaseError`)
- **Option 1:** Enforce only `SupportAgentBaseError`.
- **Option 2 (Selected):** Expose `AppBaseError` as an alias for `SupportAgentBaseError`.
- **Rationale:** Satisfies universal Pax engineering guardrails across multi-project repositories while preserving domain-specific naming in local modules.

#### Decision: Contextual Attributes on Sub-Exceptions
- **Option 1:** Embed parameters only in string messages.
- **Option 2 (Selected):** Typed attributes (`tool_name`, `order_id`).
- **Rationale:** Downstream error middleware, audit log repositories, and FSM transition managers can programmatically inspect key entities without brittle string parsing.

---

### 3. 🛠️ Implementation & Code
*Implementation details and validation commands.*

```python
# src/core/exceptions.py
__all__ = [
    "AppBaseError",
    "CircuitBreakerError",
    "ConfigurationError",
    "FSMStateError",
    "OrderNotFoundError",
    "SecurityAccessError",
    "SupportAgentBaseError",
    "ToolExecutionError",
]

class SupportAgentBaseError(Exception):
    def __init__(self, message: str, error_code: str = "INTERNAL_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code

AppBaseError = SupportAgentBaseError

class ConfigurationError(SupportAgentBaseError):
    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="CONFIGURATION_ERROR")

class SecurityAccessError(SupportAgentBaseError):
    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="SECURITY_UNAUTHORIZED_ACCESS")

class ToolExecutionError(SupportAgentBaseError):
    def __init__(self, message: str, tool_name: str = "unknown") -> None:
        super().__init__(message, error_code="TOOL_EXECUTION_ERROR")
        self.tool_name = tool_name

class FSMStateError(SupportAgentBaseError):
    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="FSM_STATE_INVALID")

class CircuitBreakerError(SupportAgentBaseError):
    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="CIRCUIT_BREAKER_TRIPPED")

class OrderNotFoundError(SupportAgentBaseError):
    def __init__(self, order_id: str) -> None:
        super().__init__(f"Order '{order_id}' not found.", error_code="ORDER_NOT_FOUND")
        self.order_id = order_id
```

```bash
# Validation commands
make lint
make typecheck
make test
```

---

### 4. 📌 Session Checklist & Deliverables
1. [x] **SupportAgentBaseError & AppBaseError Defined (`src/core/exceptions.py`)** with `error_code` and explicit `__all__` export.
2. [x] **Domain Sub-Exceptions Implemented**: `SecurityAccessError`, `ToolExecutionError`, `FSMStateError`, `CircuitBreakerError`, `ConfigurationError`, `OrderNotFoundError`.
3. [x] **Dedicated Unit Test Suite (`tests/unit/test_exceptions.py`)** verifying taxonomy, inheritance, attribute bindings, and exception shielding patterns.
4. [x] **Static Verification**: `make lint`, `make typecheck` (Mypy strict), and `make test` passing 100%.
