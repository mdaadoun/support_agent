"""Unit tests for structlog structured JSON logging configuration."""

import io
import json
from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path

import pytest

from observability.logger import (
    DualStreamWriter,
    bind_contextvars,
    clear_contextvars,
    get_contextvars,
    get_logger,
    reset_logger,
    setup_logger,
    unbind_contextvars,
)


@pytest.fixture(autouse=True)
def clean_logger_state() -> Generator[None, None, None]:
    """Ensure clean logger state before and after each test."""
    reset_logger()
    yield
    reset_logger()


def test_structured_json_logging_output_format() -> None:
    """Verify structured logger emits valid single-line JSON with standard fields."""
    stream = io.StringIO()
    setup_logger(log_level="INFO", stream=stream, json_output=True)
    logger = get_logger("test_module")

    logger.info("order_status_queried", order_id="CMD-12345", status="DELIVERED")

    output = stream.getvalue().strip()
    assert output != ""
    data = json.loads(output)

    assert data["event"] == "order_status_queried"
    assert data["level"] == "info"
    assert data["logger"] == "test_module"
    assert data["order_id"] == "CMD-12345"
    assert data["status"] == "DELIVERED"
    assert "timestamp" in data
    # Validate ISO timestamp format
    assert datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))


def test_log_level_filtering() -> None:
    """Verify messages below configured log level are filtered out."""
    stream = io.StringIO()
    setup_logger(log_level="WARNING", stream=stream, json_output=True)
    logger = get_logger("test_filter")

    logger.debug("debug_event", step="skip")
    logger.info("info_event", step="skip")
    assert stream.getvalue() == ""

    logger.warning("warning_event", step="keep")
    output = stream.getvalue().strip()
    assert output != ""
    data = json.loads(output)
    assert data["event"] == "warning_event"
    assert data["level"] == "warning"


def test_contextvars_binding_and_clearing() -> None:
    """Verify context variable binding, retrieval, and isolation."""
    stream = io.StringIO()
    setup_logger(log_level="INFO", stream=stream, json_output=True)
    logger = get_logger("test_context")

    bind_contextvars(session_id="SESS-CTX-01", tenant_id="tenant_acme")
    ctx = get_contextvars()
    assert ctx["session_id"] == "SESS-CTX-01"
    assert ctx["tenant_id"] == "tenant_acme"

    logger.info("context_event", action="verify")
    data = json.loads(stream.getvalue().strip())
    assert data["session_id"] == "SESS-CTX-01"
    assert data["tenant_id"] == "tenant_acme"
    assert data["action"] == "verify"

    # Test unbinding single key
    unbind_contextvars("session_id")
    assert "session_id" not in get_contextvars()
    assert get_contextvars()["tenant_id"] == "tenant_acme"

    # Test full clear
    clear_contextvars()
    assert get_contextvars() == {}


def test_exception_traceback_formatting() -> None:
    """Verify exceptions are captured and formatted as strings in JSON output."""
    stream = io.StringIO()
    setup_logger(log_level="INFO", stream=stream, json_output=True)
    logger = get_logger("test_exc")

    try:
        raise ValueError("simulated_failure")
    except ValueError:
        logger.exception("unhandled_error", task_id="TASK-99")

    data = json.loads(stream.getvalue().strip())
    assert data["event"] == "unhandled_error"
    assert data["level"] == "error"
    assert data["task_id"] == "TASK-99"
    assert "exception" in data
    assert "ValueError: simulated_failure" in data["exception"]


def test_non_primitive_safe_serialization() -> None:
    """Verify non-primitive objects (Path, datetime, sets) serialize without crashing."""
    stream = io.StringIO()
    setup_logger(log_level="INFO", stream=stream, json_output=True)
    logger = get_logger("test_serializer")

    logger.info(
        "complex_event",
        path=Path("/var/log/app.log"),
        created_at=datetime.now(timezone.utc),
        tags={"production", "audit"},
    )

    data = json.loads(stream.getvalue().strip())
    assert data["path"] == "/var/log/app.log"
    assert isinstance(data["created_at"], str)
    assert isinstance(data["tags"], str)


def test_dual_stream_writer_file_and_stream(tmp_path: Path) -> None:
    """Verify DualStreamWriter writes to primary stream and appends to file."""
    log_file = tmp_path / "traces.jsonl"
    stream = io.StringIO()

    setup_logger(log_level="INFO", stream=stream, log_file=log_file, json_output=True)
    logger = get_logger("test_dual")

    logger.info("dual_write_test", count=42)

    # Check primary stream
    stream_data = json.loads(stream.getvalue().strip())
    assert stream_data["event"] == "dual_write_test"
    assert stream_data["count"] == 42

    # Check file output
    assert log_file.exists()
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    file_data = json.loads(lines[0])
    assert file_data["event"] == "dual_write_test"
    assert file_data["count"] == 42


def test_dual_stream_writer_resilience_to_io_error() -> None:
    """Verify DualStreamWriter shields against invalid file paths without crashing."""
    stream = io.StringIO()
    # Invalid directory path that cannot be opened for writing
    invalid_file = Path("/nonexistent_directory_12345/sub/traces.jsonl")

    writer = DualStreamWriter(stream=stream, file_path=invalid_file)
    # Should not raise exception
    writer.write('{"event": "shielded"}\n')
    writer.flush()

    assert stream.getvalue() == '{"event": "shielded"}\n'


def test_dev_console_output_mode() -> None:
    """Verify json_output=False uses console renderer."""
    stream = io.StringIO()
    setup_logger(log_level="INFO", stream=stream, json_output=False)
    logger = get_logger("test_dev")

    logger.info("console_event", key="value")
    output = stream.getvalue()
    assert "console_event" in output
    assert "key" in output
