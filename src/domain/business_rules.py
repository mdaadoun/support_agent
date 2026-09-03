"""Deterministic domain business rules for statutory refunds and delay vouchers."""

from datetime import datetime

from models.enums import RefundReasonCode
from models.tools import DeliveryDelayResult, RefundEligibilityResult


def calculate_statutory_withdrawal(
    delivery_date: datetime,
    request_date: datetime,
    item_prices_cents: list[int],
    shipping_fee_cents: int,
) -> RefundEligibilityResult:
    """Evaluate eligibility under 14-day statutory cooling-off consumer law."""
    days_elapsed = (request_date.date() - delivery_date.date()).days
    if days_elapsed < 0:
        days_elapsed = 0

    is_eligible = days_elapsed <= 14
    refundable_total = sum(item_prices_cents) if is_eligible else 0
    reason_code = (
        RefundReasonCode.WITHIN_LEGAL_TIMEFRAME
        if is_eligible
        else RefundReasonCode.TIMEFRAME_EXCEEDED
    )

    return RefundEligibilityResult(
        is_eligible_for_return=is_eligible,
        days_elapsed=days_elapsed,
        refundable_items_total_cents=refundable_total,
        delay_compensation_voucher_cents=0,
        reason_code=reason_code,
    )


def calculate_shipping_delay(
    estimated_delivery_date: datetime,
    reference_date: datetime,
) -> DeliveryDelayResult:
    """Compute shipping delay in calendar days relative to expected date."""
    diff = (reference_date.date() - estimated_delivery_date.date()).days
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
    """Grant 100% shipping fee voucher if express shipment delayed over 5 days."""
    if is_express and delay_days > 5:
        return shipping_fee_cents
    return 0
