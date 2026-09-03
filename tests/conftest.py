"""Shared pytest fixtures and test configuration."""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from clients.erp_client import MockERPClient
from models.email import InboundEmailMessage


@pytest.fixture
def test_client() -> TestClient:
    """Provide FastAPI test client."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def mock_erp_client() -> MockERPClient:
    """Provide mock ERP client querying fixture data."""
    fixture_path = Path(__file__).parent / "fixtures" / "mock_orders.json"
    return MockERPClient(data_path=fixture_path)


@pytest.fixture
def sample_inbound_email() -> InboundEmailMessage:
    """Provide a validated sample customer inbound email message."""
    return InboundEmailMessage(
        message_id="MSG-TEST-001",
        sender_email="alice@example.com",
        subject="Where is my package CMD-10001?",
        body_text="Hello, I placed order CMD-10001 and wonder when it will arrive.",
        received_at=datetime.now(timezone.utc),
    )
