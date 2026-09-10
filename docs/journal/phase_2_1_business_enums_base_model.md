# Session 2.1: Business Enums & Base Model
**Date:** 2026-09-10

*Established foundational domain contracts and enumerations for the autonomous customer support agent, implementing `BaseDTO` with strict immutability (`frozen=True`) and attribute rejection (`extra="forbid"`), alongside standardizing business enums (`OrderStatusEnum`, `IntentEnum`, `RefundReasonCode`, `ResolutionStatusEnum`) using Python 3.11+ `StrEnum`.*

---

### 1. 🎓 Concepts Introduced
- **BaseDTO Immutability:** Root Pydantic V2 model contract enforcing `model_config = ConfigDict(frozen=True, extra="forbid")`, guaranteeing that all domain models are immutable post-creation and reject unmapped attributes.
- **Python 3.11+ StrEnum:** String-backed enumerations that are direct instances of `str`, eliminating `.value` indirection, enabling zero-cost JSON serialization, and providing exhaustive static typing under Mypy strict mode.
- **Schema Drift & Parameter Injection Defense:** Using `extra="forbid"` to fail fast at the boundary against hostile parameter injection or accidental payload drift.

---

### 2. 🧠 Architecture Decisions (ADR)

#### Decision: BaseDTO Immutability (`frozen=True`) & Strict Rejection (`extra="forbid"`)
- **Option 1:** Use default mutable Pydantic models with `extra="ignore"`.
- **Option 2 (Selected):** Enforce `ConfigDict(frozen=True, extra="forbid")` across all domain DTOs.
- **Rationale:** In multi-step agentic systems with concurrent tool executions, immutable models eliminate data races, enable safe state snapshots, and allow DTOs to be hashable (`__hash__`) for use in sets and caches. Forbidding extra fields stops silent schema drift and rejects prompt-injected payload properties.

#### Decision: Native Python 3.11+ `StrEnum`
- **Option 1:** Standard `enum.Enum` or `(str, Enum)`.
- **Option 2:** Type-only `Literal[...]` unions.
- **Option 3 (Selected):** Standard library `StrEnum`.
- **Rationale:** `StrEnum` satisfies both `isinstance(x, str)` and `isinstance(x, Enum)`, serializing directly to JSON string values without custom encoders while providing runtime validation and static exhaustiveness checking.

---

### 3. 🛠️ Implementation & Code
*Implementation details and validation commands.*

```python
# src/models/base.py
from pydantic import BaseModel, ConfigDict

__all__ = ["BaseDTO"]

class BaseDTO(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

# src/models/enums.py
from enum import StrEnum

__all__ = [
    "IntentEnum",
    "OrderStatusEnum",
    "RefundReasonCode",
    "ResolutionStatusEnum",
]

class OrderStatusEnum(StrEnum):
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    DELAYED = "DELAYED"
    # ...
```

```bash
# Validation commands
make lint
make typecheck
make test
```

---

### 4. 📌 Session Checklist & Deliverables
1. [x] **BaseDTO Implemented (`src/models/base.py`)** with `frozen=True` and `extra="forbid"`.
2. [x] **Business Enums Defined (`src/models/enums.py`)**: `OrderStatusEnum`, `IntentEnum`, `RefundReasonCode`, `ResolutionStatusEnum`.
3. [x] **Unit Verification Suite (`tests/unit/test_schemas.py`)** asserting immutability, extra attribute rejection, hashability, and enum validation.
4. [x] **Static Verification**: `make lint`, `make typecheck` (Mypy strict), and `make test` passing 100%.
