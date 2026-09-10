"""Unit tests verifying InboundEmailMessage and ExtractedDemand schemas."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from models.email import InboundEmailMessage
from models.enums import IntentEnum
from models.extraction import ExtractedDemand


def test_inbound_email_message_immutability() -> None:
    """Validate InboundEmailMessage is frozen and rejects mutation."""
    email = InboundEmailMessage(
        message_id="MSG-001",
        sender_email="customer@example.com",
        subject="Status check",
        body_text="Where is order CMD-10001?",
        received_at=datetime.now(timezone.utc),
    )
    with pytest.raises(ValidationError):
        email.subject = "Mutated Subject"


def test_inbound_email_rejects_extra_fields() -> None:
    """Validate extra fields are strictly forbidden."""
    with pytest.raises(ValidationError):
        InboundEmailMessage(
            message_id="MSG-001",
            sender_email="customer@example.com",
            subject="Status check",
            body_text="Where is order CMD-10001?",
            received_at=datetime.now(timezone.utc),
            injected_attribute="malicious_value",  # type: ignore[call-arg]
        )


@pytest.mark.parametrize(
    "invalid_email",
    ["notanemail", "user@", "@example.com", "user@.com"],
)
def test_inbound_email_syntax_validation(invalid_email: str) -> None:
    """Validate syntax validation on sender_email."""
    with pytest.raises(ValidationError):
        InboundEmailMessage(
            message_id="MSG-001",
            sender_email=invalid_email,
            subject="Status",
            body_text="Query",
            received_at=datetime.now(timezone.utc),
        )


@pytest.mark.parametrize(
    ("msg_id", "subject", "body"),
    [
        ("", "Subject", "Body"),
        ("MSG-001", "", "Body"),
        ("MSG-001", "Subject", ""),
    ],
)
def test_inbound_email_min_length_constraints(
    msg_id: str, subject: str, body: str
) -> None:
    """Validate non-empty string constraints on InboundEmailMessage."""
    with pytest.raises(ValidationError):
        InboundEmailMessage(
            message_id=msg_id,
            sender_email="customer@example.com",
            subject=subject,
            body_text=body,
            received_at=datetime.now(timezone.utc),
        )


@pytest.mark.parametrize(
    "valid_order_id",
    ["CMD-10001", "CMD-12345", "CMD-12345678", None],
)
def test_extracted_demand_valid_order_ids(valid_order_id: str | None) -> None:
    """Validate order_id regex pattern matches 5-8 digits and None."""
    demand = ExtractedDemand(
        intent=IntentEnum.ORDER_STATUS,
        order_id=valid_order_id,
        customer_email="customer@example.com",
    )
    assert demand.order_id == valid_order_id


@pytest.mark.parametrize(
    "invalid_order_id",
    ["CMD-1234", "CMD-123456789", "INVALID_FORMAT", "cmd-10001", "ORDER-10001"],
)
def test_extracted_demand_invalid_order_ids(invalid_order_id: str) -> None:
    """Validate order_id regex rejects non-conforming patterns."""
    with pytest.raises(ValidationError):
        ExtractedDemand(
            intent=IntentEnum.ORDER_STATUS,
            order_id=invalid_order_id,
            customer_email="customer@example.com",
        )


def test_extracted_demand_defaults_and_immutability() -> None:
    """Validate ExtractedDemand default values and frozen immutability."""
    demand = ExtractedDemand(
        intent=IntentEnum.REFUND_REQUEST,
        customer_email="customer@example.com",
    )
    assert demand.order_id is None
    assert demand.is_legal_threat_or_aggressive is False
    assert demand.sub_queries == ()

    with pytest.raises(ValidationError):
        demand.is_legal_threat_or_aggressive = True

    with pytest.raises(ValidationError):
        ExtractedDemand(
            intent=IntentEnum.ORDER_STATUS,
            customer_email="invalid_email",
        )


def test_extracted_demand_rejects_extra_fields() -> None:
    """Validate ExtractedDemand rejects extra attributes."""
    with pytest.raises(ValidationError):
        ExtractedDemand(
            intent=IntentEnum.ORDER_STATUS,
            customer_email="customer@example.com",
            extra_field="rejected",  # type: ignore[call-arg]
        )
