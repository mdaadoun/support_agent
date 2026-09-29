"""Unit tests verifying ToolInterface, BaseTool abstract base, and execution shielding."""

from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import Field

from core.exceptions import (
    BusinessRuleViolationError,
    OrderNotFoundError,
    SecurityAccessError,
)
from models.base import BaseDTO
from models.tools import ToolExecutionResult
from tools.base import (
    BaseTool,
    ToolInterface,
    shield_tool_execution,
)
from tools.delay_calculator import DelayCalculatorTool
from tools.order_status import OrderStatusTool
from tools.refund_calculator import RefundCalculatorTool


class SampleArgs(BaseDTO):
    """Test argument schema."""

    query: str
    count: int = Field(default=1, ge=1)


class DummyTool(BaseTool):
    """Concrete tool implementation for testing."""

    name: str = "dummy_tool"
    description: str = "Dummy tool for testing abstract base functionality."
    args_schema: type[SampleArgs] = SampleArgs

    def __init__(self, mode: str = "nominal") -> None:
        self.mode = mode

    async def _run(self, **kwargs: Any) -> Any:
        if self.mode == "dict":
            return {"echo": kwargs["query"], "count": kwargs.get("count", 1)}
        if self.mode == "dto":
            return SampleArgs(query=kwargs["query"], count=kwargs.get("count", 1))
        if self.mode == "none":
            return None
        if self.mode == "primitive":
            return "ok"
        if self.mode == "direct_result":
            return ToolExecutionResult(
                success=True, tool_name=self.name, data={"direct": True}
            )
        if self.mode == "domain_error":
            raise OrderNotFoundError("CMD-77777")
        if self.mode == "security_error":
            raise SecurityAccessError("PII leak blocked")
        if self.mode == "raw_error":
            raise RuntimeError("Database connection timed out")
        return {"result": kwargs["query"]}


def test_tool_interface_protocol_conformance() -> None:
    """Validate runtime protocol conformance for ToolInterface."""
    tool = DummyTool()
    assert isinstance(tool, ToolInterface)
    assert isinstance(tool, BaseTool)

    class IncompleteTool:
        name = "incomplete"

    assert not isinstance(IncompleteTool(), ToolInterface)


def test_base_tool_abstract_instantiation() -> None:
    """Verify BaseTool cannot be instantiated directly without _run implementation."""
    with pytest.raises(TypeError, match="Can't instantiate abstract class BaseTool"):
        BaseTool()  # type: ignore[abstract]


def test_base_tool_mcp_spec_and_validation() -> None:
    """Validate MCP specification generation and argument validation helper."""
    tool = DummyTool()
    spec = tool.get_mcp_spec()
    assert spec["name"] == "dummy_tool"
    assert "parameters" in spec
    assert spec["parameters"]["type"] == "object"

    validated = tool.validate_arguments(query="hello", count=5)
    assert isinstance(validated, SampleArgs)
    assert validated.query == "hello"
    assert validated.count == 5


@pytest.mark.asyncio
async def test_base_tool_execute_success_types() -> None:
    """Verify execute shields return types: dict, BaseDTO, ToolExecutionResult, None, primitive."""
    dict_tool = DummyTool(mode="dict")
    res_dict = await dict_tool.execute(query="test_query", count=2)
    assert res_dict.success is True
    assert res_dict.tool_name == "dummy_tool"
    assert res_dict.data == {"echo": "test_query", "count": 2}

    dto_tool = DummyTool(mode="dto")
    res_dto = await dto_tool.execute(query="test_dto", count=3)
    assert res_dto.success is True
    assert res_dto.data == {"query": "test_dto", "count": 3}

    none_tool = DummyTool(mode="none")
    res_none = await none_tool.execute(query="test_none")
    assert res_none.success is True
    assert res_none.data is None

    prim_tool = DummyTool(mode="primitive")
    res_prim = await prim_tool.execute(query="test_prim")
    assert res_prim.success is True
    assert res_prim.data == {"result": "ok"}

    direct_tool = DummyTool(mode="direct_result")
    res_direct = await direct_tool.execute(query="test_direct")
    assert res_direct.success is True
    assert res_direct.data == {"direct": True}


