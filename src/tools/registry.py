"""Dynamic tool catalog, discovery, validation, and MCP specification exporter."""

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel

from clients.erp_client import MockERPClient
from core.exceptions import (
    BusinessRuleViolationError,
    SupportAgentBaseError,
    ToolExecutionError,
)
from models.tools import ToolExecutionResult
from observability.logger import get_logger
from persistence.cache import IdempotencyCache
from tools.base import ToolInterface
from tools.delay_calculator import DelayCalculatorTool
from tools.order_status import OrderStatusTool
from tools.refund_calculator import RefundCalculatorTool

logger = get_logger(__name__)

__all__ = ["ToolRegistry", "create_default_registry"]


class ToolRegistry:
    """Central catalog of tools accessible by the ReAct agent and MCP runtime."""

    def __init__(
        self,
        tools: Sequence[ToolInterface] | None = None,
        cache: IdempotencyCache | None = None,
    ) -> None:
        """Initialize tool catalog with optional pre-registered tools and cache."""
        self._tools: dict[str, ToolInterface] = {}
        self.cache = cache
        if tools:
            for tool in tools:
                self.register(tool)

    def register(self, tool: ToolInterface) -> None:
        """Register a tool in catalog after verifying protocol contract."""
        if not isinstance(tool, ToolInterface):
            raise BusinessRuleViolationError(
                f"Object of type '{type(tool).__name__}' does not conform to ToolInterface.",
                error_code="INVALID_TOOL_PROTOCOL",
            )
        if not tool.name or not isinstance(tool.name, str):
            raise BusinessRuleViolationError(
                "Tool name must be a non-empty string.",
                error_code="INVALID_TOOL_METADATA",
            )
        if not isinstance(tool.args_schema, type) or not issubclass(
            tool.args_schema, BaseModel
        ):
            raise BusinessRuleViolationError(
                f"Tool '{tool.name}' args_schema must be a subclass of BaseModel.",
                error_code="INVALID_TOOL_METADATA",
            )

        if tool.name in self._tools:
            logger.info("tool_overwritten_in_registry", tool_name=tool.name)

        self._tools[tool.name] = tool
        logger.debug("tool_registered", tool_name=tool.name)

    def unregister(self, name: str) -> None:
        """Remove a tool from the catalog."""
        if name not in self._tools:
            raise ToolExecutionError(
                f"Cannot unregister: tool '{name}' is not in the catalog.",
                tool_name=name,
            )
        del self._tools[name]
        logger.debug("tool_unregistered", tool_name=name)

    def get_tool(self, name: str) -> ToolInterface:
        """Retrieve registered tool by identifier."""
        if name not in self._tools:
            raise ToolExecutionError(
                f"Tool '{name}' is not registered.", tool_name=name
            )
        return self._tools[name]

    def has_tool(self, name: str) -> bool:
        """Check if tool identifier exists in registry."""
        return name in self._tools

    def list_tools(self) -> list[str]:
        """Return sorted list of registered tool names."""
        return sorted(self._tools.keys())

    def validate_tool_arguments(self, tool_name: str, **kwargs: Any) -> BaseModel:
        """Validate input arguments against a tool schema without executing it."""
        tool = self.get_tool(tool_name)
        return tool.args_schema.model_validate(kwargs)

    async def execute(
        self,
        tool_name: str,
        session_id: str | None = None,
        **kwargs: Any,
    ) -> ToolExecutionResult:
        """Safely execute registered tool by name with shielding and caching."""
        if not self.has_tool(tool_name):
            logger.warning("unregistered_tool_execution_attempt", tool_name=tool_name)
            return ToolExecutionResult(
                success=False,
                tool_name=tool_name,
                error_code="TOOL_NOT_FOUND",
                error_message=f"Tool '{tool_name}' is not registered in the catalog.",
            )

        cache_key: str | None = None
        if self.cache is not None and session_id:
            cache_key = self.cache.compute_key(session_id, tool_name, kwargs)
            cached = await self.cache.get_result_async(cache_key)
            if cached is not None:
                logger.info(
                    "tool_execution_cache_hit",
                    tool_name=tool_name,
                    session_id=session_id,
                    cache_key=cache_key,
                )
                return cached

        try:
            tool = self.get_tool(tool_name)
            result = await tool.execute(**kwargs)
            if self.cache is not None and cache_key and result.success:
                await self.cache.set_result_async(cache_key, result)
            return result
        except SupportAgentBaseError as domain_err:
            logger.warning(
                "registry_shielded_domain_error",
                tool_name=tool_name,
                error_code=domain_err.error_code,
            )
            return ToolExecutionResult(
                success=False,
                tool_name=tool_name,
                error_code=domain_err.error_code,
                error_message=domain_err.message,
            )
        except Exception as exc:
            logger.error(
                "registry_shielded_unhandled_fault",
                tool_name=tool_name,
                error=str(exc),
            )
            return ToolExecutionResult(
                success=False,
                tool_name=tool_name,
                error_code="UNHANDLED_TOOL_FAULT",
                error_message=f"Unhandled tool execution fault in '{tool_name}': {exc}",
            )

    def get_mcp_specs(self) -> list[dict[str, Any]]:
        """Export tool specifications formatted for MCP and LLM tool calling."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.args_schema.model_json_schema(),
            }
            for tool in self._tools.values()
        ]

    def get_mcp_spec(self, tool_name: str) -> dict[str, Any]:
        """Export single tool specification formatted for MCP."""
        tool = self.get_tool(tool_name)
        return {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.args_schema.model_json_schema(),
        }

    def get_openai_tools(self) -> list[dict[str, Any]]:
        """Export tool catalog formatted for OpenAI / LiteLLM function calling."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.args_schema.model_json_schema(),
                },
            }
            for tool in self._tools.values()
        ]

    def __contains__(self, name: str) -> bool:
        """Check if tool is in registry using 'in' operator."""
        return self.has_tool(name)

    def __len__(self) -> int:
        """Return total count of registered tools."""
        return len(self._tools)


def create_default_registry(
    erp_client: MockERPClient | None = None,
    cache: IdempotencyCache | None = None,
) -> ToolRegistry:
    """Factory creating a ToolRegistry pre-populated with standard domain tools."""
    registry = ToolRegistry(cache=cache)
    registry.register(OrderStatusTool(erp_client=erp_client))
    registry.register(RefundCalculatorTool())
    registry.register(DelayCalculatorTool())
    return registry
