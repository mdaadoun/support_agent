# Session 3.2: Shipping Delay & Express Compensation Logic
**Date:** 2026-09-18

*Implemented deterministic calculation functions for logistics delay drift (`calculate_shipping_delay`) and commercial express delay compensation vouchers (`calculate_express_compensation`). Enforced UTC date normalization for calendar-day delay measurements, strict non-negative assertions on delay days and shipping fees via `BusinessRuleViolationError`, commercial policy voucher qualification (100% shipping fee voucher if `is_express` and `delay_days > 5`), and integrated express voucher tracking into statutory refund evaluation.*

---

### 1. 🎓 Concepts Introduced
- **Shipping Delay Drift:** Deterministic measurement of calendar days elapsed between promised delivery dates (`estimated_delivery_date`) and actual or reference evaluation dates (`reference_date`).
- **Express Compensation Voucher Policy:** Commercial customer service SLA rule granting an automatic 100% shipping fee voucher credit when an express shipment is delayed by strictly more than 5 full calendar days (`delay_days > 5`).
- **Decoupled Business Separation:** Separating factual logistical state determination (`DeliveryDelayResult`) from mutable commercial compensation policies (`calculate_express_compensation`).
- **Composite Reason Qualification (`RefundReasonCode.EXPRESS_DELAY_COMPENSATED`):** Automatic classification when an inquiry's return window is exceeded or undelivered, but qualifies for express shipping delay credit.

---

### 2. 🧠 Architecture Decisions (ADR)

#### Decision: Calendar Day Delay Drift via UTC Normalization vs Hourly Timestamp Subtraction
- **Option 1:** Fractional timestamp subtraction in seconds or hours (`(ref - est).total_seconds() / 86400`).
- **Option 2 (Selected):** UTC-normalized calendar day difference `max(0, (_to_utc_date(ref) - _to_utc_date(est)).days)`.
- **Rationale:** Delivery promises to customers are communicated on a calendar-day basis (e.g. "Delivery on Aug 17"). Intra-day hourly differences should not trigger false-positive delivery delays when delivery occurs on the expected date. UTC date normalization prevents timezone offset discrepancies.

#### Decision: Decoupled Pure Functions: Logistical Delay Drift vs Commercial Policy Compensation
- **Option 1:** Single monolithic function returning delay and voucher amounts together.
- **Option 2 (Selected):** Two distinct pure functions (`calculate_shipping_delay` and `calculate_express_compensation`).
- **Rationale:** Adheres to the Single Responsibility Principle: logistics drift is an objective operational fact (`DeliveryDelayResult`), whereas compensation vouchers reflect mutable commercial policy. Decoupling allows logistical delays to be queried by order status tools without calculating financial vouchers, and allows voucher calculations to be shared across refund and delay tools.

#### Decision: Strict Non-Negative Invariant Enforcement via BusinessRuleViolationError
- **Option 1:** Rely solely on Pydantic validation at tool boundaries.
- **Option 2 (Selected):** Assert `delay_days >= 0` and `shipping_fee_cents >= 0` in domain functions, raising `BusinessRuleViolationError`.
- **Rationale:** Enforces defense-in-depth within the Core Domain layer, guaranteeing that direct domain consumers or tests cannot pass invalid negative parameters without an explicit `AppBaseError` derivative being raised.

---

### 3. 🛠️ Implementation & Code
*Implementation details and validation commands.*

```python
# src/domain/business_rules.py
from datetime import datetime
from core.exceptions import BusinessRuleViolationError
from models.tools import DeliveryDelayResult

def calculate_shipping_delay(
    estimated_delivery_date: datetime,
    reference_date: datetime,
) -> DeliveryDelayResult:
    est_date = _to_utc_date(estimated_delivery_date)
    ref_date = _to_utc_date(reference_date)
    diff = (ref_date - est_date).days
    delay_days = max(0, diff)
    return DeliveryDelayResult(
        delay_days=delay_days,
        is_delayed=delay_days > 0,
    )

def calculate_express_compensation(
    delay_days: int,
    is_express: bool,
    shipping_fee_cents: int,
) -> int:
    if delay_days < 0:
        raise BusinessRuleViolationError(
            f"Delay days cannot be negative, got {delay_days}.",
            error_code="INVALID_DELAY_DAYS",
        )
    if shipping_fee_cents < 0:
        raise BusinessRuleViolationError(
            f"Shipping fee cannot be negative, got {shipping_fee_cents}.",
            error_code="INVALID_MONETARY_VALUE",
        )

    if is_express and delay_days > 5:
        return shipping_fee_cents
    return 0
```

```bash
# Validation commands
make lint
make typecheck
make test
```

---

### 4. 📌 Session Checklist & Deliverables
1. [x] **calculate_shipping_delay Implemented (`src/domain/business_rules.py`)** with UTC date normalization and calendar drift calculation.
2. [x] **calculate_express_compensation Implemented (`src/domain/business_rules.py`)** enforcing 100% voucher credit when `is_express` and `delay_days > 5`.
3. [x] **Refund Eligibility Integration (`src/domain/business_rules.py`)** supporting `is_express` and `delay_days` with `RefundReasonCode.EXPRESS_DELAY_COMPENSATED`.
4. [x] **Tool Adapter Alignment (`src/tools/refund_calculator.py` & `src/tools/delay_calculator.py`)** connecting arguments and domain logic.
5. [x] **Comprehensive Test Suite (`tests/unit/test_business_rules.py`)** verifying early/on-time/delayed orders, leap years, timezone normalization, 5-day boundary thresholds, and negative argument rejection.
6. [x] **Static Verification & CI Gates**: `make lint`, `make typecheck` (Mypy strict), and `make test` passing 100%.
