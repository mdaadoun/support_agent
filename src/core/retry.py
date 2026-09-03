"""Tenacity retry wrappers and transient error detectors for 8_support_agent."""

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import structlog
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

from core.config import get_settings
from core.exceptions import ConfigurationError, SecurityAccessError

logger = structlog.get_logger(__name__)

T = TypeVar("T")

RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})
TRANSIENT_KEYWORDS: tuple[str, ...] = (
    "rate limit",
    "429",
    "503",
    "502",
    "504",
    "500",
    "timeout",
    "timed out",
    "connection reset",
    "connection refused",
    "service unavailable",
    "overloaded",
    "temporary failure",
)


def is_retryable_exception(exc: BaseException) -> bool:
    """Determine whether an exception is transient and eligible for retry."""
    if isinstance(exc, ConfigurationError | SecurityAccessError):
        return False

    status_code: int | None = getattr(exc, "status_code", None) or getattr(
        exc, "code", None
    )
    if isinstance(status_code, int):
        if status_code in RETRYABLE_STATUS_CODES:
            return True
        if 400 <= status_code < 500:
            return False

    if isinstance(exc, TimeoutError | ConnectionError):
        return True

    exc_msg = str(exc).lower()
    return any(kw in exc_msg for kw in TRANSIENT_KEYWORDS)


def _log_retry_attempt(retry_state: RetryCallState) -> None:
    """Log retry attempt details using structured logging."""
    fn_name = retry_state.fn.__name__ if retry_state.fn is not None else "external_call"
    attempt = retry_state.attempt_number
    upcoming_sleep = retry_state.next_action.sleep if retry_state.next_action else 0.0
    outcome = retry_state.outcome
    exc = outcome.exception() if outcome and outcome.failed else None

    logger.warning(
        "retry_attempt",
        function=fn_name,
        attempt=attempt,
        sleep_seconds=round(upcoming_sleep, 2),
        error_type=exc.__class__.__name__ if exc else None,
        error_message=str(exc) if exc else None,
    )


def create_sync_retrying(max_attempts: int | None = None) -> Retrying:
    """Construct configured Tenacity Retrying orchestrator for sync functions."""
    settings = get_settings()
    eff_max = max_attempts or settings.retry_max_attempts
    return Retrying(
        stop=stop_after_attempt(eff_max),
        wait=wait_random_exponential(
            min=settings.retry_min_wait_seconds,
            max=settings.retry_max_wait_seconds,
        ),
        retry=retry_if_exception(is_retryable_exception),
        before_sleep=_log_retry_attempt,
        reraise=True,
    )


def create_async_retrying(max_attempts: int | None = None) -> AsyncRetrying:
    """Construct configured Tenacity AsyncRetrying orchestrator for async coroutines."""
    settings = get_settings()
    eff_max = max_attempts or settings.retry_max_attempts
    return AsyncRetrying(
        stop=stop_after_attempt(eff_max),
        wait=wait_random_exponential(
            min=settings.retry_min_wait_seconds,
            max=settings.retry_max_wait_seconds,
        ),
        retry=retry_if_exception(is_retryable_exception),
        before_sleep=_log_retry_attempt,
        reraise=True,
    )


def retry_sync_call(
    func: Callable[..., T],
    *args: Any,
    max_attempts: int | None = None,
    **kwargs: Any,
) -> T:
    """Execute a synchronous function wrapped with Tenacity retry policy."""
    retrying = create_sync_retrying(max_attempts=max_attempts)
    for attempt in retrying:
        with attempt:
            return func(*args, **kwargs)
    raise RuntimeError("Retry loop terminated unexpectedly without returning a value")


async def retry_async_call(
    func: Callable[..., Awaitable[T]],
    *args: Any,
    max_attempts: int | None = None,
    **kwargs: Any,
) -> T:
    """Execute an asynchronous coroutine wrapped with Tenacity retry policy."""
    retrying = create_async_retrying(max_attempts=max_attempts)
    async for attempt in retrying:
        with attempt:
            return await func(*args, **kwargs)
    raise RuntimeError("Retry loop terminated unexpectedly without returning a value")
