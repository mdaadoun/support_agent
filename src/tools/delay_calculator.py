"""Delivery delay and compensation voucher tool adapter."""

from datetime import datetime
from typing import Any

from domain.business_rules import (
    calculate_express_compensation,
    calculate_shipping_delay,
)
from models.base import BaseDTO
from tools.base import BaseTool


class DelayCalculatorArgs(BaseDTO):
    """Arguments for calculate_delivery_delay tool."""

    estimated_delivery_date: datetime
    reference_date: datetime
    is_express: bool = False
    shipping_fee_cents: int = 0


class DelayCalculatorTool(BaseTool):
    """Calculates shipping delay and express delivery compensation vouchers."""

    name: str = "calculate_delivery_delay"
    description: str = (
        "Compute delivery delay in calendar days and evaluate express shipping "
        "voucher compensation if delayed beyond 5 days."
    )
    args_schema: type[DelayCalculatorArgs] = DelayCalculatorArgs

    async def _run(self, **kwargs: Any) -> dict[str, Any]:
        """Execute shipping delay evaluation."""
        delay_res = calculate_shipping_delay(
            estimated_delivery_date=kwargs["estimated_delivery_date"],
            reference_date=kwargs["reference_date"],
        )
        voucher_cents = calculate_express_compensation(
            delay_days=delay_res.delay_days,
            is_express=kwargs.get("is_express", False),
            shipping_fee_cents=kwargs.get("shipping_fee_cents", 0),
        )
        data = delay_res.model_dump()
        data["voucher_compensation_cents"] = voucher_cents
        return data
