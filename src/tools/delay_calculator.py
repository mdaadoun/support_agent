"""Delivery delay and compensation voucher tool adapter."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from domain.business_rules import (
    calculate_express_compensation,
    calculate_shipping_delay,
)
from models.tools import ToolExecutionResult
from tools.base import ToolInterface


class DelayCalculatorArgs(BaseModel):
    """Arguments for calculate_delivery_delay tool."""

    estimated_delivery_date: datetime
    reference_date: datetime
    is_express: bool = False
    shipping_fee_cents: int = 0


class DelayCalculatorTool(ToolInterface):
    """Calculates shipping delay and express delivery compensation vouchers."""

    name: str = "calculate_delivery_delay"
    description: str = (
        "Compute delivery delay in calendar days and evaluate express shipping "
        "voucher compensation if delayed beyond 5 days."
    )
    args_schema: type[DelayCalculatorArgs] = DelayCalculatorArgs

    async def execute(self, **kwargs: Any) -> ToolExecutionResult:
        """Execute shipping delay evaluation."""
        try:
            args = DelayCalculatorArgs.model_validate(kwargs)
            delay_res = calculate_shipping_delay(
                estimated_delivery_date=args.estimated_delivery_date,
                reference_date=args.reference_date,
            )
            voucher_cents = calculate_express_compensation(
                delay_days=delay_res.delay_days,
                is_express=args.is_express,
                shipping_fee_cents=args.shipping_fee_cents,
            )
            data = delay_res.model_dump()
            data["voucher_compensation_cents"] = voucher_cents

            return ToolExecutionResult(
                success=True,
                tool_name=self.name,
                data=data,
            )
        except Exception as exc:
            return ToolExecutionResult(
                success=False,
                tool_name=self.name,
                error_code="CALCULATION_ERROR",
                error_message=str(exc),
            )
