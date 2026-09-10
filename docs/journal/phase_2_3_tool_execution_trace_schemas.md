# Session 2.3: Tool Execution & Trace Schemas
**Date:** 2026-09-10

*Implemented standardized tool execution and audit trace DTO contracts (`OrderDetailsResult`, `RefundEligibilityResult`, `DeliveryDelayResult`, `ToolExecutionResult`, `ToolCallTrace`) enforcing boundary exception shielding, integer cent monetary representation with non-negative constraints, and comprehensive invocation telemetry.*

---

### 1. 🎓 Concepts Introduced
- **Shielded Tool Execution Container (`ToolExecutionResult`):** Standardized envelope returning execution status, payload data, and machine-readable error codes rather than raising uncaught exceptions, enabling graceful ReAct observation feedback.
- **Audit Invocation Trace (`ToolCallTrace`):** Structured telemetry model capturing tool call ID, tool name, input arguments, execution result, timestamp, and millisecond latency for PostgreSQL/JSONL audit logging.
- **Integer Cent Monetary Representation:** Strict integer cent attributes (`_cents: int = Field(ge=0)`) preventing floating-point precision drift across statutory cooling-off and delay voucher calculations.
- **Observability Duration Constraint:** Non-negative duration bounds (`duration_ms: float = Field(ge=0.0)`) guaranteeing telemetry integrity.

---

### 2. 🧠 Architecture Decisions (ADR)

#### Decision: Shielded Envelope (`ToolExecutionResult`) vs Stack Exception Propagation
- **Option 1:** Allow tools to raise domain or infrastructure exceptions directly into the agent loop.
- **Option 2 (Selected):** Tools catch all internal failures and return `ToolExecutionResult(success=False, error_code=..., error_message=...)`.
- **Rationale:** Preserves the "Zero Naked Crash" architectural rule. In ReAct loops, tool failures must be ingested as structured environment observations, allowing the model to self-correct, try alternative parameters, or gracefully transition the FSM to `REQUIRES_HUMAN`.

#### Decision: Integer Cents vs Floating-Point Decimals for Financial Fields
- **Option 1:** Floating-point numbers (`float`) representing euros or dollars.
- **Option 2 (Selected):** Integer cents (`int = Field(ge=0)`).
- **Rationale:** Binary floating-point arithmetic introduces IEEE-754 precision inaccuracies that can lead to statutory calculation discrepancies. Using integer cents guarantees exact arithmetic and eliminates rounding drift.

#### Decision: Dedicated Audit Trace Contract (`ToolCallTrace`)
- **Option 1:** Ad-hoc structured dictionary logging in tool execution wrappers.
- **Option 2 (Selected):** Immutable `ToolCallTrace` DTO.
- **Rationale:** Standardizes trace structure across all tools, supports deterministic serialization for audit log persistence, and powers evaluation replay harnesses.

---

### 3. 🛠️ Implementation & Code
*Implementation details and validation commands.*

```python
# src/models/tools.py
from datetime import datetime
from typing import Any
from pydantic import Field
from models.base import BaseDTO
from models.enums import OrderStatusEnum, RefundReasonCode

__all__ = [
    "DeliveryDelayResult",
    "OrderDetailsResult",
    "RefundEligibilityResult",
    "ToolCallTrace",
    "ToolExecutionResult",
]

class OrderDetailsResult(BaseDTO):
    order_id: str
    status: OrderStatusEnum
    carrier: str
    tracking_number: str | None = None
    ordered_at: datetime
    shipped_at: datetime | None = None
    estimated_delivery: datetime
    actual_delivery: datetime | None = None
    items_total_ttc_cents: int = Field(ge=0)
    shipping_fee_ttc_cents: int = Field(ge=0)
    is_express: bool

class RefundEligibilityResult(BaseDTO):
    is_eligible_for_return: bool
    days_elapsed: int = Field(ge=0)
    refundable_items_total_cents: int = Field(ge=0)
    delay_compensation_voucher_cents: int = Field(ge=0)
    reason_code: RefundReasonCode

class DeliveryDelayResult(BaseDTO):
    delay_days: int
    is_delayed: bool

class ToolExecutionResult(BaseDTO):
    success: bool
    tool_name: str
    data: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None

class ToolCallTrace(BaseDTO):
    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]
    result: ToolExecutionResult
    timestamp: datetime
    duration_ms: float = Field(ge=0.0)
```

```bash
# Validation commands
make lint
make typecheck
make test
```

---

### 4. 📌 Session Checklist & Deliverables
1. [x] **Tool DTOs Defined (`src/models/tools.py`)**: `OrderDetailsResult`, `RefundEligibilityResult`, `DeliveryDelayResult`, `ToolExecutionResult`, `ToolCallTrace`.
2. [x] **Monetary and Duration Constraints Added**: `Field(ge=0)` on monetary cents, `Field(ge=0.0)` on `duration_ms`.
3. [x] **Dedicated Unit Test Suite (`tests/unit/test_tool_schemas.py`)** validating nominal cases, negative value rejections, error containers, and immutability.
4. [x] **Static Verification**: `make lint`, `make typecheck` (Mypy strict), and `make test` passing 100%.
