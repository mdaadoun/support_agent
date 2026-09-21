# Session 3.1: Statutory Withdrawal Business Logic (14-Day Rule)
**Date:** 2026-09-18

*Implemented deterministic pure Python calculation engine for the 14-day statutory cooling-off consumer protection rule under EU Directive 2011/83/EU. Enforced exact calendar-day arithmetic, timezone normalization to UTC, non-negative monetary boundary checks, undelivered order shielding with NOT_DELIVERED_YET, and domain exception shielding via BusinessRuleViolationError.*

---

### 1. 🎓 Concepts Introduced
- **Statutory Withdrawal Right (14-Day Rule):** Consumer protection standard under EU Directive 2011/83/EU entitling customers to a 14-calendar-day withdrawal window commencing upon physical delivery of goods.
- **Exact Calendar Day Computation:** Computing elapsed days via UTC-normalized calendar dates (`(date2 - date1).days`) rather than 24-hour timestamps in seconds, eliminating time-of-day discrepancies and timezone offset bugs.
- **Zero LLM Financial Authority:** Strict domain isolation ensuring that all monetary figures, refund amounts, and legal eligibility statuses originate from pure, tested Python functions rather than LLM generation.
- **Graceful Undelivered Inquiry Shielding:** Standardizing `RefundReasonCode.NOT_DELIVERED_YET` when an inquiry is received prior to delivery or without a confirmed delivery date, enabling structured agent observations without exception crashing.
- **Domain Business Rule Exception Shielding (`BusinessRuleViolationError`):** Specialized domain exception derived from `AppBaseError` protecting boundary invariants (non-negative monetary figures and strict datetime types).

---

### 2. 🧠 Architecture Decisions (ADR)

#### Decision: Exact Calendar Day Difference via UTC Normalization vs Seconds Elapsed
- **Option 1:** Fractional timestamp subtraction in seconds (`(req - del).total_seconds() / 86400 <= 14`).
- **Option 2 (Selected):** UTC-normalized calendar day difference (`(_to_utc_date(req) - _to_utc_date(del)).days <= 14`).
- **Rationale:** Under consumer protection law (Directive 2011/83/EU), cooling-off periods expire at the close of the 14th full calendar day following the physical receipt of goods, regardless of the time of day. Calculating exact calendar day difference avoids false rejections on day 14 due to delivery hour offsets and eliminates timezone offset drift.

#### Decision: Deterministic Pure Domain Function vs LLM Decision or Sandbox Code Execution
- **Option 1:** Prompt LLM to calculate dates or run Python REPL in sandbox.
- **Option 2 (Selected):** Pure deterministic Python function in `src/domain/business_rules.py`.
- **Rationale:** Enforces Universal Engineering Guardrail Rule 2 ("Zero LLM Financial & Operational Authority"). Eliminates stochastic hallucination, code injection security vulnerabilities, and latency, guaranteeing 100% mathematical consistency.

#### Decision: Graceful NOT_DELIVERED_YET Handling vs Exception Raising for Undelivered Orders
- **Option 1:** Raise an exception if `delivery_date` is `None` or `request_date < delivery_date`.
- **Option 2 (Selected):** Return `RefundEligibilityResult(is_eligible_for_return=False, reason_code=RefundReasonCode.NOT_DELIVERED_YET)`.
- **Rationale:** Premature inquiries for undelivered or in-transit orders are normal customer inquiries, not application crashes. Structured observation allows the ReAct loop to guide the customer cleanly without tripping error handling or cascading escalations.

#### Decision: Monetary Boundary Validation & Shielding via BusinessRuleViolationError
- **Option 1:** Raise raw `ValueError` on negative financial figures.
- **Option 2 (Selected):** Raise `BusinessRuleViolationError` inheriting from `AppBaseError`.
- **Rationale:** Enforces the "Zero Naked Crash" policy and Pax layer contracts, guaranteeing domain exceptions are uniformly typed, catchable via `AppBaseError`, and tagged with normalized error codes.

---

### 3. 🛠️ Implementation & Code
*Implementation details and validation commands.*

```python
# src/domain/business_rules.py
from datetime import date, datetime, timezone
from core.exceptions import BusinessRuleViolationError
from models.enums import RefundReasonCode
from models.tools import RefundEligibilityResult

def _to_utc_date(dt: datetime) -> date:
    if not isinstance(dt, datetime):
        raise BusinessRuleViolationError(
            f"Expected datetime instance, got {type(dt).__name__}.",
            error_code="INVALID_DATE_TYPE",
        )
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).date()
    return dt.date()

def calculate_statutory_withdrawal(
    delivery_date: datetime | None,
    request_date: datetime,
    item_prices_cents: list[int],
    shipping_fee_cents: int = 0,
) -> RefundEligibilityResult:
    if shipping_fee_cents < 0:
        raise BusinessRuleViolationError(
            f"Shipping fee cannot be negative, got {shipping_fee_cents}.",
            error_code="INVALID_MONETARY_VALUE",
        )
    if any(price < 0 for price in item_prices_cents):
        raise BusinessRuleViolationError(
            "Item prices cannot be negative.",
            error_code="INVALID_MONETARY_VALUE",
        )

    if delivery_date is None:
        return RefundEligibilityResult(
            is_eligible_for_return=False,
            days_elapsed=0,
            refundable_items_total_cents=0,
            delay_compensation_voucher_cents=0,
            reason_code=RefundReasonCode.NOT_DELIVERED_YET,
        )

    req_date = _to_utc_date(request_date)
    del_date = _to_utc_date(delivery_date)
    diff_days = (req_date - del_date).days

    if diff_days < 0:
        return RefundEligibilityResult(
            is_eligible_for_return=False,
            days_elapsed=0,
            refundable_items_total_cents=0,
            delay_compensation_voucher_cents=0,
            reason_code=RefundReasonCode.NOT_DELIVERED_YET,
        )

    is_eligible = diff_days <= 14
    refundable_total = sum(item_prices_cents) if is_eligible else 0
    reason_code = (
        RefundReasonCode.WITHIN_LEGAL_TIMEFRAME
        if is_eligible
        else RefundReasonCode.TIMEFRAME_EXCEEDED
    )

    return RefundEligibilityResult(
        is_eligible_for_return=is_eligible,
        days_elapsed=diff_days,
        refundable_items_total_cents=refundable_total,
        delay_compensation_voucher_cents=0,
        reason_code=reason_code,
    )
```

```bash
# Validation commands
make lint
make typecheck
make test
```

---

### 4. 📌 Session Checklist & Deliverables
1. [x] **calculate_statutory_withdrawal Implemented (`src/domain/business_rules.py`)** with exact 14-day calendar math and UTC date normalization.
2. [x] **BusinessRuleViolationError Defined (`src/core/exceptions.py`)** for domain invariant boundary shielding.
3. [x] **Tool Adapter Alignment (`src/tools/refund_calculator.py`)** allowing optional `delivery_date` for undelivered order queries.
4. [x] **Comprehensive Unit Test Suite (`tests/unit/test_business_rules.py`)** validating TC-03 nominal eligible refund, TC-04 expired refund, exact 14/15 boundary thresholds, leap years, timezones, and negative constraints.
5. [x] **Static Verification & CI Gates**: `make lint`, `make typecheck` (Mypy strict), and `make test` passing 100%.
