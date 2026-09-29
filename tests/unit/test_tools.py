"""Unit tests verifying concrete tool adapters (OrderStatus, Refund, Delay)."""

from datetime import datetime, timezone

import pytest

from clients.erp_client import MockERPClient
from models.enums import OrderStatusEnum, RefundReasonCode
from tools.delay_calculator import DelayCalculatorTool
from tools.order_status import OrderStatusTool
from tools.refund_calculator import RefundCalculatorTool


@pytest.mark.asyncio
async def test_order_status_tool_nominal_delivered() -> None:
    """Validate OrderStatusTool successfully returns delivered order details."""
    tool = OrderStatusTool()
    res = await tool.execute(order_id="CMD-10001", customer_email="alice@example.com")
    assert res.success is True
    assert res.tool_name == "get_order_details"
    assert res.data is not None
    assert res.data["order_id"] == "CMD-10001"
    assert res.data["status"] == OrderStatusEnum.DELIVERED.value
    assert res.data["carrier"] == "Colissimo"
    assert res.data["items_total_ttc_cents"] == 8990
    assert res.data["shipping_fee_ttc_cents"] == 490
    assert res.data["is_express"] is False


@pytest.mark.asyncio
async def test_order_status_tool_nominal_delayed_express() -> None:
    """Validate OrderStatusTool correctly inspects delayed express order."""
    tool = OrderStatusTool()
    res = await tool.execute(order_id="CMD-10002", customer_email="bob@example.com")
    assert res.success is True
    assert res.data is not None
    assert res.data["status"] == OrderStatusEnum.DELAYED.value
    assert res.data["is_express"] is True
    assert res.data["shipping_fee_ttc_cents"] == 1200


@pytest.mark.asyncio
async def test_order_status_tool_pii_mismatch() -> None:
    """Validate OrderStatusTool shields PII mismatch with SECURITY_UNAUTHORIZED_ACCESS."""
    tool = OrderStatusTool()
    res = await tool.execute(
        order_id="CMD-10001", customer_email="mallory@attacker.com"
    )
    assert res.success is False
    assert res.error_code == "SECURITY_UNAUTHORIZED_ACCESS"
    assert res.data is None
    assert "alice@example.com" not in (res.error_message or "")


@pytest.mark.asyncio
async def test_order_status_tool_order_not_found() -> None:
    """Validate OrderStatusTool shields missing order with ORDER_NOT_FOUND."""
    tool = OrderStatusTool()
    res = await tool.execute(order_id="CMD-99999", customer_email="alice@example.com")
    assert res.success is False
    assert res.error_code == "ORDER_NOT_FOUND"
    assert "CMD-99999" in (res.error_message or "")


@pytest.mark.asyncio
async def test_order_status_tool_circuit_breaker() -> None:
    """Validate OrderStatusTool shields upstream ERP network failure."""
    erp_client = MockERPClient()
    erp_client.simulate_transient_network_failure(failure_count=3)
    tool = OrderStatusTool(erp_client=erp_client)

    res = await tool.execute(order_id="CMD-10001", customer_email="alice@example.com")
    assert res.success is False
    assert res.error_code == "CIRCUIT_BREAKER_TRIPPED"


@pytest.mark.asyncio
async def test_order_status_tool_invalid_arguments() -> None:
    """Validate OrderStatusTool shields schema validation errors."""
    tool = OrderStatusTool()
    res_bad_email = await tool.execute(
        order_id="CMD-10001", customer_email="not-an-email"
    )
    assert res_bad_email.success is False
    assert res_bad_email.error_code == "INVALID_ARGUMENTS"

    res_extra = await tool.execute(
        order_id="CMD-10001", customer_email="alice@example.com", extra="bad"
    )
    assert res_extra.success is False
    assert res_extra.error_code == "INVALID_ARGUMENTS"


@pytest.mark.asyncio
async def test_refund_calculator_eligible_return() -> None:
    """Validate RefundCalculatorTool for order delivered within 14 days."""
    tool = RefundCalculatorTool()
    now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    delivered = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)

    res = await tool.execute(
        delivery_date=delivered,
        request_date=now,
        item_prices_cents=[3500, 1500],
        shipping_fee_cents=500,
    )
    assert res.success is True
    assert res.data is not None
    assert res.data["is_eligible_for_return"] is True
    assert res.data["days_elapsed"] == 10
    assert res.data["refundable_items_total_cents"] == 5000
    assert res.data["reason_code"] == RefundReasonCode.WITHIN_LEGAL_TIMEFRAME.value


