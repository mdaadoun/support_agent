"""Unit tests asserting API error handling middleware, status mapping, and tenant isolation."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_agent_service
from api.service import AgentService
from core.exceptions import (
    BusinessRuleViolationError,
    CircuitBreakerError,
    ConfigurationError,
    FSMStateError,
    OrderNotFoundError,
    SecurityAccessError,
    ToolExecutionError,
)
from models.email import InboundEmailMessage
from models.enums import AgentLifecycleState
from models.session import AgentSessionSnapshot
from persistence.session_store import SessionStateStore


@pytest.fixture
def sample_payload() -> dict[str, str]:
    return {
        "message_id": "MSG-TEST-500",
        "sender_email": "user@example.com",
        "subject": "Help",
        "body_text": "Need help with order",
        "received_at": datetime.now(timezone.utc).isoformat(),
    }


@pytest.mark.parametrize(
    ("exception_cls", "expected_status", "expected_code"),
    [
        (SecurityAccessError, 403, "SECURITY_UNAUTHORIZED_ACCESS"),
        (OrderNotFoundError, 404, "ORDER_NOT_FOUND"),
        (BusinessRuleViolationError, 422, "BUSINESS_RULE_VIOLATION"),
        (FSMStateError, 409, "FSM_STATE_INVALID"),
        (CircuitBreakerError, 503, "CIRCUIT_BREAKER_TRIPPED"),
        (ToolExecutionError, 502, "TOOL_EXECUTION_ERROR"),
        (ConfigurationError, 500, "CONFIGURATION_ERROR"),
    ],
)
def test_domain_exception_status_mapping(
    sample_payload: dict[str, str],
    exception_cls: type,
    expected_status: int,
    expected_code: str,
) -> None:
    """Verify each domain exception maps strictly to its designated HTTP status code."""
    app = create_app()
    mock_svc = MagicMock()
    if exception_cls is OrderNotFoundError:
        mock_svc.process_email = AsyncMock(side_effect=OrderNotFoundError("CMD-999"))
    elif exception_cls is ToolExecutionError:
        mock_svc.process_email = AsyncMock(
            side_effect=ToolExecutionError("Tool timeout", tool_name="status_tool")
        )
    else:
        mock_svc.process_email = AsyncMock(side_effect=exception_cls("Operation fault"))

    app.dependency_overrides[get_agent_service] = lambda: mock_svc

    with TestClient(app) as client:
        resp = client.post("/agent/process", json=sample_payload)
        assert resp.status_code == expected_status
        data = resp.json()
        assert data["error_code"] == expected_code
        assert "message" in data


def test_unhandled_exception_returns_clean_500(sample_payload: dict[str, str]) -> None:
    """Verify raw runtime exceptions are shielded into clean 500 without leaking stack traces."""
    app = create_app()
    mock_svc = MagicMock()
    mock_svc.process_email = AsyncMock(
        side_effect=RuntimeError("Raw database driver crash")
    )
    app.dependency_overrides[get_agent_service] = lambda: mock_svc

    with TestClient(app) as client:
        resp = client.post("/agent/process", json=sample_payload)
        assert resp.status_code == 500
        data = resp.json()
        assert data["error_code"] == "INTERNAL_SERVER_ERROR"
        assert "Raw database driver crash" not in data["message"]
        assert "Traceback" not in resp.text


def test_agent_service_tenant_isolation() -> None:
    """Verify AgentService enforces tenant partition boundaries and isolation."""
    store = SessionStateStore()
    store.clear()

    snapshot_alpha = AgentSessionSnapshot(
        session_id="SESS-ISOLATION-01",
        inbound_message=InboundEmailMessage(
            message_id="MSG-ISO-1",
            sender_email="tenant_a@example.com",
            subject="Alpha Subject",
            body_text="Alpha Body",
            received_at=datetime.now(timezone.utc),
        ),
        current_state=AgentLifecycleState.COMPLETED,
        tenant_id="tenant_alpha",
    )
    store.save(snapshot_alpha)

    service = AgentService(session_store=store)
    app = create_app()
    app.dependency_overrides[get_agent_service] = lambda: service

    with TestClient(app) as client:
        # 1. Query under correct tenant -> 200 OK
        resp_alpha = client.get(
            "/agent/sessions/SESS-ISOLATION-01",
            headers={"X-Tenant-ID": "tenant_alpha"},
        )
        assert resp_alpha.status_code == 200
        assert resp_alpha.json()["session_id"] == "SESS-ISOLATION-01"

        # 2. Query under different tenant -> 404 Not Found (Cross-tenant access blocked)
        resp_beta = client.get(
            "/agent/sessions/SESS-ISOLATION-01",
            headers={"X-Tenant-ID": "tenant_beta"},
        )
        assert resp_beta.status_code == 404
        assert resp_beta.json()["error_code"] == "SESSION_NOT_FOUND"


def test_invalid_tenant_and_session_id_boundary_rejection() -> None:
    """Verify AgentService rejects malformed tenant and session IDs with 422."""
    app = create_app()
    with TestClient(app) as client:
        resp_bad_tenant = client.get(
            "/agent/sessions/SESS-01",
            headers={"X-Tenant-ID": "../../../etc/passwd"},
        )
        assert resp_bad_tenant.status_code == 422
        assert resp_bad_tenant.json()["error_code"] == "INVALID_TENANT_ID"

        resp_bad_session = client.get(
            "/agent/sessions/bad session!!",
            headers={"X-Tenant-ID": "tenant_valid"},
        )
        assert resp_bad_session.status_code == 422
        assert resp_bad_session.json()["error_code"] == "INVALID_SESSION_ID"


def test_cors_headers_present() -> None:
    """Verify CORS middleware attaches allow-origin headers."""
    app = create_app()
    with TestClient(app) as client:
        resp = client.get(
            "/health", headers={"Origin": "https://dashboard.example.com"}
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "*"
