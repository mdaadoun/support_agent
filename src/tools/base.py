"""Tool interface, abstract base class, and execution shielding wrapper."""

import inspect
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ValidationError

from core.exceptions import SupportAgentBaseError
from models.tools import ToolExecutionResult
from observability.logger import get_logger

logger = get_logger(__name__)

__all__ = [
    "BaseTool",
    "ToolInterface",
    "execute_shielded",
    "shield_tool_execution",
]


@runtime_checkable
class ToolInterface(Protocol):
    """Protocol for tools compatible with ReAct loop and MCP runtime."""

    name: str
    description: str
    args_schema: type[BaseModel]

    async def execute(self, **kwargs: Any) -> ToolExecutionResult:
        """Execute the tool operation safely with complete exception shielding."""
        ...


async def execute_shielded(
    func: Callable[..., Any],
    tool_name: str,
    args_schema: type[BaseModel] | None = None,
    **kwargs: Any,
) -> ToolExecutionResult:
    """Execute tool callable with argument validation and absolute exception shielding.

    Args:
        func: Coroutine or callable implementing the tool logic.
        tool_name: Registered name of the tool for auditing.
        args_schema: Optional Pydantic model for schema validation.
        **kwargs: Raw input arguments supplied by LLM or caller.

    Returns:
        ToolExecutionResult capturing outcome, payload, or shielded error.
    """
    try:
        call_kwargs: dict[str, Any]
        if args_schema is not None:
            validated = args_schema.model_validate(kwargs)
            call_kwargs = validated.model_dump()
        else:
            call_kwargs = kwargs

        res = func(**call_kwargs)
        if inspect.isawaitable(res):
            raw_result = await res
        else:
            raw_result = res

        if isinstance(raw_result, ToolExecutionResult):
            return raw_result
        if isinstance(raw_result, BaseModel):
            return ToolExecutionResult(
                success=True,
                tool_name=tool_name,
                data=raw_result.model_dump(mode="json"),
            )
        if isinstance(raw_result, dict):
            return ToolExecutionResult(
                success=True,
                tool_name=tool_name,
                data=raw_result,
            )
        if raw_result is None:
            return ToolExecutionResult(
                success=True,
                tool_name=tool_name,
                data=None,
            )
        return ToolExecutionResult(
            success=True,
            tool_name=tool_name,
            data={"result": raw_result},
        )
    except ValidationError as val_err:
        logger.warning(
            "tool_validation_error",
            tool_name=tool_name,
            error=str(val_err),
        )
        return ToolExecutionResult(
            success=False,
            tool_name=tool_name,
            error_code="INVALID_ARGUMENTS",
            error_message=str(val_err),
        )
    except SupportAgentBaseError as domain_err:
        logger.warning(
            "tool_domain_error",
            tool_name=tool_name,
            error_code=domain_err.error_code,
            error=domain_err.message,
        )
        return ToolExecutionResult(
            success=False,
            tool_name=tool_name,
            error_code=domain_err.error_code,
            error_message=domain_err.message,
        )
    except Exception as exc:
        logger.error(
            "tool_unhandled_exception",
            tool_name=tool_name,
            error=str(exc),
        )
        return ToolExecutionResult(
            success=False,
            tool_name=tool_name,
            error_code="TOOL_EXECUTION_ERROR",
            error_message=f"Unhandled tool failure: {exc}",
        )


def shield_tool_execution(
    tool_name: str | None = None,
    args_schema: type[BaseModel] | None = None,
) -> Callable[
    [Callable[..., Any]], Callable[..., Coroutine[Any, Any, ToolExecutionResult]]
]:
    """Decorator shielding tool execution and returning structured ToolExecutionResult."""

    def decorator(
        func: Callable[..., Any],
    ) -> Callable[..., Coroutine[Any, Any, ToolExecutionResult]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> ToolExecutionResult:
            effective_name = tool_name
            effective_schema = args_schema

            bound_args: tuple[Any, ...] = ()
            if args:
                first = args[0]
                if effective_name is None and hasattr(first, "name"):
                    effective_name = str(first.name)
                if effective_schema is None and hasattr(first, "args_schema"):
                    effective_schema = first.args_schema
                bound_args = args

            if effective_name is None:
                effective_name = getattr(func, "__name__", "anonymous_tool")

            def _invoker(**kw: Any) -> Any:
                if bound_args:
                    return func(*bound_args, **kw)
                return func(**kw)

            return await execute_shielded(
                func=_invoker,
                tool_name=effective_name,
                args_schema=effective_schema,
                **kwargs,
            )

        return wrapper

    return decorator


class BaseTool(ABC, ToolInterface):
    """Abstract base class for support agent tools providing argument validation and exception shielding."""

    name: str
    description: str
    args_schema: type[BaseModel]

    def validate_arguments(self, **kwargs: Any) -> BaseModel:
        """Validate input parameters against the tool's argument schema."""
        return self.args_schema.model_validate(kwargs)

    def get_mcp_spec(self) -> dict[str, Any]:
        """Return MCP-compliant tool specification dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.args_schema.model_json_schema(),
        }

    @abstractmethod
    async def _run(self, **kwargs: Any) -> Any:
        """Internal execution method implemented by concrete tools."""
        ...

    async def execute(self, **kwargs: Any) -> ToolExecutionResult:
        """Execute tool logic safely with complete argument validation and exception shielding."""
        return await execute_shielded(
            func=self._run,
            tool_name=self.name,
            args_schema=self.args_schema,
            **kwargs,
        )
