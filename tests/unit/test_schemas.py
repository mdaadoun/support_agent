"""Tests asserting schema immutability, extra field rejection, and boundary constraints."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from models.email import InboundEmailMessage
from models.enums import IntentEnum, OrderStatusEnum
from models.extraction import ExtractedDemand
from models.tools import DeliveryDelayResult, OrderDetailsResult


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


def test_extracted_demand_order_id_regex() -> None:
    """Validate order_id regex pattern enforcement."""
    valid_demand = ExtractedDemand(
        intent=IntentEnum.ORDER_STATUS,
        order_id="CMD-10001",
        customer_email="customer@example.com",
    )
    assert valid_demand.order_id == "CMD-10001"

    with pytest.raises(ValidationError):
        ExtractedDemand(
            intent=IntentEnum.ORDER_STATUS,
            order_id="INVALID_CMD_FORMAT",
            customer_email="customer@example.com",
        )


def test_order_details_result_validation() -> None:
    """Validate numeric and enum constraints on OrderDetailsResult."""
    result = OrderDetailsResult(
        order_id="CMD-10001",
        status=OrderStatusEnum.DELIVERED,
        carrier="Colissimo",
        tracking_number="COL-001",
        ordered_at=datetime.now(timezone.utc),
        estimated_delivery=datetime.now(timezone.utc),
        items_total_ttc_cents=2990,
        shipping_fee_ttc_cents=490,
        is_express=False,
    )
    assert result.status == OrderStatusEnum.DELIVERED
    assert result.items_total_ttc_cents == 2990


def test_delivery_delay_result() -> None:
    """Validate DeliveryDelayResult fields."""
    res = DeliveryDelayResult(delay_days=3, is_delayed=True)
    assert res.delay_days == 3
    assert res.is_delayed is True
