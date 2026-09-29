"""Unit tests verifying ToolRegistry catalog, validation, and MCP specification export."""

from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import Field, ValidationError

from clients.erp_client import MockERPClient
from core.exceptions import BusinessRuleViolationError, ToolExecutionError
from models.base import BaseDTO
from models.tools import ToolExecutionResult
from tools.base import BaseTool
from tools.order_status import OrderStatusTool
from tools.registry import ToolRegistry, create_default_registry


class AlphaArgs(BaseDTO):
    """Schema for test tool Alpha."""

    message: str
    repeat: int = Field(default=1, ge=1)


class AlphaTool(BaseTool):
    """Test tool implementation Alpha."""

    name: str = "alpha_tool"
    description: str = "Repeats a message a given number of times."
    args_schema: type[AlphaArgs] = AlphaArgs

    async def _run(self, **kwargs: Any) -> dict[str, Any]:
        return {"result": kwargs["message"] * kwargs["repeat"]}


class FaultyTool(BaseTool):
    """Tool raising unexpected fault during execution."""

    name: str = "faulty_tool"
    description: str = "Always crashes unexpectedly."
    args_schema: type[AlphaArgs] = AlphaArgs

    async def _run(self, **kwargs: Any) -> dict[str, Any]:
        return {}

    async def execute(self, **kwargs: Any) -> ToolExecutionResult:
        raise RuntimeError("Unexpected internal crash inside tool")


def test_registry_registration_and_discovery() -> None:
    """Validate dynamic tool registration, introspection, and retrieval."""
    registry = ToolRegistry()
    assert len(registry) == 0

    tool = AlphaTool()
    registry.register(tool)

    assert len(registry) == 1
    assert "alpha_tool" in registry
    assert registry.has_tool("alpha_tool")
    assert registry.list_tools() == ["alpha_tool"]
    assert registry.get_tool("alpha_tool") is tool

    # Overwrite tool with same name
    tool_v2 = AlphaTool()
    registry.register(tool_v2)
    assert len(registry) == 1
    assert registry.get_tool("alpha_tool") is tool_v2


def test_registry_unregister_and_missing_lookups() -> None:
    """Validate tool removal and error shielding on non-existent tool lookups."""
    registry = ToolRegistry()
    registry.register(AlphaTool())

    registry.unregister("alpha_tool")
    assert "alpha_tool" not in registry
    assert len(registry) == 0

    with pytest.raises(ToolExecutionError, match="not registered"):
        registry.get_tool("alpha_tool")

    with pytest.raises(ToolExecutionError, match="Cannot unregister"):
        registry.unregister("alpha_tool")


def test_registry_contract_validation_on_registration() -> None:
    """Validate that invalid tools violating ToolInterface are rejected."""
    registry = ToolRegistry()

    class NotATool:
        name = "invalid"

    with pytest.raises(BusinessRuleViolationError) as exc_proto:
        registry.register(NotATool())  # type: ignore[arg-type]
    assert exc_proto.value.error_code == "INVALID_TOOL_PROTOCOL"

    class BadNameTool:
        name = ""
        description = "desc"
        args_schema = AlphaArgs

        async def execute(self, **kwargs: Any) -> ToolExecutionResult:
            return ToolExecutionResult(success=True, tool_name="")

    with pytest.raises(BusinessRuleViolationError) as exc_meta:
        registry.register(BadNameTool())  # type: ignore[arg-type]
    assert exc_meta.value.error_code == "INVALID_TOOL_METADATA"


def test_registry_validate_tool_arguments() -> None:
    """Validate pre-flight argument validation against tool schemas."""
    registry = ToolRegistry([AlphaTool()])

    validated = registry.validate_tool_arguments(
        "alpha_tool", message="hello", repeat=3
    )
    assert isinstance(validated, AlphaArgs)
    assert validated.message == "hello"
    assert validated.repeat == 3

    with pytest.raises(ValidationError):
        registry.validate_tool_arguments("alpha_tool", message="hello", repeat=-1)

    with pytest.raises(ToolExecutionError, match="not registered"):
        registry.validate_tool_arguments("unknown", message="hello")


@pytest.mark.asyncio
async def test_registry_execute_nominal_and_error_paths() -> None:
    """Validate execution via registry including unknown tools and unexpected crashes."""
    registry = ToolRegistry([AlphaTool(), FaultyTool()])

    # Nominal execution
    res = await registry.execute("alpha_tool", message="hi", repeat=2)
    assert res.success is True
    assert res.tool_name == "alpha_tool"
    assert res.data == {"result": "hihi"}

    # Unregistered tool execution returns shielded error
    missing_res = await registry.execute("unknown_tool", query="data")
    assert missing_res.success is False
    assert missing_res.error_code == "TOOL_NOT_FOUND"
    assert "unknown_tool" in (missing_res.error_message or "")

    # Faulty tool raising raw Exception is shielded
    fault_res = await registry.execute("faulty_tool", message="crash")
    assert fault_res.success is False
    assert fault_res.error_code == "UNHANDLED_TOOL_FAULT"
    assert "Unexpected internal crash" in (fault_res.error_message or "")


def test_registry_mcp_and_openai_spec_exporters() -> None:
    """Validate MCP and OpenAI tool specification generation."""
    registry = ToolRegistry([AlphaTool()])

    mcp_specs = registry.get_mcp_specs()
    assert len(mcp_specs) == 1
    assert mcp_specs[0]["name"] == "alpha_tool"
    assert "Repeats a message" in mcp_specs[0]["description"]
    assert "properties" in mcp_specs[0]["parameters"]
    assert "message" in mcp_specs[0]["parameters"]["properties"]

    single_spec = registry.get_mcp_spec("alpha_tool")
    assert single_spec == mcp_specs[0]

    with pytest.raises(ToolExecutionError):
        registry.get_mcp_spec("unknown_tool")

    openai_tools = registry.get_openai_tools()
    assert len(openai_tools) == 1
    assert openai_tools[0]["type"] == "function"
    assert openai_tools[0]["function"]["name"] == "alpha_tool"
    assert openai_tools[0]["function"]["parameters"] == mcp_specs[0]["parameters"]


@pytest.mark.asyncio
async def test_create_default_registry_factory() -> None:
    """Validate create_default_registry factory registers all core domain tools."""
    mock_erp = MockERPClient()
    registry = create_default_registry(erp_client=mock_erp)

    expected_tools = [
        "calculate_delivery_delay",
        "calculate_refund_eligibility",
        "get_order_details",
    ]
    assert registry.list_tools() == expected_tools

    order_tool = registry.get_tool("get_order_details")
    assert isinstance(order_tool, OrderStatusTool)
    assert order_tool.erp_client is mock_erp

    # Execute all tools through registry
    res_order = await registry.execute(
        "get_order_details",
        order_id="CMD-10001",
        customer_email="alice@example.com",
    )
    assert res_order.success is True

    now = datetime(2026, 9, 20, tzinfo=timezone.utc)
    res_delay = await registry.execute(
        "calculate_delivery_delay",
        estimated_delivery_date=now,
        reference_date=now,
    )
    assert res_delay.success is True

    res_refund = await registry.execute(
        "calculate_refund_eligibility",
        delivery_date=now,
        request_date=now,
    )
    assert res_refund.success is True

    # Assert 3 MCP specs produced
    specs = registry.get_mcp_specs()
    assert len(specs) == 3
    tool_names = {s["name"] for s in specs}
    assert tool_names == set(expected_tools)
