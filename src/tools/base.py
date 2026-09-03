"""Tool interface and MCP protocol definitions for 8_support_agent."""

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

from models.tools import ToolExecutionResult


@runtime_checkable
class ToolInterface(Protocol):
    """Protocol for tools compatible with ReAct loop and MCP runtime."""

    name: str
    description: str
    args_schema: type[BaseModel]

    async def execute(self, **kwargs: Any) -> ToolExecutionResult:
        """Execute the tool operation safely with complete exception shielding."""
        ...
