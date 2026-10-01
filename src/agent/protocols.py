"""Protocols decoupling agent reasoning loops from concrete infrastructure dependencies."""

from typing import Any, Protocol, runtime_checkable

from models.llm import LLMResponse
from models.tools import ToolExecutionResult

__all__ = ["LLMClientProtocol", "ToolRegistryProtocol"]


@runtime_checkable
class LLMClientProtocol(Protocol):
    """Structural contract for LLM inference client required by ReAct loops."""

    async def generate_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> LLMResponse: ...

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[Any],
        messages: list[dict[str, Any]] | None = None,
    ) -> Any: ...


@runtime_checkable
class ToolRegistryProtocol(Protocol):
    """Structural contract for tool discovery and execution required by ReAct loops."""

    def get_openai_tools(self) -> list[dict[str, Any]]: ...

    async def execute(
        self,
        tool_name: str,
        session_id: str | None = None,
        **kwargs: Any,
    ) -> ToolExecutionResult: ...
