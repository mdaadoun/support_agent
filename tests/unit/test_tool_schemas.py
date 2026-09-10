"""Unit tests verifying tool execution and trace DTO schemas."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from models.enums import OrderStatusEnum, RefundReasonCode
from models.tools import (
    DeliveryDelayResult,
    OrderDetailsResult,
    RefundEligibilityResult,
    ToolCallTrace,
    ToolExecutionResult,
)


def test_order_details_result_valid() -> None:
    """Validate nominal OrderDetailsResult with complete fields."""
    now = datetime.now(timezone.utc)
    res = OrderDetailsResult(
        order_id="CMD-10001",
        status=OrderStatusEnum.SHIPPED,
        carrier="DHL",
        tracking_number="DHL-9999",
        ordered_at=now,
        shipped_at=now,
        estimated_delivery=now,
        actual_delivery=None,
        items_total_ttc_cents=4500,
        shipping_fee_ttc_cents=500,
        is_express=True,
    )
    assert res.order_id == "CMD-10001"
    assert res.status == OrderStatusEnum.SHIPPED
    assert res.tracking_number == "DHL-9999"
    assert res.items_total_ttc_cents == 4500
    assert res.is_express is True


def test_order_details_result_immutability_and_extra_forbid() -> None:
    """Validate OrderDetailsResult is frozen and forbids extra fields."""
    now = datetime.now(timezone.utc)
    res = OrderDetailsResult(
        order_id="CMD-10001",
        status=OrderStatusEnum.DELIVERED,
        carrier="Colissimo",
        ordered_at=now,
        estimated_delivery=now,
        items_total_ttc_cents=1000,
        shipping_fee_ttc_cents=0,
        is_express=False,
    )
    with pytest.raises(ValidationError):
        res.carrier = "FedEx"

    with pytest.raises(ValidationError):
        OrderDetailsResult(
            order_id="CMD-10001",
            status=OrderStatusEnum.DELIVERED,
            carrier="Colissimo",
            ordered_at=now,
            estimated_delivery=now,
            items_total_ttc_cents=1000,
            shipping_fee_ttc_cents=0,
            is_express=False,
            extra_field="invalid",  # type: ignore[call-arg]
        )


@pytest.mark.parametrize(
    ("items_total", "shipping_fee"),
    [
        (-1, 500),
        (500, -1),
    ],
)
def test_order_details_negative_monetary_values(
    items_total: int, shipping_fee: int
) -> None:
    """Validate negative financial amounts raise ValidationError."""
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        OrderDetailsResult(
            order_id="CMD-10001",
            status=OrderStatusEnum.DELIVERED,
            carrier="Colissimo",
            ordered_at=now,
            estimated_delivery=now,
            items_total_ttc_cents=items_total,
            shipping_fee_ttc_cents=shipping_fee,
            is_express=False,
        )


def test_refund_eligibility_result_valid() -> None:
    """Validate RefundEligibilityResult instantiation and fields."""
    res = RefundEligibilityResult(
        is_eligible_for_return=True,
        days_elapsed=7,
        refundable_items_total_cents=2990,
        delay_compensation_voucher_cents=0,
        reason_code=RefundReasonCode.WITHIN_LEGAL_TIMEFRAME,
    )
    assert res.is_eligible_for_return is True
    assert res.days_elapsed == 7
    assert res.refundable_items_total_cents == 2990
    assert res.reason_code == RefundReasonCode.WITHIN_LEGAL_TIMEFRAME


@pytest.mark.parametrize(
    ("days", "items_cents", "voucher_cents"),
    [
        (-1, 1000, 0),
        (5, -1, 0),
        (5, 1000, -1),
    ],
)
def test_refund_eligibility_negative_constraints(
    days: int, items_cents: int, voucher_cents: int
) -> None:
    """Validate negative integers trigger ValidationError on RefundEligibilityResult."""
    with pytest.raises(ValidationError):
        RefundEligibilityResult(
            is_eligible_for_return=False,
            days_elapsed=days,
            refundable_items_total_cents=items_cents,
            delay_compensation_voucher_cents=voucher_cents,
            reason_code=RefundReasonCode.TIMEFRAME_EXCEEDED,
        )


def test_delivery_delay_result() -> None:
    """Validate DeliveryDelayResult attributes and immutability."""
    res = DeliveryDelayResult(delay_days=4, is_delayed=True)
    assert res.delay_days == 4
    assert res.is_delayed is True

    with pytest.raises(ValidationError):
        res.delay_days = 5


def test_tool_execution_result_success_and_failure() -> None:
    """Validate ToolExecutionResult for both success and error paths."""
    success_res = ToolExecutionResult(
        success=True,
        tool_name="get_order_details",
        data={"order_id": "CMD-10001"},
    )
    assert success_res.success is True
    assert success_res.data == {"order_id": "CMD-10001"}
    assert success_res.error_code is None

    fail_res = ToolExecutionResult(
        success=False,
        tool_name="get_order_details",
        error_code="ORDER_NOT_FOUND",
        error_message="Order 'CMD-99999' not found.",
    )
    assert fail_res.success is False
    assert fail_res.error_code == "ORDER_NOT_FOUND"
    assert fail_res.data is None


def test_tool_call_trace_validation() -> None:
    """Validate ToolCallTrace audit model constraints and duration validation."""
    now = datetime.now(timezone.utc)
    exec_res = ToolExecutionResult(
        success=True,
        tool_name="calculate_delivery_delay",
        data={"delay_days": 2},
    )
    trace = ToolCallTrace(
        tool_call_id="call-001",
        tool_name="calculate_delivery_delay",
        arguments={"order_id": "CMD-10001"},
        result=exec_res,
        timestamp=now,
        duration_ms=45.2,
    )
    assert trace.tool_call_id == "call-001"
    assert trace.duration_ms == 45.2
    assert trace.result.success is True

    # Negative duration must be rejected
    with pytest.raises(ValidationError):
        ToolCallTrace(
            tool_call_id="call-002",
            tool_name="calculate_delivery_delay",
            arguments={},
            result=exec_res,
            timestamp=now,
            duration_ms=-1.0,
        )

    # Immutability check
    with pytest.raises(ValidationError):
        trace.duration_ms = 50.0
