"""Structured JSON logging via structlog for 8_support_agent."""

from __future__ import annotations

import io
import logging
import sys
from pathlib import Path
from typing import Any, TextIO

import structlog
from structlog.typing import FilteringBoundLogger

from core.config import get_settings

__all__ = [
    "DualStreamWriter",
    "bind_contextvars",
    "clear_contextvars",
    "get_contextvars",
    "get_logger",
    "reset_logger",
    "setup_logger",
    "unbind_contextvars",
]

_is_configured: bool = False


class DualStreamWriter(io.StringIO):
    """Thread-safe writer supporting stream output and optional file appending."""

    def __init__(
        self,
        stream: TextIO | None = None,
        file_path: Path | str | None = None,
    ) -> None:
        super().__init__()
        self.stream: TextIO = stream if stream is not None else sys.stdout
        self.file_path: Path | None = Path(file_path) if file_path else None

    def write(self, s: str) -> int:
        """Write formatted log message to primary stream and optional file."""
        self.stream.write(s)
        if self.file_path is not None:
            try:
                with open(self.file_path, "a", encoding="utf-8") as file:
                    file.write(s)
            except Exception:
                # Shield logging from raw I/O failures to prevent crashes
                pass
        return len(s)

    def flush(self) -> None:
        """Flush the primary output stream."""
        self.stream.flush()


def setup_logger(
    log_level: str | None = None,
    stream: TextIO | None = None,
    log_file: Path | str | None = None,
    json_output: bool = True,
) -> None:
    """Configure structlog for JSON Lines output to standard out and optional file.

    Args:
        log_level: Case-insensitive level name (DEBUG, INFO, WARNING, ERROR).
        stream: Primary text stream sink (defaults to sys.stdout).
        log_file: Optional path for appending JSON log lines (e.g. traces.jsonl).
        json_output: Whether to output strict JSON Lines or development console text.
    """
    global _is_configured

    if log_level is None:
        try:
            settings = get_settings()
            log_level = settings.log_level
        except Exception:
            log_level = "INFO"

    level_num: int = getattr(logging, log_level.upper(), logging.INFO)

    renderer: structlog.types.Processor
    if json_output:
        renderer = structlog.processors.JSONRenderer(sort_keys=True, default=str)
    else:
        renderer = structlog.dev.ConsoleRenderer()

    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.format_exc_info,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        renderer,
    ]

    writer = DualStreamWriter(stream=stream, file_path=log_file)

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level_num),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=writer),
        cache_logger_on_first_use=False,
    )
    _is_configured = True


def _ensure_configured() -> None:
    """Ensure structlog is initialized with default settings before first use."""
    if not _is_configured:
        setup_logger()


def get_logger(name: str = __name__) -> FilteringBoundLogger:
    """Retrieve configured bound structured logger instance."""
    _ensure_configured()
    logger: FilteringBoundLogger = structlog.get_logger(name)
    if name:
        return logger.bind(logger=name)
    return logger


def bind_contextvars(**kwargs: Any) -> None:
    """Bind contextual attributes to all future log records in active context."""
    structlog.contextvars.bind_contextvars(**kwargs)


def unbind_contextvars(*keys: str) -> None:
    """Remove specified attributes from active structlog context."""
    structlog.contextvars.unbind_contextvars(*keys)


def clear_contextvars() -> None:
    """Clear all contextual variables from active structlog context."""
    structlog.contextvars.clear_contextvars()


def get_contextvars() -> dict[str, Any]:
    """Retrieve copy of active context variables."""
    return structlog.contextvars.get_contextvars()


def reset_logger() -> None:
    """Reset structlog configuration and context state (primarily for test isolation)."""
    global _is_configured
    clear_contextvars()
    structlog.reset_defaults()
    _is_configured = False


# Auto-configure structured JSON logging on module import
setup_logger()
