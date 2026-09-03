"""Observability tracer and span emitter for 8_support_agent."""

import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class AgentTracer:
    """Manages telemetry spans and execution duration tracking."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id

    @contextmanager
    def span(self, operation: str, **attributes: Any) -> Generator[None, None, None]:
        """Track elapsed duration of an operation and emit structured telemetry."""
        start_time = time.perf_counter()
        logger.info(
            "span_start",
            session_id=self.session_id,
            operation=operation,
            **attributes,
        )
        try:
            yield
        finally:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.info(
                "span_end",
                session_id=self.session_id,
                operation=operation,
                duration_ms=duration_ms,
            )
