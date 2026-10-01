"""Unit tests verifying LLMClient initialization, temperature validation, and tool calling."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from clients.llm_client import LLMClient
from core.exceptions import BusinessRuleViolationError, LLMResponseValidationError
from models.llm import LLMResponse


@pytest.fixture
def mock_openai_client() -> MagicMock:
    """Fixture providing a mocked AsyncOpenAI client with completions."""
    client = MagicMock()
    client.beta = MagicMock()
    client.beta.chat = MagicMock()
    client.beta.chat.completions = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    return client


def test_llm_client_initialization_defaults() -> None:
    """Verify default model, temperature clamping <= 0.2, and custom parameters."""
    client = LLMClient(model_name="gpt-4o-mini")
    assert client.model_name == "gpt-4o-mini"
    assert client.temperature <= 0.2

    custom_client = LLMClient(model_name="custom-model", temperature=0.05)
    assert custom_client.model_name == "custom-model"
    assert custom_client.temperature == 0.05


def test_llm_client_temperature_validation_bounds() -> None:
    """Verify that temperatures > 0.2 or < 0.0 raise BusinessRuleViolationError."""
    with pytest.raises(BusinessRuleViolationError) as exc_high:
        LLMClient(temperature=0.5)
    assert exc_high.value.error_code == "LLM_TEMPERATURE_INVALID"

    with pytest.raises(BusinessRuleViolationError) as exc_low:
        LLMClient(temperature=-0.1)
    assert exc_low.value.error_code == "LLM_TEMPERATURE_INVALID"


@pytest.mark.asyncio
async def test_llm_client_generate_with_tools_success(
    mock_openai_client: MagicMock,
) -> None:
    """Verify generate_with_tools parses tool calls, content, and token usage."""
    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_abc123"
    mock_tool_call.function.name = "get_order_details"
    mock_tool_call.function.arguments = '{"order_id": "CMD-12345"}'

    mock_choice = MagicMock()
    mock_choice.message.content = "I will check the order status."
    mock_choice.message.tool_calls = [mock_tool_call]
    mock_choice.finish_reason = "tool_calls"

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.model = "gpt-4o-mini"
    mock_response.usage.prompt_tokens = 150
    mock_response.usage.completion_tokens = 50
    mock_response.usage.total_tokens = 200

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

    client = LLMClient(client=mock_openai_client)
    messages: list[dict[str, Any]] = [{"role": "user", "content": "Where is my order?"}]
    tools: list[dict[str, Any]] = [
        {"type": "function", "function": {"name": "get_order_details"}}
    ]

    resp = await client.generate_with_tools(messages=messages, tools=tools)

    assert isinstance(resp, LLMResponse)
    assert resp.content == "I will check the order status."
    assert resp.has_tool_calls is True
    assert len(resp.tool_calls) == 1
    assert resp.first_tool_call is not None
    assert resp.first_tool_call.id == "call_abc123"
    assert resp.first_tool_call.name == "get_order_details"
    assert resp.first_tool_call.arguments == {"order_id": "CMD-12345"}
    assert resp.usage.prompt_tokens == 150
    assert resp.usage.completion_tokens == 50
    assert resp.usage.cost_usd > 0.0


@pytest.mark.asyncio
async def test_llm_client_generate_with_tools_no_tool_calls(
    mock_openai_client: MagicMock,
) -> None:
    """Verify generate_with_tools handles message with pure text content and zero tool calls."""
    mock_choice = MagicMock()
    mock_choice.message.content = "Here is your answers."
    mock_choice.message.tool_calls = None
    mock_choice.finish_reason = "stop"

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.model = "gpt-4o-mini"
    mock_response.usage = None

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

    client = LLMClient(client=mock_openai_client)
    resp = await client.generate_with_tools(
        messages=[{"role": "user", "content": "Hello"}]
    )

    assert resp.has_tool_calls is False
    assert resp.first_tool_call is None
    assert resp.content == "Here is your answers."
    assert resp.finish_reason == "stop"


@pytest.mark.asyncio
async def test_llm_client_generate_with_tools_malformed_arguments(
    mock_openai_client: MagicMock,
) -> None:
    """Verify tool call with unparseable JSON arguments raises LLMResponseValidationError."""
    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_bad"
    mock_tool_call.function.name = "broken_tool"
    mock_tool_call.function.arguments = "{unquoted_json_key:"

    mock_choice = MagicMock()
    mock_choice.message.content = None
    mock_choice.message.tool_calls = [mock_tool_call]
    mock_choice.finish_reason = "tool_calls"

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = None

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

    client = LLMClient(client=mock_openai_client)
    with pytest.raises(LLMResponseValidationError) as exc_info:
        await client.generate_with_tools(
            messages=[{"role": "user", "content": "Run broken tool"}]
        )
    assert "Malformed JSON" in str(exc_info.value)


@pytest.mark.asyncio
async def test_llm_client_generate_with_tools_empty_messages() -> None:
    """Verify passing empty messages raises BusinessRuleViolationError."""
    client = LLMClient()
    with pytest.raises(BusinessRuleViolationError) as exc_info:
        await client.generate_with_tools(messages=[])
    assert exc_info.value.error_code == "LLM_EMPTY_MESSAGES"
