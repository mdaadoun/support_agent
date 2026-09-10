# Session 2.4: Final Certified Response Schema
**Date:** 2026-09-10

*Implemented the certified final response contract (`AgentFinalResponse`) in `src/models/response.py`, enforcing cross-field human escalation validation, strict FinOps and latency non-negativity invariants, confidence score bounds, and concise executive diagnostic summaries.*

---

### 1. 🎓 Concepts Introduced
- **Certified Response Contract (`AgentFinalResponse`):** Strongly-typed, immutable DTO representing the certified egress contract across API and CLI presentation layers.
- **Cross-Field Validation Gate:** Conditional enforcement via `@model_validator(mode="after")` guaranteeing that a non-empty `human_escalation_reason` is present whenever `status_resolution` is `REQUIRES_HUMAN_REVIEW`.
- **FinOps Telemetry Invariants:** Non-negative constraints on prompt/completion tokens, execution latency, and estimated USD expenditure embedded directly into the response payload.
- **Diagnostic Summary Boundary Constraint:** Strict `max_length=250` character limit on `internal_technical_summary` preventing verbose LLM output from cluttering monitoring queues.

---

### 2. 🧠 Architecture Decisions (ADR)

#### Decision: Cross-Field Validator for Human Escalation Rationale
- **Option 1:** Allow optional or unvalidated escalation reasons.
- **Option 2 (Selected):** Strict model validation requiring a non-empty string when `status_resolution == REQUIRES_HUMAN_REVIEW`.
- **Rationale:** Ensures human support agents receiving escalated tickets have clear, actionable technical context without searching raw trace logs.

#### Decision: Atomic Egress with Embedded FinOps & Latency Telemetry
- **Option 1:** Separate business responses from FinOps metrics.
- **Option 2 (Selected):** Embed FinOps token counts, USD cost estimation, and latency directly in `AgentFinalResponse`.
- **Rationale:** Provides callers and audit repositories with an atomic, certified snapshot of execution costs and performance alongside resolution state.

#### Decision: Deep Immutability on Actions Taken
- **Option 1:** Mutable `list[str]` of tool execution names.
- **Option 2 (Selected):** `tuple[str, ...] = Field(default_factory=tuple)`.
- **Rationale:** Preserves immutability under `frozen=True` and enables deterministic hashing.

---

### 3. 🛠️ Implementation & Code
*Implementation details and validation commands.*

```python
# src/models/response.py
from pydantic import Field, model_validator
from models.base import BaseDTO
from models.enums import IntentEnum, ResolutionStatusEnum

__all__ = ["AgentFinalResponse"]

class AgentFinalResponse(BaseDTO):
    session_id: str
    intent: IntentEnum
    confidence_score: float = Field(ge=0.0, le=1.0)
    order_id: str | None = None
    actions_taken: tuple[str, ...] = Field(default_factory=tuple)
    status_resolution: ResolutionStatusEnum
    human_escalation_reason: str | None = None
    internal_technical_summary: str = Field(max_length=250)
    email_response_subject: str
    email_response_body: str
    tokens_prompt: int = Field(default=0, ge=0)
    tokens_completion: int = Field(default=0, ge=0)
    cost_estimation_usd: float = Field(default=0.0, ge=0.0)
    execution_time_seconds: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def validate_escalation_metadata(self) -> "AgentFinalResponse":
        if (
            self.status_resolution == ResolutionStatusEnum.REQUIRES_HUMAN_REVIEW
            and not (
                self.human_escalation_reason and self.human_escalation_reason.strip()
            )
        ):
            raise ValueError(
                "human_escalation_reason is mandatory when status_resolution is REQUIRES_HUMAN_REVIEW"
            )
        return self
```

```bash
# Validation commands
make lint
make typecheck
make test
```

---

### 4. 📌 Session Checklist & Deliverables
1. [x] **`AgentFinalResponse` Schema Defined (`src/models/response.py`)** with cross-field validation and FinOps invariants.
2. [x] **Field Bounds and Validation Tested**: confidence score [0.0, 1.0], FinOps non-negativity, summary length limit.
3. [x] **Dedicated Unit Test Suite (`tests/unit/test_response_schema.py`)** verifying nominal cases, escalation validation, immutability, and attribute injection rejection.
4. [x] **Static Verification**: `make lint`, `make typecheck` (Mypy strict), and `make test` passing 100%.
