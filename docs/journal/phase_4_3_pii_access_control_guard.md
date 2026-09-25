# Session 4.3: PII Access Control Guard
**Date:** 2026-09-25

*Implemented the PII Access Control Guard in `src/security/access_control.py` to prevent unauthorized disclosure of customer order metadata. The guard provides canonical email normalization and syntax validation, non-throwing boolean authorization predicates (`is_authorized`), strict access assertions (`verify_order_access`, `verify_order_record_access`) raising `SecurityAccessError` on mismatch, fail-closed metadata containment ensuring zero PII leakage in exception messages, and proactive tool exception shielding returning standardized `ToolExecutionResult` payloads with machine-readable error code `SECURITY_UNAUTHORIZED_ACCESS`.*

---

### 1. 🎓 Concepts Introduced
- **PII Access Control Guard:** A defensive security boundary module enforcing strict cross-authorization by verifying that the authenticated sender's identity matches the customer record associated with a queried entity.
- **Fail-Closed Metadata Containment:** A security design principle ensuring that when an authorization check fails, the system terminates access immediately and withholds all entity metadata, customer identities, or state details from the response.
- **Cross-Authorization Verification:** The validation that an authenticated user possesses explicit ownership or authorized access rights to an individual entity (e.g. order) rather than merely possessing a valid user account.
- **Tool Execution Shielding:** An architectural pattern where security violations or execution failures within tools return a structured, machine-readable result payload (`ToolExecutionResult(success=False, error_code=...)`) rather than crashing the calling agent loop with an unhandled exception.
- **Opaque Security Error:** A sanitized error response that communicates access rejection without revealing internal system state, owner identities, or whether a queried entity even exists.

---

### 2. 🧠 Architecture Decisions (ADR)

#### Decision: Fail-Closed Metadata Containment in Exception Messages
- **Option 1:** Include the expected owner email or order ID in the exception message for easier debugging (e.g. mismatch details).
- **Option 2 (Selected):** Generic opaque exception message (`Unauthorized access attempt: Sender email does not match order record.`) while logging full context internally via structured logger.
- **Rationale:** Disclosing the order owner's email address or sensitive logistical details in error messages creates a critical PII data leakage vulnerability. An attacker probing random order IDs would receive confirmation of legitimate customer email addresses. The guard logs the full context internally via structured logger while raising an opaque domain exception.

#### Decision: Two-Tier Authorization Contract (Assertion vs. Shielding Result)
- **Option 1:** Only provide raising assertion `verify_order_access`, or only return `ToolExecutionResult`.
- **Option 2 (Selected):** Provide both strict assertions (`verify_order_access`) and shielded results (`shield_unauthorized_access`).
- **Rationale:** Different execution contexts require different control flows. Direct domain services and FSM transitions require fail-fast exception throwing (`verify_order_access`), while MCP tool adapters and ReAct loops require shielded execution results (`shield_unauthorized_access` returning `ToolExecutionResult(success=False, error_code="SECURITY_UNAUTHORIZED_ACCESS")`) to uphold the "Zero Naked Crash" policy and prevent agent loop termination.

#### Decision: Canonical Case and Whitespace Normalization prior to Identity Comparison
- **Option 1:** Perform raw string equality `sender_email == order_customer_email`.
- **Option 2 (Selected):** Canonicalize both sender and owner addresses via `normalize_email` (`.strip().lower()`).
- **Rationale:** Email addresses are case-insensitive per RFC 5321 (especially the domain part), and user inputs often contain inadvertent leading or trailing whitespace. Canonicalizing both sender and owner addresses via `normalize_email` prevents false-negative access denials for legitimate customers while validating strict syntax.