@pytest.mark.asyncio
async def test_refund_calculator_expired_return() -> None:
    """Validate RefundCalculatorTool refusal when 14-day window is exceeded."""
    tool = RefundCalculatorTool()
    now = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
    delivered = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)

    res = await tool.execute(
        delivery_date=delivered,
        request_date=now,
        item_prices_cents=[5000],
    )
    assert res.success is True
    assert res.data is not None
    assert res.data["is_eligible_for_return"] is False
    assert res.data["days_elapsed"] == 24
    assert res.data["refundable_items_total_cents"] == 0
    assert res.data["reason_code"] == RefundReasonCode.TIMEFRAME_EXCEEDED.value


@pytest.mark.asyncio
async def test_refund_calculator_not_delivered_yet() -> None:
    """Validate RefundCalculatorTool when delivery_date is None."""
    tool = RefundCalculatorTool()
    now = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)

    res = await tool.execute(
        delivery_date=None,
        request_date=now,
        item_prices_cents=[5000],
    )
    assert res.success is True
    assert res.data is not None
    assert res.data["is_eligible_for_return"] is False
    assert res.data["reason_code"] == RefundReasonCode.NOT_DELIVERED_YET.value


@pytest.mark.asyncio
async def test_refund_calculator_express_voucher_compensation() -> None:
    """Validate RefundCalculatorTool includes express delay voucher."""
    tool = RefundCalculatorTool()
    now = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
    delivered = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)

    res = await tool.execute(
        delivery_date=delivered,
        request_date=now,
        item_prices_cents=[5000],
        shipping_fee_cents=800,
        is_express=True,
        delay_days=6,
    )
    assert res.success is True
    assert res.data is not None
    assert res.data["delay_compensation_voucher_cents"] == 800
    assert res.data["reason_code"] == RefundReasonCode.EXPRESS_DELAY_COMPENSATED.value


@pytest.mark.asyncio
async def test_refund_calculator_negative_monetary_value() -> None:
    """Validate RefundCalculatorTool shields negative values."""
    tool = RefundCalculatorTool()
    now = datetime(2026, 9, 25, tzinfo=timezone.utc)

    res = await tool.execute(
        delivery_date=now,
        request_date=now,
        shipping_fee_cents=-100,
    )
    assert res.success is False
    assert res.error_code == "INVALID_ARGUMENTS"


@pytest.mark.asyncio
async def test_delay_calculator_delayed_with_voucher() -> None:
    """Validate DelayCalculatorTool computes delay days and express voucher."""
    tool = DelayCalculatorTool()
    est = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    ref = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)

    res = await tool.execute(
        estimated_delivery_date=est,
        reference_date=ref,
        is_express=True,
        shipping_fee_cents=1200,
    )
    assert res.success is True
    assert res.data is not None
    assert res.data["delay_days"] == 7
    assert res.data["is_delayed"] is True
    assert res.data["voucher_compensation_cents"] == 1200


@pytest.mark.asyncio
async def test_delay_calculator_on_time_delivery() -> None:
    """Validate DelayCalculatorTool computes 0 delay days when on time."""
    tool = DelayCalculatorTool()
    est = datetime(2026, 8, 15, tzinfo=timezone.utc)
    ref = datetime(2026, 8, 14, tzinfo=timezone.utc)

    res = await tool.execute(
        estimated_delivery_date=est,
        reference_date=ref,
        is_express=True,
        shipping_fee_cents=1000,
    )
    assert res.success is True
    assert res.data is not None
    assert res.data["delay_days"] == 0
    assert res.data["is_delayed"] is False
    assert res.data["voucher_compensation_cents"] == 0


@pytest.mark.asyncio
async def test_delay_calculator_standard_shipping_no_voucher() -> None:
    """Validate non-express shipments do not receive compensation vouchers."""
    tool = DelayCalculatorTool()
    est = datetime(2026, 8, 1, tzinfo=timezone.utc)
    ref = datetime(2026, 8, 10, tzinfo=timezone.utc)

    res = await tool.execute(
        estimated_delivery_date=est,
        reference_date=ref,
        is_express=False,
        shipping_fee_cents=500,
    )
    assert res.success is True
    assert res.data is not None
    assert res.data["delay_days"] == 9
    assert res.data["voucher_compensation_cents"] == 0