@pytest.mark.asyncio
async def test_base_tool_argument_validation_shielding() -> None:
    """Validate that invalid, missing, or forbidden extra arguments are shielded."""
    tool = DummyTool()
    # Missing required 'query'
    res_missing = await tool.execute()
    assert res_missing.success is False
    assert res_missing.error_code == "INVALID_ARGUMENTS"

    # Count negative (violates ge=1)
    res_invalid = await tool.execute(query="valid", count=0)
    assert res_invalid.success is False
    assert res_invalid.error_code == "INVALID_ARGUMENTS"

    # Extra arguments (forbidden by BaseDTO)
    res_extra = await tool.execute(query="valid", extra_field="bad")
    assert res_extra.success is False
    assert res_extra.error_code == "INVALID_ARGUMENTS"


@pytest.mark.asyncio
async def test_base_tool_domain_exception_shielding() -> None:
    """Validate domain errors are converted to ToolExecutionResult with exact error codes."""
    err_tool = DummyTool(mode="domain_error")
    res = await err_tool.execute(query="find")
    assert res.success is False
    assert res.error_code == "ORDER_NOT_FOUND"
    assert "CMD-77777" in (res.error_message or "")

    sec_tool = DummyTool(mode="security_error")
    sec_res = await sec_tool.execute(query="leak")
    assert sec_res.success is False
    assert sec_res.error_code == "SECURITY_UNAUTHORIZED_ACCESS"


@pytest.mark.asyncio
async def test_base_tool_raw_exception_shielding() -> None:
    """Validate raw unhandled exceptions are caught and wrapped in TOOL_EXECUTION_ERROR."""
    raw_tool = DummyTool(mode="raw_error")
    res = await raw_tool.execute(query="crash")
    assert res.success is False
    assert res.error_code == "TOOL_EXECUTION_ERROR"
    assert "Database connection timed out" in (res.error_message or "")


@pytest.mark.asyncio
async def test_shield_tool_execution_decorator() -> None:
    """Validate @shield_tool_execution on standalone functions and methods."""

    @shield_tool_execution(tool_name="standalone_tool", args_schema=SampleArgs)
    async def standalone_fn(query: str, count: int = 1) -> dict[str, Any]:
        return {"processed": query, "total": count * 10}

    # Success invocation
    ok_res = await standalone_fn(query="sample", count=4)
    assert ok_res.success is True
    assert ok_res.tool_name == "standalone_tool"
    assert ok_res.data == {"processed": "sample", "total": 40}

    # Validation failure invocation
    fail_res = await standalone_fn(query="sample", count=-1)
    assert fail_res.success is False
    assert fail_res.error_code == "INVALID_ARGUMENTS"

    # Synchronous function wrapping
    @shield_tool_execution(tool_name="sync_tool")
    def sync_fn(value: int) -> int:
        if value < 0:
            raise BusinessRuleViolationError("Negative value prohibited")
        return value * 2

    sync_ok = await sync_fn(value=5)
    assert sync_ok.success is True
    assert sync_ok.data == {"result": 10}

    sync_err = await sync_fn(value=-5)
    assert sync_err.success is False
    assert sync_err.error_code == "BUSINESS_RULE_VIOLATION"


@pytest.mark.asyncio
async def test_existing_domain_tools_inherit_base_tool() -> None:
    """Verify OrderStatusTool, DelayCalculatorTool, and RefundCalculatorTool conform to BaseTool."""
    order_tool = OrderStatusTool()
    assert isinstance(order_tool, BaseTool)
    assert isinstance(order_tool, ToolInterface)
    order_res = await order_tool.execute(
        order_id="CMD-10001", customer_email="alice@example.com"
    )
    assert order_res.success is True
    assert order_res.data is not None
    assert order_res.data["order_id"] == "CMD-10001"
    assert order_res.data["status"] == "DELIVERED"

    now = datetime.now(timezone.utc)
    delay_tool = DelayCalculatorTool()
    assert isinstance(delay_tool, BaseTool)
    delay_res = await delay_tool.execute(
        estimated_delivery_date=now,
        reference_date=now,
        is_express=True,
        shipping_fee_cents=500,
    )
    assert delay_res.success is True
    assert delay_res.data is not None
    assert "delay_days" in delay_res.data

    refund_tool = RefundCalculatorTool()
    assert isinstance(refund_tool, BaseTool)
    refund_res = await refund_tool.execute(
        delivery_date=now,
        request_date=now,
        item_prices_cents=[1000, 2000],
        shipping_fee_cents=400,
    )
    assert refund_res.success is True
    assert refund_res.data is not None
    assert refund_res.data["is_eligible_for_return"] is True