#### Decision: Polymorphic Order Record Access Verification (dict and BaseModel)
- **Option 1:** Require callers to manually extract `order_customer_email` as a string before calling the guard.
- **Option 2 (Selected):** Provide `verify_order_record_access` accepting both raw dictionaries and `BaseModel` instances.
- **Rationale:** Callers in different layers interact with orders as either raw dictionaries (Mock ERP store, JSON responses) or immutable Pydantic models (`OrderDetailsResult`). Providing `verify_order_record_access` centralizes attribute extraction and error checking, raising `BusinessRuleViolationError("MISSING_CUSTOMER_EMAIL")` if the record lacks an owner attribute.

---

### 3. 🛠️ Implementation & Code
*Implementation details and validation commands.*

```python
# src/security/access_control.py
from typing import Any
from pydantic import BaseModel
from core.exceptions import BusinessRuleViolationError, SecurityAccessError
from models.tools import ToolExecutionResult
from observability.logger import get_logger
from security.sanitizer import is_valid_email

logger = get_logger(__name__)

class AccessControlGuard:
    @staticmethod
    def normalize_email(email: str) -> str:
        if not isinstance(email, str):
            raise BusinessRuleViolationError(
                f"Expected email string, got {type(email).__name__}",
                error_code="INVALID_PAYLOAD_TYPE",
            )
        cleaned = email.strip().lower()
        if not cleaned:
            raise BusinessRuleViolationError(
                "Email address cannot be empty.",
                error_code="INVALID_PAYLOAD_TYPE",
            )
        if not is_valid_email(cleaned):
            raise BusinessRuleViolationError(
                f"Malformed email address syntax: '{cleaned}'",
                error_code="INVALID_EMAIL_SYNTAX",
            )
        return cleaned

    @classmethod
    def is_authorized(cls, sender_email: str, order_customer_email: str) -> bool:
        try:
            norm_sender = cls.normalize_email(sender_email)
            norm_owner = cls.normalize_email(order_customer_email)
            return norm_sender == norm_owner
        except Exception:
            return False

    @classmethod
    def verify_order_access(cls, sender_email: str, order_customer_email: str) -> None:
        normalized_sender = cls.normalize_email(sender_email)
        normalized_owner = cls.normalize_email(order_customer_email)

        if normalized_sender != normalized_owner:
            logger.warning(
                "security_access_denied",
                sender_email=normalized_sender,
                order_owner=normalized_owner,
            )
            raise SecurityAccessError(
                "Unauthorized access attempt: Sender email does not match order record."
            )

    @classmethod
    def shield_unauthorized_access(
        cls,
        tool_name: str,
        sender_email: str,
        order_customer_email: str,
    ) -> ToolExecutionResult | None:
        if not cls.is_authorized(sender_email, order_customer_email):
            logger.warning(
                "security_tool_access_shielded",
                tool_name=tool_name,
                sender_email=sender_email,
            )
            return ToolExecutionResult(
                success=False,
                tool_name=tool_name,
                error_code="SECURITY_UNAUTHORIZED_ACCESS",
                error_message="Unauthorized access attempt: Sender email does not match order record.",
            )
        return None
```

```bash
# Validation commands
make lint
make typecheck
make test
```

---

### 4. 📌 Session Checklist & Deliverables
1. [x] **Canonical Email Normalization (`normalize_email`)**: Strips whitespace, lowercases, and validates syntax.
2. [x] **Safe Authorization Predicate (`is_authorized`)**: Returns boolean status without raising exceptions.
3. [x] **Fail-Closed Access Verification (`verify_order_access`)**: Raises `SecurityAccessError` with `SECURITY_UNAUTHORIZED_ACCESS` and zero metadata leakage.
4. [x] **Polymorphic Record Verification (`verify_order_record_access`)**: Supports both dictionaries and Pydantic models.
5. [x] **Tool Exception Shielding (`shield_unauthorized_access`)**: Returns standardized `ToolExecutionResult` on unauthorized requests.
6. [x] **Comprehensive Test Suite (`tests/unit/test_access_control.py`)**: 151 tests passing across normalization, mismatch containment, and shielding.
7. [x] **Quality Gates Verified**: `make lint`, `make typecheck` (Mypy strict), and `make test` passing 100%.
