"""Tool execution argument and result schemas."""

from datetime import datetime
from typing import Any

from pydantic import Field

from models.base import BaseDTO
from models.enums import OrderStatusEnum, RefundReasonCode


class OrderDetailsResult(BaseDTO):
    """Normalized order information returned by order query tool."""

    order_id: str
    status: OrderStatusEnum
    carrier: str
    tracking_number: str | None = None
    ordered_at: datetime
    shipped_at: datetime | None = None
    estimated_delivery: datetime
    actual_delivery: datetime | None = None
    items_total_ttc_cents: int = Field(ge=0)
    shipping_fee_ttc_cents: int = Field(ge=0)
    is_express: bool


class RefundEligibilityResult(BaseDTO):
    """Deterministic outcome of refund/statutory return evaluation."""

    is_eligible_for_return: bool
    days_elapsed: int = Field(ge=0)
    refundable_items_total_cents: int = Field(ge=0)
    delay_compensation_voucher_cents: int = Field(ge=0)
    reason_code: RefundReasonCode


class DeliveryDelayResult(BaseDTO):
    """Calculated delivery delay information."""

    delay_days: int
    is_delayed: bool


class ToolExecutionResult(BaseDTO):
    """Shielded result container for all tool executions."""

    success: bool
    tool_name: str
    data: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None


class ToolCallTrace(BaseDTO):
    """Audit log entry capturing individual tool invocation details."""

    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]
    result: ToolExecutionResult
    timestamp: datetime
    duration_ms: float
