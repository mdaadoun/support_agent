"""Unit tests asserting Step 8.2 Rich Terminal CLI runner functionality."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from cli import app
from typer.testing import CliRunner

from models.email import InboundEmailMessage
from models.enums import IntentEnum, ResolutionStatusEnum
from models.response import AgentFinalResponse
from models.session import AgentSessionSnapshot
from models.tools import ToolCallTrace, ToolExecutionResult

runner = CliRunner()


def _make_dummy_agent_response() -> tuple[AgentFinalResponse, AgentSessionSnapshot]:
    response = AgentFinalResponse(
        session_id="SESS-CLI-001",
        intent=IntentEnum.ORDER_STATUS,
        confidence_score=0.95,
        order_id="CMD-10001",
        actions_taken=("get_order_details",),
        status_resolution=ResolutionStatusEnum.RESOLVED_AUTOMATICALLY,
        internal_technical_summary="Order CMD-10001 delivered on schedule.",
        email_response_subject="Order CMD-10001 Delivered",
        email_response_body="Hello Alice, your order has been delivered.",
        tokens_prompt=120,
        tokens_completion=40,
        cost_estimation_usd=0.00015,
        execution_time_seconds=0.45,
    )
    snapshot = AgentSessionSnapshot(
        session_id="SESS-CLI-001",
        inbound_message=InboundEmailMessage(
            message_id="MSG-CLI-01",
            sender_email="alice@example.com",
            subject="Order status",
            body_text="Where is my order CMD-10001?",
            received_at=datetime.now(timezone.utc),
        ),
        current_state="COMPLETED",  # type: ignore[arg-type]
        tool_traces=(
            ToolCallTrace(
                tool_call_id="call_001",
                tool_name="get_order_details",
                arguments={
                    "order_id": "CMD-10001",
                    "customer_email": "alice@example.com",
                },
                result=ToolExecutionResult(
                    success=True,
                    tool_name="get_order_details",
                    data={"order_id": "CMD-10001", "status": "DELIVERED"},
                ),
                timestamp=datetime.now(timezone.utc),
                duration_ms=42.5,
            ),
        ),
        tenant_id="default_tenant",
    )
    return response, snapshot


def test_cli_info() -> None:
    """Verify info command displays diagnostics panel."""
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    assert "Service Diagnostics" in result.stdout
    assert "8_support_agent" in result.stdout


def test_cli_check_order_found() -> None:
    """Verify check-order command queries mock ERP successfully."""
    result = runner.invoke(app, ["check-order", "CMD-10001"])
    assert result.exit_code == 0
    assert "Order Details: CMD-10001" in result.stdout
    assert "alice@example.com" in result.stdout
    assert "DELIVERED" in result.stdout


def test_cli_check_order_not_found() -> None:
    """Verify check-order handles missing order gracefully."""
    result = runner.invoke(app, ["check-order", "CMD-99999"])
    assert result.exit_code == 0
    assert "Order 'CMD-99999' not found in mock ERP" in result.stdout


def test_cli_run_missing_inputs() -> None:
    """Verify run fails when no input mechanism is provided."""
    result = runner.invoke(app, ["run"])
    assert result.exit_code == 1
    assert "Provide --file, --interactive, or --sender and --body" in result.stdout


def test_cli_run_nonexistent_file() -> None:
    """Verify run handles nonexistent file path."""
    result = runner.invoke(app, ["run", "--file", "data/nonexistent_file.json"])
    assert result.exit_code == 1
    assert "Error:" in result.stdout


def test_cli_run_with_json_file() -> None:
    """Verify run parses JSON email file and prints formatted tables and panels."""
    fixture_path = Path("tests/fixtures/sample_emails/sample_email.json")
    resp, snap = _make_dummy_agent_response()

    with patch("cli.execute_agent", return_value=(resp, snap)):
        result = runner.invoke(app, ["run", "--file", str(fixture_path)])
        assert result.exit_code == 0
        assert "Execution Summary" in result.stdout
        assert "SESS-CLI-001" in result.stdout
        assert "ReAct Tool Execution Traces" in result.stdout
        assert "get_order_details" in result.stdout
        assert "SUCCESS" in result.stdout
        assert "Certified Email Response" in result.stdout
        assert "Tokens: 120 prompt" in result.stdout


def test_cli_run_with_text_file() -> None:
    """Verify run parses structured text email file with headers."""
    fixture_path = Path("tests/fixtures/sample_emails/sample_email.txt")
    resp, snap = _make_dummy_agent_response()

    with patch("cli.execute_agent", return_value=(resp, snap)):
        result = runner.invoke(app, ["run", "--file", str(fixture_path)])
        assert result.exit_code == 0
        assert "Execution Summary" in result.stdout
        assert "Order CMD-10001 Delivered" in result.stdout


def test_cli_run_with_direct_arguments() -> None:
    """Verify run accepts direct sender, subject, and body options."""
    resp, snap = _make_dummy_agent_response()

    with patch("cli.execute_agent", return_value=(resp, snap)):
        result = runner.invoke(
            app,
            [
                "run",
                "--sender",
                "alice@example.com",
                "--subject",
                "Where is CMD-10001?",
                "--body",
                "Need tracking status please.",
            ],
        )
        assert result.exit_code == 0
        assert "SESS-CLI-001" in result.stdout


def test_cli_run_json_output() -> None:
    """Verify --json emits serialized JSON response."""
    resp, snap = _make_dummy_agent_response()

    with patch("cli.execute_agent", return_value=(resp, snap)):
        result = runner.invoke(
            app,
            [
                "run",
                "--sender",
                "alice@example.com",
                "--body",
                "Tracking CMD-10001?",
                "--json",
            ],
        )
        assert result.exit_code == 0
        assert '"session_id": "SESS-CLI-001"' in result.stdout
        assert '"order_id": "CMD-10001"' in result.stdout


def test_cli_run_domain_error_shielding() -> None:
    """Verify domain exceptions are caught and formatted without raw tracebacks."""
    from core.exceptions import SecurityAccessError

    with patch(
        "cli.execute_agent", side_effect=SecurityAccessError("PII email mismatch")
    ):
        result = runner.invoke(
            app,
            [
                "run",
                "--sender",
                "unauthorized@example.com",
                "--body",
                "Give me order CMD-10001",
            ],
        )
        assert result.exit_code == 1
        assert "SECURITY_UNAUTHORIZED_ACCESS" in result.stdout
        assert "PII email mismatch" in result.stdout
        assert "Traceback" not in result.stdout


def test_cli_interactive_prompt_mode() -> None:
    """Verify interactive command prompts user for input and executes."""
    resp, snap = _make_dummy_agent_response()

    with patch("cli.execute_agent", return_value=(resp, snap)):
        result = runner.invoke(
            app,
            ["interactive"],
            input="alice@example.com\nWhere is my order?\nI need order CMD-10001\n",
        )
        assert result.exit_code == 0
        assert "Execution Summary" in result.stdout
        assert "SESS-CLI-001" in result.stdout
