"""Tool protocols, adapters, and registration catalogue."""

from tools.base import (
    BaseTool,
    ToolInterface,
    execute_shielded,
    shield_tool_execution,
)
from tools.delay_calculator import DelayCalculatorTool
from tools.order_status import OrderStatusTool
from tools.refund_calculator import RefundCalculatorTool
from tools.registry import ToolRegistry, create_default_registry

__all__ = [
    "BaseTool",
    "DelayCalculatorTool",
    "OrderStatusTool",
    "RefundCalculatorTool",
    "ToolInterface",
    "ToolRegistry",
    "create_default_registry",
    "execute_shielded",
    "shield_tool_execution",
]
