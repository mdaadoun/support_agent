"""Order status inspection tool adapter for 8_support_agent."""

from typing import Any

from pydantic import EmailStr

from clients.erp_client import MockERPClient
from models.base import BaseDTO
from models.enums import OrderStatusEnum
from models.tools import OrderDetailsResult
from security.access_control import AccessControlGuard
from tools.base import BaseTool


class OrderStatusArgs(BaseDTO):
    """Input parameters for get_order_details tool."""

    order_id: str
    customer_email: EmailStr


class OrderStatusTool(BaseTool):
    """Tool retrieving order metadata with customer verification."""

    name: str = "get_order_details"
    description: str = (
        "Retrieve order details, delivery dates, carrier info, and item totals. "
        "Requires order_id and verified customer_email."
    )
    args_schema: type[OrderStatusArgs] = OrderStatusArgs

    def __init__(self, erp_client: MockERPClient | None = None) -> None:
        """Initialize tool with optional ERP client injection."""
        self.erp_client = erp_client or MockERPClient()

    async def _run(self, **kwargs: Any) -> OrderDetailsResult:
        """Execute order retrieval logic with cross-authorization verification.

        Args:
            **kwargs: Validated arguments including order_id and customer_email.

        Returns:
            OrderDetailsResult with complete order lifecycle metadata.

        Raises:
            OrderNotFoundError: If order does not exist in ERP.
            SecurityAccessError: If sender email fails PII cross-authorization.
            CircuitBreakerError: If upstream ERP service is unavailable.
        """
        order_id: str = kwargs["order_id"]
        customer_email: str = kwargs["customer_email"]

        # Fetch order asynchronously from ERP client with retry handling
        order_record = await self.erp_client.get_order_by_id_async(order_id)

        # Cross-authorization PII check (fails closed on mismatch)
        AccessControlGuard.verify_order_record_access(
            sender_email=customer_email,
            order_record=order_record,
        )

        return OrderDetailsResult(
            order_id=order_record["order_id"],
            status=OrderStatusEnum(order_record["status"]),
            carrier=order_record["carrier"],
            tracking_number=order_record.get("tracking_number"),
            ordered_at=order_record["ordered_at"],
            shipped_at=order_record.get("shipped_at"),
            estimated_delivery=order_record["estimated_delivery"],
            actual_delivery=order_record.get("actual_delivery"),
            items_total_ttc_cents=order_record["items_total_ttc_cents"],
            shipping_fee_ttc_cents=order_record["shipping_fee_ttc_cents"],
            is_express=order_record["is_express"],
        )
