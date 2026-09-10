# Session 2.2: Ingestion & Extraction Schemas
**Date:** 2026-09-10

*Implemented foundational ingestion and extraction DTO contracts (`InboundEmailMessage`, `ExtractedDemand`) enforcing RFC-compliant email syntax validation, strict regex pattern validation for ERP order identifiers (`^CMD-[0-9]{5,8}$`), deep immutability via `tuple[str, ...]`, and strict boundary field forbidding.*

---

### 1. 🎓 Concepts Introduced
- **Boundary Ingestion Contract (`InboundEmailMessage`):** Structured, immutable DTO capturing inbound email data with fail-fast `EmailStr` syntax validation and non-empty string guarantees.
- **Pre-Extraction Entity Schema (`ExtractedDemand`):** Structured entity representing parsed customer intent, validated order reference, legal threat classification, and sub-queries.
- **Deep Immutability Pattern:** Utilizing `tuple[str, ...]` rather than mutable `list` in frozen models to guarantee complete immutability and preserve deterministic hashability.
- **Fail-Fast Regex Boundary Enforcement:** Anchored regex pattern (`^CMD-[0-9]{5,8}$`) halting malformed order references before tool dispatch, protecting downstream ERP APIs.

---

### 2. 🧠 Architecture Decisions (ADR)

#### Decision: RFC Email Syntax Validation via `EmailStr`
- **Option 1:** Unvalidated `str` or loose custom regex in presentation handlers.
- **Option 2 (Selected):** `pydantic.EmailStr` on `InboundEmailMessage.sender_email` and `ExtractedDemand.customer_email`.
- **Rationale:** Normalizes email addresses, eliminates parser discrepancies, and ensures fail-fast rejection of malformed addresses before security PII matching or ERP querying.

#### Decision: Strict Bounded Regex for Order IDs (`^CMD-[0-9]{5,8}$`)
- **Option 1:** Unrestricted string or late validation inside ERP client.
- **Option 2 (Selected):** Strict regex pattern validation at DTO boundary.
- **Rationale:** Prevents unnecessary external tool dispatches, stops invalid order formats from consuming API rate limits or tripping circuit breakers, and mitigates injection attacks.

#### Decision: Immutable Tuples for Nested Collections (`sub_queries`)
- **Option 1:** Standard mutable `list[str]`.
- **Option 2 (Selected):** Immutable `tuple[str, ...]`.
- **Rationale:** In frozen Pydantic models, mutable lists allow in-place mutations (`.append()`), breaking immutability guarantees across asynchronous agent execution cycles. Tuples guarantee deep immutability.

---

### 3. 🛠️ Implementation & Code
*Implementation details and validation commands.*

```python
# src/models/email.py
from datetime import datetime
from pydantic import EmailStr, Field
from models.base import BaseDTO

__all__ = ["InboundEmailMessage"]

class InboundEmailMessage(BaseDTO):
    message_id: str = Field(min_length=1)
    sender_email: EmailStr
    subject: str = Field(min_length=1)
    body_text: str = Field(min_length=1)
    received_at: datetime

# src/models/extraction.py
from pydantic import EmailStr, Field
from models.base import BaseDTO
from models.enums import IntentEnum

__all__ = ["ExtractedDemand"]

class ExtractedDemand(BaseDTO):
    intent: IntentEnum
    order_id: str | None = Field(default=None, pattern=r"^CMD-[0-9]{5,8}$")
    customer_email: EmailStr
    is_legal_threat_or_aggressive: bool = False
    sub_queries: tuple[str, ...] = Field(default_factory=tuple)
```

```bash
# Validation commands
make lint
make typecheck
make test
```

---

### 4. 📌 Session Checklist & Deliverables
1. [x] **InboundEmailMessage Defined (`src/models/email.py`)** with `EmailStr`, non-empty strings, and `__all__` export.
2. [x] **ExtractedDemand Defined (`src/models/extraction.py`)** with `CMD-[0-9]{5,8}` regex pattern, `tuple[str, ...]`, and `__all__` export.
3. [x] **Single-Responsibility Unit Tests (`tests/unit/test_ingestion_extraction.py`)** verifying email syntax, regex bounds, defaults, and immutability.
4. [x] **Static Verification**: `make lint`, `make typecheck` (Mypy strict), and `make test` passing 100%.
