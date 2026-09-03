"""Statutory refund eligibility calculator tool adapter."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from domain.business_rules import calculate_statutory_withdrawal
from models.tools import ToolExecutionResult
from tools.base import ToolInterface


class RefundCalculatorArgs(BaseModel):
    """Arguments for calculate_refund_eligibility tool."""

    delivery_date: datetime
    request_date: datetime
    item_prices_cents: list[int] = Field(default_factory=list)
    shipping_fee_cents: int = Field(default=0, ge=0)


class RefundCalculatorTool(ToolInterface):
    """Evaluates 14-day legal return window and refundable amounts."""

    name: str = "calculate_refund_eligibility"
    description: str = (
        "Calculate return eligibility under the statutory 14-day cooling-off rule. "
        "Returns refundable item total and reason code."
    )
    args_schema: type[RefundCalculatorArgs] = RefundCalculatorArgs

    async def execute(self, **kwargs: Any) -> ToolExecutionResult:
        """Execute refund calculation with deterministic business logic."""
        try:
            args = RefundCalculatorArgs.model_validate(kwargs)
            result = calculate_statutory_withdrawal(
                delivery_date=args.delivery_date,
                request_date=args.request_date,
                item_prices_cents=args.item_prices_cents,
                shipping_fee_cents=args.shipping_fee_cents,
            )
            return ToolExecutionResult(
                success=True,
                tool_name=self.name,
                data=result.model_dump(),
            )
        except Exception as exc:
            return ToolExecutionResult(
                success=False,
                tool_name=self.name,
                error_code="CALCULATION_ERROR",
                error_message=str(exc),
            )
