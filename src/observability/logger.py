"""Structured JSON logging via structlog for 8_support_agent."""

import logging
from typing import Any

import structlog


def setup_logger(log_level: str = "INFO") -> None:
    """Configure structlog for JSON Lines output to standard out."""
    level_num: int = getattr(logging, log_level.upper(), logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level_num),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = __name__) -> Any:
    """Retrieve configured bound structured logger instance."""
    return structlog.get_logger(name)
