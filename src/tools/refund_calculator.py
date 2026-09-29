"""Statutory refund eligibility calculator tool adapter."""

from datetime import datetime
from typing import Any

from pydantic import Field

from domain.business_rules import calculate_statutory_withdrawal
from models.base import BaseDTO
from tools.base import BaseTool


class RefundCalculatorArgs(BaseDTO):
    """Arguments for calculate_refund_eligibility tool."""

    delivery_date: datetime | None = None
    request_date: datetime
    item_prices_cents: list[int] = Field(default_factory=list)
    shipping_fee_cents: int = Field(default=0, ge=0)
    is_express: bool = False
    delay_days: int = Field(default=0, ge=0)


class RefundCalculatorTool(BaseTool):
    """Evaluates 14-day legal return window and refundable amounts."""

    name: str = "calculate_refund_eligibility"
    description: str = (
        "Calculate return eligibility under the statutory 14-day cooling-off rule. "
        "Returns refundable item total, delay vouchers, and reason code."
    )
    args_schema: type[RefundCalculatorArgs] = RefundCalculatorArgs

    async def _run(self, **kwargs: Any) -> dict[str, Any]:
        """Execute refund calculation with deterministic business logic."""
        result = calculate_statutory_withdrawal(
            delivery_date=kwargs.get("delivery_date"),
            request_date=kwargs["request_date"],
            item_prices_cents=kwargs.get("item_prices_cents", []),
            shipping_fee_cents=kwargs.get("shipping_fee_cents", 0),
            is_express=kwargs.get("is_express", False),
            delay_days=kwargs.get("delay_days", 0),
        )
        return result.model_dump()
