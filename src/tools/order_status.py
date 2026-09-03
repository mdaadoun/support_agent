"""Order status inspection tool adapter for 8_support_agent."""

from typing import Any

from pydantic import BaseModel, EmailStr

from models.tools import ToolExecutionResult
from tools.base import ToolInterface


class OrderStatusArgs(BaseModel):
    """Input parameters for get_order_details tool."""

    order_id: str
    customer_email: EmailStr


class OrderStatusTool(ToolInterface):
    """Tool retrieving order metadata with customer verification."""

    name: str = "get_order_details"
    description: str = (
        "Retrieve order details, delivery dates, carrier info, and item totals. "
        "Requires order_id and verified customer_email."
    )
    args_schema: type[OrderStatusArgs] = OrderStatusArgs

    async def execute(self, **kwargs: Any) -> ToolExecutionResult:
        """Execute order retrieval with error shielding."""
        try:
            validated = OrderStatusArgs.model_validate(kwargs)
            # Scaffold placeholder: logic will connect erp_client and access_control in Phase 5
            return ToolExecutionResult(
                success=True,
                tool_name=self.name,
                data={"order_id": validated.order_id},
            )
        except Exception as exc:
            return ToolExecutionResult(
                success=False,
                tool_name=self.name,
                error_code="INVALID_ARGUMENTS",
                error_message=str(exc),
            )
