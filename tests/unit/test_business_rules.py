"""Unit tests verifying deterministic domain business rules and calculations."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from core.exceptions import AppBaseError, BusinessRuleViolationError
from domain.business_rules import (
    calculate_express_compensation,
    calculate_shipping_delay,
    calculate_statutory_withdrawal,
)
from models.enums import RefundReasonCode
from models.tools import DeliveryDelayResult, RefundEligibilityResult


@pytest.mark.parametrize(
    ("days_offset", "expected_eligible", "expected_reason"),
    [
        (0, True, RefundReasonCode.WITHIN_LEGAL_TIMEFRAME),
        (1, True, RefundReasonCode.WITHIN_LEGAL_TIMEFRAME),
        (8, True, RefundReasonCode.WITHIN_LEGAL_TIMEFRAME),  # TC-03 nominal eligible
        (14, True, RefundReasonCode.WITHIN_LEGAL_TIMEFRAME),  # 14-day exact boundary
        (15, False, RefundReasonCode.TIMEFRAME_EXCEEDED),  # 15-day immediate expiry
        (25, False, RefundReasonCode.TIMEFRAME_EXCEEDED),  # TC-04 expired return
    ],
)
def test_statutory_withdrawal_cooling_off_thresholds(
    days_offset: int,
    expected_eligible: bool,
    expected_reason: RefundReasonCode,
) -> None:
    """Validate 14-day statutory withdrawal rule across exact calendar day boundaries."""
    del_dt = datetime(2026, 8, 24, 15, 12, tzinfo=timezone.utc)
    req_dt = del_dt + timedelta(days=days_offset)

    res = calculate_statutory_withdrawal(del_dt, req_dt, [8990], 490)
    assert isinstance(res, RefundEligibilityResult)
    assert res.is_eligible_for_return is expected_eligible
    assert res.days_elapsed == days_offset
    assert res.reason_code == expected_reason
    assert res.refundable_items_total_cents == (8990 if expected_eligible else 0)


@pytest.mark.parametrize(
    ("del_date", "req_date"),
    [
        (None, datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)),
        (
            datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc),
            datetime(2026, 9, 5, 8, 0, tzinfo=timezone.utc),
        ),
    ],
)
def test_statutory_withdrawal_not_delivered_states(
    del_date: datetime | None, req_date: datetime
) -> None:
    """Validate undelivered or premature inquiries return NOT_DELIVERED_YET."""
    res = calculate_statutory_withdrawal(del_date, req_date, [4500])
    assert res.is_eligible_for_return is False
    assert res.days_elapsed == 0
    assert res.refundable_items_total_cents == 0
    assert res.reason_code == RefundReasonCode.NOT_DELIVERED_YET


def test_statutory_withdrawal_edge_cases() -> None:
    """Validate leap year math, timezone offsets, multi-items, and immutability."""
    # Leap year (2024): Feb 20 -> Mar 5 is 14 days, Mar 6 is 15 days
    leap_del = datetime(2024, 2, 20, 10, 0, tzinfo=timezone.utc)
    assert calculate_statutory_withdrawal(
        leap_del, datetime(2024, 3, 5, 12, 0, tzinfo=timezone.utc), [1000]
    ).is_eligible_for_return
    assert not calculate_statutory_withdrawal(
        leap_del, datetime(2024, 3, 6, 8, 0, tzinfo=timezone.utc), [1000]
    ).is_eligible_for_return

    # Timezone-aware vs naive
    tz_del = datetime(2026, 8, 10, 22, 0, tzinfo=timezone(timedelta(hours=4)))
    tz_req = datetime(2026, 8, 20, 14, 0, tzinfo=timezone.utc)
    assert calculate_statutory_withdrawal(tz_del, tz_req, [2000]).days_elapsed == 10

    # Multi-items sum and immutability
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    res = calculate_statutory_withdrawal(now, now, [1299, 3450, 990])
    assert res.refundable_items_total_cents == 5739
    with pytest.raises(ValidationError):
        res.refundable_items_total_cents = 0


@pytest.mark.parametrize(
    ("ref_offset", "expected_delay", "expected_is_delayed"),
    [
        (-2, 0, False),  # Delivered early
        (0, 0, False),  # Delivered on time
        (1, 1, True),  # 1 day delay
        (6, 6, True),  # 6 days delay (TC-02)
    ],
)
def test_shipping_delay_calendar_computations(
    ref_offset: int, expected_delay: int, expected_is_delayed: bool
) -> None:
    """Validate shipping delay calculation across early, on-time, and delayed cases."""
    est_date = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
    ref_date = est_date + timedelta(days=ref_offset)

    delay_res = calculate_shipping_delay(est_date, ref_date)
    assert isinstance(delay_res, DeliveryDelayResult)
    assert delay_res.delay_days == expected_delay
    assert delay_res.is_delayed is expected_is_delayed


def test_shipping_delay_timezones_and_validation() -> None:
    """Validate shipping delay timezone normalization and invalid type rejection."""
    tz_p3 = timezone(timedelta(hours=3))
    est_date = datetime(2026, 8, 17, 23, 0, tzinfo=tz_p3)  # 20:00 UTC Aug 17
    ref_date = datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc)  # Aug 23

    res = calculate_shipping_delay(est_date, ref_date)
    assert res.delay_days == 6
    assert res.is_delayed is True

    # Leap year crossing
    leap_est = datetime(2024, 2, 28, 10, 0, tzinfo=timezone.utc)
    leap_ref = datetime(2024, 3, 2, 10, 0, tzinfo=timezone.utc)
    assert calculate_shipping_delay(leap_est, leap_ref).delay_days == 3

    with pytest.raises(BusinessRuleViolationError) as exc_info:
        calculate_shipping_delay("2026-08-17", ref_date)  # type: ignore[arg-type]
    assert exc_info.value.error_code == "INVALID_DATE_TYPE"


@pytest.mark.parametrize(
    ("delay_days", "is_express", "shipping_fee", "expected_voucher"),
    [
        (6, True, 1200, 1200),  # TC-02: Express delayed > 5 days -> 100% voucher
        (5, True, 1200, 0),  # Boundary: Exactly 5 days -> No voucher
        (0, True, 1200, 0),  # On-time express -> No voucher
        (10, False, 500, 0),  # Standard shipping delayed -> No voucher
        (10, True, 0, 0),  # Free express shipping -> 0 voucher
    ],
)
def test_express_compensation_commercial_policy(
    delay_days: int, is_express: bool, shipping_fee: int, expected_voucher: int
) -> None:
    """Validate express compensation rules granting 100% voucher when delay > 5 days."""
    voucher = calculate_express_compensation(
        delay_days=delay_days,
        is_express=is_express,
        shipping_fee_cents=shipping_fee,
    )
    assert voucher == expected_voucher


def test_express_compensation_validation() -> None:
    """Validate negative delay days or negative shipping fee rejection."""
    with pytest.raises(BusinessRuleViolationError) as exc_info_delay:
        calculate_express_compensation(
            delay_days=-1, is_express=True, shipping_fee_cents=1000
        )
    assert exc_info_delay.value.error_code == "INVALID_DELAY_DAYS"

    with pytest.raises(BusinessRuleViolationError) as exc_info_fee:
        calculate_express_compensation(
            delay_days=6, is_express=True, shipping_fee_cents=-100
        )
    assert exc_info_fee.value.error_code == "INVALID_MONETARY_VALUE"


def test_statutory_withdrawal_with_express_delay_voucher() -> None:
    """Validate integrated statutory withdrawal combining return window and delay voucher."""
    del_dt = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
    req_dt = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)  # 25 days later

    # Expired return + express delay > 5 days -> EXPRESS_DELAY_COMPENSATED
    res_expired_voucher = calculate_statutory_withdrawal(
        delivery_date=del_dt,
        request_date=req_dt,
        item_prices_cents=[5900],
        shipping_fee_cents=1200,
        is_express=True,
        delay_days=6,
    )
    assert res_expired_voucher.is_eligible_for_return is False
    assert res_expired_voucher.refundable_items_total_cents == 0
    assert res_expired_voucher.delay_compensation_voucher_cents == 1200
    assert res_expired_voucher.reason_code == RefundReasonCode.EXPRESS_DELAY_COMPENSATED

    # Valid return + express delay voucher
    req_dt_valid = del_dt + timedelta(days=8)
    res_valid_voucher = calculate_statutory_withdrawal(
        delivery_date=del_dt,
        request_date=req_dt_valid,
        item_prices_cents=[5900],
        shipping_fee_cents=1200,
        is_express=True,
        delay_days=6,
    )
    assert res_valid_voucher.is_eligible_for_return is True
    assert res_valid_voucher.refundable_items_total_cents == 5900
    assert res_valid_voucher.delay_compensation_voucher_cents == 1200
    assert res_valid_voucher.reason_code == RefundReasonCode.WITHIN_LEGAL_TIMEFRAME


def test_statutory_withdrawal_validation_rejections() -> None:
    """Validate negative monetary values and invalid date types trigger errors."""
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)

    with pytest.raises(BusinessRuleViolationError) as exc_price:
        calculate_statutory_withdrawal(now, now, [1000, -500])
    assert exc_price.value.error_code == "INVALID_MONETARY_VALUE"

    with pytest.raises(BusinessRuleViolationError) as exc_fee:
        calculate_statutory_withdrawal(now, now, [1000], shipping_fee_cents=-1)
    assert exc_fee.value.error_code == "INVALID_MONETARY_VALUE"

    with pytest.raises(BusinessRuleViolationError) as exc_date:
        calculate_statutory_withdrawal("invalid_date", now, [1000])  # type: ignore[arg-type]
    assert exc_date.value.error_code == "INVALID_DATE_TYPE"
    assert issubclass(BusinessRuleViolationError, AppBaseError)
