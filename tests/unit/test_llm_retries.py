"""Unit tests verifying Tenacity retries, recovery, and exception shielding in LLMClient."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import openai
import pytest

from clients.llm_client import LLMClient
from core.exceptions import (
    LLMAuthenticationError,
    LLMInferenceError,
    LLMTimeoutError,
)


def _make_response(status_code: int) -> httpx.Response:
    req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return httpx.Response(status_code, request=req)


def _make_mock_client() -> MagicMock:
    client = MagicMock()
    client.beta = MagicMock()
    client.beta.chat.completions = MagicMock()
    client.chat.completions = MagicMock()
    return client


@pytest.mark.asyncio
async def test_retry_recovers_from_rate_limit() -> None:
    """Verify LLMClient retries on RateLimitError and recovers when subsequent call succeeds."""
    mock_client = _make_mock_client()
    rate_err = openai.RateLimitError(
        "Rate limit", response=_make_response(429), body=None
    )

    mock_resp = MagicMock()
    mock_resp.choices = [
        MagicMock(
            message=MagicMock(content="Recovered", tool_calls=None),
            finish_reason="stop",
        )
    ]
    mock_resp.usage = None

    mock_client.chat.completions.create = AsyncMock(side_effect=[rate_err, mock_resp])

    client = LLMClient(
        client=mock_client,
        max_retries=3,
        retry_min_wait=0.001,
        retry_max_wait=0.005,
    )
    res = await client.generate_with_tools(messages=[{"role": "user", "content": "Hi"}])
    assert res.content == "Recovered"
    assert mock_client.chat.completions.create.await_count == 2


@pytest.mark.asyncio
async def test_retry_recovers_from_connection_and_500_errors() -> None:
    """Verify retries on APIConnectionError and InternalServerError before succeeding."""
    mock_client = _make_mock_client()
    req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    conn_err = openai.APIConnectionError(request=req)
    server_err = openai.InternalServerError(
        "500 err", response=_make_response(500), body=None
    )

    mock_resp = MagicMock()
    mock_resp.choices = [
        MagicMock(
            message=MagicMock(content="Success after 500", tool_calls=None),
            finish_reason="stop",
        )
    ]
    mock_resp.usage = None

    mock_client.chat.completions.create = AsyncMock(
        side_effect=[conn_err, server_err, mock_resp]
    )

    client = LLMClient(
        client=mock_client,
        max_retries=3,
        retry_min_wait=0.001,
        retry_max_wait=0.005,
    )
    res = await client.generate_with_tools(messages=[{"role": "user", "content": "Hi"}])
    assert res.content == "Success after 500"
    assert mock_client.chat.completions.create.await_count == 3


@pytest.mark.asyncio
async def test_retry_exhaustion_raises_llm_inference_error() -> None:
    """Verify exhausting retries on RateLimitError raises LLMInferenceError."""
    mock_client = _make_mock_client()
    rate_err = openai.RateLimitError(
        "Quota limit", response=_make_response(429), body=None
    )
    mock_client.chat.completions.create = AsyncMock(side_effect=rate_err)

    client = LLMClient(
        client=mock_client,
        max_retries=2,
        retry_min_wait=0.001,
        retry_max_wait=0.005,
    )
    with pytest.raises(LLMInferenceError) as exc_info:
        await client.generate_with_tools(messages=[{"role": "user", "content": "Hi"}])
    assert exc_info.value.error_code == "LLM_API_ERROR"
    assert mock_client.chat.completions.create.await_count == 2


@pytest.mark.asyncio
async def test_timeout_raises_llm_timeout_error() -> None:
    """Verify APITimeoutError is shielded into LLMTimeoutError."""
    mock_client = _make_mock_client()
    req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    mock_client.chat.completions.create = AsyncMock(
        side_effect=openai.APITimeoutError(req)
    )

    client = LLMClient(
        client=mock_client,
        max_retries=1,
        retry_min_wait=0.001,
        retry_max_wait=0.005,
    )
    with pytest.raises(LLMTimeoutError) as exc_info:
        await client.generate_with_tools(messages=[{"role": "user", "content": "Hi"}])
    assert exc_info.value.error_code == "LLM_TIMEOUT_ERROR"


@pytest.mark.asyncio
async def test_authentication_error_fails_fast_without_retries() -> None:
    """Verify 401 AuthenticationError is not retried and raises LLMAuthenticationError."""
    mock_client = _make_mock_client()
    auth_err = openai.AuthenticationError(
        "Invalid API Key", response=_make_response(401), body=None
    )
    mock_client.chat.completions.create = AsyncMock(side_effect=auth_err)

    client = LLMClient(
        client=mock_client,
        max_retries=3,
        retry_min_wait=0.001,
        retry_max_wait=0.005,
    )
    with pytest.raises(LLMAuthenticationError) as exc_info:
        await client.generate_with_tools(messages=[{"role": "user", "content": "Hi"}])
    assert exc_info.value.error_code == "LLM_AUTHENTICATION_ERROR"
    assert mock_client.chat.completions.create.await_count == 1


@pytest.mark.asyncio
async def test_unexpected_runtime_error_shielded() -> None:
    """Verify unexpected runtime exceptions are shielded into LLMInferenceError."""
    mock_client = _make_mock_client()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=RuntimeError("Memory fault")
    )

    client = LLMClient(
        client=mock_client,
        max_retries=1,
        retry_min_wait=0.001,
        retry_max_wait=0.005,
    )
    with pytest.raises(LLMInferenceError) as exc_info:
        await client.generate_with_tools(messages=[{"role": "user", "content": "Hi"}])
    assert exc_info.value.error_code == "LLM_INFERENCE_UNEXPECTED"
