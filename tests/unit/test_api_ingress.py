"""Unit tests verifying FastAPI REST ingress endpoints and authentication."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_agent_service
from core.config import Settings
from core.exceptions import SessionNotFoundError
from models.email import InboundEmailMessage
from models.enums import IntentEnum, ResolutionStatusEnum
from models.response import AgentFinalResponse
from models.session import AgentSessionSnapshot


def _make_dummy_response(session_id: str = "SESS-TEST-01") -> AgentFinalResponse:
    return AgentFinalResponse(
        session_id=session_id,
        intent=IntentEnum.ORDER_STATUS,
        confidence_score=0.95,
        order_id="CMD-10001",
        actions_taken=("get_order_details",),
        status_resolution=ResolutionStatusEnum.RESOLVED_AUTOMATICALLY,
        internal_technical_summary="Delivered order status retrieved.",
        email_response_subject="Order CMD-10001 Status",
        email_response_body="Your order CMD-10001 has been delivered.",
        tokens_prompt=120,
        tokens_completion=45,
        cost_estimation_usd=0.00015,
        execution_time_seconds=0.42,
    )


def test_healthcheck_returns_ok() -> None:
    """Verify /health returns 200 OK and valid health payload."""
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["version"] == "0.1.0"


def test_healthcheck_unauthenticated_when_api_key_set() -> None:
    """Verify /health remains accessible without API key even when authentication is required."""
    settings = Settings.load(api_key="super-secret-key")
    app = create_app(settings=settings)
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


def test_api_key_auth_enforcement_on_agent_endpoints() -> None:
    """Verify /agent endpoints reject missing or invalid API keys when configured."""
    settings = Settings.load(api_key="expected-secret-key")
    app = create_app(settings=settings)

    with TestClient(app) as client:
        payload = {
            "message_id": "MSG-001",
            "sender_email": "alice@example.com",
            "subject": "Order query",
            "body_text": "Where is CMD-10001?",
            "received_at": datetime.now(timezone.utc).isoformat(),
        }

        # 1. Missing API Key
        resp_missing = client.post("/agent/process", json=payload)
        assert resp_missing.status_code == 401
        assert resp_missing.json()["error_code"] == "API_AUTHENTICATION_ERROR"

        # 2. Invalid API Key
        resp_invalid = client.post(
            "/agent/process",
            json=payload,
            headers={"X-API-Key": "wrong-key"},
        )
        assert resp_invalid.status_code == 401
        assert resp_invalid.json()["error_code"] == "API_AUTHENTICATION_ERROR"

        # 3. Valid API Key via X-API-Key header
        mock_svc = MagicMock()
        mock_svc.process_email = AsyncMock(return_value=_make_dummy_response())
        app.dependency_overrides[get_agent_service] = lambda: mock_svc

        resp_valid = client.post(
            "/agent/process",
            json=payload,
            headers={"X-API-Key": "expected-secret-key"},
        )
        assert resp_valid.status_code == 200

        # 4. Valid API Key via Authorization Bearer header
        resp_bearer = client.post(
            "/agent/process",
            json=payload,
            headers={"Authorization": "Bearer expected-secret-key"},
        )
        assert resp_bearer.status_code == 200


def test_process_email_nominal_flow() -> None:
    """Verify POST /agent/process calls AgentService and returns AgentFinalResponse."""
    app = create_app()
    mock_svc = MagicMock()
    dummy_resp = _make_dummy_response("SESS-CUSTOM-99")
    mock_svc.process_email = AsyncMock(return_value=dummy_resp)
    app.dependency_overrides[get_agent_service] = lambda: mock_svc

    with TestClient(app) as client:
        payload = {
            "message_id": "MSG-999",
            "sender_email": "bob@example.com",
            "subject": "Status of CMD-10001",
            "body_text": "Is order CMD-10001 shipped?",
            "received_at": datetime.now(timezone.utc).isoformat(),
        }
        resp = client.post(
            "/agent/process",
            json=payload,
            headers={
                "X-Tenant-ID": "tenant_custom",
                "X-Session-ID": "SESS-CUSTOM-99",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "SESS-CUSTOM-99"
        assert data["order_id"] == "CMD-10001"
        assert data["status_resolution"] == "RESOLVED_AUTOMATICALLY"

        mock_svc.process_email.assert_awaited_once()
        _, kwargs = mock_svc.process_email.call_args
        assert kwargs["tenant_id"] == "tenant_custom"
        assert kwargs["session_id"] == "SESS-CUSTOM-99"


def test_process_email_validation_error() -> None:
    """Verify POST /agent/process rejects malformed email syntax with 422."""
    app = create_app()
    with TestClient(app) as client:
        payload = {
            "message_id": "MSG-100",
            "sender_email": "not-an-email",
            "subject": "Hi",
            "body_text": "Hello",
            "received_at": datetime.now(timezone.utc).isoformat(),
        }
        resp = client.post("/agent/process", json=payload)
        assert resp.status_code == 422
        assert resp.json()["error_code"] == "VALIDATION_ERROR"


def test_get_session_success_and_not_found() -> None:
    """Verify GET /agent/sessions/{session_id} returns snapshot or 404 when absent."""
    app = create_app()
    mock_svc = MagicMock()

    dummy_snapshot = AgentSessionSnapshot(
        session_id="SESS-EXISTING",
        inbound_message=InboundEmailMessage(
            message_id="MSG-1",
            sender_email="alice@example.com",
            subject="Sub",
            body_text="Body",
            received_at=datetime.now(timezone.utc),
        ),
        current_state="COMPLETED",  # type: ignore[arg-type]
        tenant_id="tenant_x",
    )
    mock_svc.get_session = AsyncMock(
        side_effect=[dummy_snapshot, SessionNotFoundError("SESS-MISSING")]
    )
    app.dependency_overrides[get_agent_service] = lambda: mock_svc

    with TestClient(app) as client:
        # Existing session
        resp_found = client.get(
            "/agent/sessions/SESS-EXISTING",
            headers={"X-Tenant-ID": "tenant_x"},
        )
        assert resp_found.status_code == 200
        assert resp_found.json()["session_id"] == "SESS-EXISTING"

        # Missing session
        resp_missing = client.get(
            "/agent/sessions/SESS-MISSING",
            headers={"X-Tenant-ID": "tenant_x"},
        )
        assert resp_missing.status_code == 404
        assert resp_missing.json()["error_code"] == "SESSION_NOT_FOUND"
