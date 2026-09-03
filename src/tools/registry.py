"""Dynamic tool catalog, discovery, and MCP schema provider."""

from typing import Any

from core.exceptions import ToolExecutionError
from models.tools import ToolExecutionResult
from tools.base import ToolInterface


class ToolRegistry:
    """Central catalog of tools accessible by the ReAct agent."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolInterface] = {}

    def register(self, tool: ToolInterface) -> None:
        """Register a tool instance in the catalog."""
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> ToolInterface:
        """Retrieve tool by identifier.

        Raises:
            ToolExecutionError: If tool is not registered.
        """
        if name not in self._tools:
            raise ToolExecutionError(
                f"Tool '{name}' is not registered.", tool_name=name
            )
        return self._tools[name]

    def list_tools(self) -> list[str]:
        """Return list of registered tool names."""
        return list(self._tools.keys())

    async def execute(self, tool_name: str, **kwargs: Any) -> ToolExecutionResult:
        """Safely execute registered tool by name with exception shielding."""
        try:
            tool = self.get_tool(tool_name)
            return await tool.execute(**kwargs)
        except Exception as exc:
            return ToolExecutionResult(
                success=False,
                tool_name=tool_name,
                error_code="UNHANDLED_TOOL_FAULT",
                error_message=str(exc),
            )

    def get_mcp_specs(self) -> list[dict[str, Any]]:
        """Export tool specifications formatted for LLM function/tool calling."""
        specs: list[dict[str, Any]] = []
        for tool in self._tools.values():
            specs.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.args_schema.model_json_schema(),
                }
            )
        return specs
