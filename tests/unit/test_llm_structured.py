"""Unit tests verifying LLMClient structured generation and schema validation."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel, Field

from clients.llm_client import LLMClient
from core.exceptions import LLMResponseValidationError


class SampleModel(BaseModel):
    summary: str
    score: int = Field(ge=0, le=100)


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


@pytest.mark.asyncio
async def test_llm_client_generate_structured_with_beta_parse(
    mock_openai_client: MagicMock,
) -> None:
    """Verify structured generation using beta parse returns parsed Pydantic model."""
    mock_parsed_obj = SampleModel(summary="All tests passed", score=98)
    mock_choice = MagicMock()
    mock_choice.message.parsed = mock_parsed_obj
    mock_choice.message.refusal = None
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_openai_client.beta.chat.completions.parse = AsyncMock(
        return_value=mock_response
    )

    client = LLMClient(client=mock_openai_client)
    result = await client.generate_structured(
        system_prompt="Analyze",
        user_prompt="Input text",
        response_schema=SampleModel,
    )

    assert isinstance(result, SampleModel)
    assert result.summary == "All tests passed"
    assert result.score == 98
    mock_openai_client.beta.chat.completions.parse.assert_awaited_once()


@pytest.mark.asyncio
async def test_llm_client_generate_structured_refusal_raises_error(
    mock_openai_client: MagicMock,
) -> None:
    """Verify refusal in beta parse raises LLMResponseValidationError."""
    mock_choice = MagicMock()
    mock_choice.message.parsed = None
    mock_choice.message.refusal = "Safety violation policy triggered"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_openai_client.beta.chat.completions.parse = AsyncMock(
        return_value=mock_response
    )

    client = LLMClient(client=mock_openai_client)
    with pytest.raises(LLMResponseValidationError) as exc_info:
        await client.generate_structured(
            system_prompt="Analyze",
            user_prompt="Input text",
            response_schema=SampleModel,
        )
    assert "refused" in str(exc_info.value)


@pytest.mark.asyncio
async def test_llm_client_generate_structured_fallback_json_create(
    mock_openai_client: MagicMock,
) -> None:
    """Verify fallback to standard chat completion with json_object validation."""
    del mock_openai_client.beta

    mock_choice = MagicMock()
    mock_choice.message.content = '{"summary": "Fallback validated", "score": 85}'
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

    client = LLMClient(client=mock_openai_client)
    result = await client.generate_structured(
        system_prompt="Analyze",
        user_prompt="Input text",
        response_schema=SampleModel,
    )

    assert isinstance(result, SampleModel)
    assert result.summary == "Fallback validated"
    assert result.score == 85


@pytest.mark.asyncio
async def test_llm_client_generate_structured_validation_failure(
    mock_openai_client: MagicMock,
) -> None:
    """Verify schema mismatch or invalid JSON raises LLMResponseValidationError."""
    del mock_openai_client.beta

    mock_choice = MagicMock()
    mock_choice.message.content = '{"invalid_key": 123}'
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

    client = LLMClient(client=mock_openai_client)
    with pytest.raises(LLMResponseValidationError):
        await client.generate_structured(
            system_prompt="Analyze",
            user_prompt="Input text",
            response_schema=SampleModel,
        )
