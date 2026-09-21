"""Deterministic domain business rules for statutory refunds and delay vouchers."""

from datetime import date, datetime, timezone

from core.exceptions import BusinessRuleViolationError
from models.enums import RefundReasonCode
from models.tools import DeliveryDelayResult, RefundEligibilityResult

__all__ = [
    "calculate_express_compensation",
    "calculate_shipping_delay",
    "calculate_statutory_withdrawal",
]


def _to_utc_date(dt: datetime) -> date:
    """Normalize datetime to UTC date for deterministic calendar day calculation."""
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
    is_express: bool = False,
    delay_days: int = 0,
) -> RefundEligibilityResult:
    """Evaluate eligibility under EU Directive 2011/83/EU 14-day statutory cooling-off law.

    The 14-day cooling-off period starts from the calendar day the consumer acquires
    physical possession of the goods (confirmed delivery date). The request is valid if
    the elapsed calendar days between request_date and delivery_date is <= 14 days.
    Also incorporates express shipping delay voucher compensation if applicable.

    Args:
        delivery_date: Confirmed delivery datetime of the order (or None if not delivered).
        request_date: Inbound customer inquiry datetime.
        item_prices_cents: Unit prices of purchased items in euro cents (non-negative).
        shipping_fee_cents: Shipping fee in euro cents (non-negative, default 0).
        is_express: Whether the order was shipped via express delivery.
        delay_days: Observed delivery delay in calendar days (default 0).

    Returns:
        RefundEligibilityResult containing deterministic eligibility status,
        elapsed calendar days, refundable items total in cents, voucher credit,
        and machine-readable reason code.

    Raises:
        BusinessRuleViolationError: If monetary values are negative or request_date is invalid.
    """
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

    voucher_cents = calculate_express_compensation(
        delay_days=delay_days,
        is_express=is_express,
        shipping_fee_cents=shipping_fee_cents,
    )

    if delivery_date is None:
        reason = (
            RefundReasonCode.EXPRESS_DELAY_COMPENSATED
            if voucher_cents > 0
            else RefundReasonCode.NOT_DELIVERED_YET
        )
        return RefundEligibilityResult(
            is_eligible_for_return=False,
            days_elapsed=0,
            refundable_items_total_cents=0,
            delay_compensation_voucher_cents=voucher_cents,
            reason_code=reason,
        )

    req_date = _to_utc_date(request_date)
    del_date = _to_utc_date(delivery_date)
    diff_days = (req_date - del_date).days

    if diff_days < 0:
        reason = (
            RefundReasonCode.EXPRESS_DELAY_COMPENSATED
            if voucher_cents > 0
            else RefundReasonCode.NOT_DELIVERED_YET
        )
        return RefundEligibilityResult(
            is_eligible_for_return=False,
            days_elapsed=0,
            refundable_items_total_cents=0,
            delay_compensation_voucher_cents=voucher_cents,
            reason_code=reason,
        )

    is_eligible = diff_days <= 14
    refundable_total = sum(item_prices_cents) if is_eligible else 0
    if is_eligible:
        reason_code = RefundReasonCode.WITHIN_LEGAL_TIMEFRAME
    elif voucher_cents > 0:
        reason_code = RefundReasonCode.EXPRESS_DELAY_COMPENSATED
    else:
        reason_code = RefundReasonCode.TIMEFRAME_EXCEEDED

    return RefundEligibilityResult(
        is_eligible_for_return=is_eligible,
        days_elapsed=diff_days,
        refundable_items_total_cents=refundable_total,
        delay_compensation_voucher_cents=voucher_cents,
        reason_code=reason_code,
    )


def calculate_shipping_delay(
    estimated_delivery_date: datetime,
    reference_date: datetime,
) -> DeliveryDelayResult:
    """Compute shipping delay in calendar days relative to expected delivery date.

    Normalizes datetimes to UTC dates before evaluating elapsed calendar days.
    If reference_date <= estimated_delivery_date, delay_days is 0 and is_delayed is False.

    Args:
        estimated_delivery_date: Promised delivery date from carrier / ERP.
        reference_date: Current evaluation date or actual delivery timestamp.

    Returns:
        DeliveryDelayResult with integer delay_days and is_delayed boolean flag.

    Raises:
        BusinessRuleViolationError: If date inputs are not datetime instances.
    """
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
    """Grant 100% shipping fee voucher if express shipment delayed over 5 days.

    Under commercial policy, express shipments delayed more than 5 calendar days
    (i.e. delay_days > 5) receive an automatic 100% shipping fee voucher credit.
    Standard shipments or delays of 5 days or fewer do not qualify.

    Args:
        delay_days: Net calendar days of observed delivery delay (must be >= 0).
        is_express: Boolean flag indicating if order used express shipping.
        shipping_fee_cents: Shipping fee in euro cents charged on the order (must be >= 0).

    Returns:
        Compensation voucher amount in euro cents (equal to shipping_fee_cents or 0).

    Raises:
        BusinessRuleViolationError: If delay_days or shipping_fee_cents is negative.
    """
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
