"""Tenacity retry executor and exception shielding for LLM inference calls."""

from collections.abc import Callable, Coroutine
from typing import Any

import openai
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from core.exceptions import (
    AppBaseError,
    LLMAuthenticationError,
    LLMInferenceError,
    LLMTimeoutError,
)
from observability.logger import get_logger

logger = get_logger(__name__)

__all__ = ["build_llm_retrying", "execute_with_retry"]

RETRIABLE_OPENAI_EXCEPTIONS = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
)


def build_llm_retrying(
    max_retries: int,
    min_wait: float,
    max_wait: float,
) -> AsyncRetrying:
    """Construct an AsyncRetrying instance configured for transient LLM faults."""
    return AsyncRetrying(
        retry=retry_if_exception_type(RETRIABLE_OPENAI_EXCEPTIONS),
        wait=wait_random_exponential(min=min_wait, max=max_wait),
        stop=stop_after_attempt(max_retries),
        reraise=True,
    )


async def execute_with_retry(
    retrying: AsyncRetrying,
    operation: Callable[[], Coroutine[Any, Any, Any]],
) -> Any:
    """Execute async operation under Tenacity retry loop with domain exception shielding."""
    try:
        async for attempt in retrying:
            with attempt:
                return await operation()
    except openai.AuthenticationError as exc:
        logger.error("llm_authentication_error", error=str(exc))
        raise LLMAuthenticationError(f"LLM authentication failed: {exc}") from exc
    except (openai.APITimeoutError, TimeoutError) as exc:
        logger.error("llm_timeout_error", error=str(exc))
        raise LLMTimeoutError(f"LLM request timed out: {exc}") from exc
    except openai.APIError as exc:
        err_code = getattr(exc, "code", None) or "LLM_API_ERROR"
        logger.error("llm_api_error", error=str(exc), code=err_code)
        raise LLMInferenceError(
            f"LLM API error ({err_code}): {exc.message}",
            error_code="LLM_API_ERROR",
        ) from exc
    except AppBaseError:
        raise
    except Exception as exc:
        logger.error("llm_unexpected_error", error=str(exc))
        raise LLMInferenceError(
            f"Unexpected error during LLM inference: {exc}",
            error_code="LLM_INFERENCE_UNEXPECTED",
        ) from exc
