"""Unit tests verifying pre-extraction intent classification and threat detection."""

from datetime import datetime, timezone

import pytest

from core.exceptions import BusinessRuleViolationError
from models.email import InboundEmailMessage
from models.enums import IntentEnum
from security.pre_extraction import (
    PreExtractionClassifier,
    classify_inbound_demand,
    detect_legal_threat_or_hostility,
    detect_out_of_scope,
)


def _create_email(
    subject: str, body: str, sender: str = "alice@example.com"
) -> InboundEmailMessage:
    """Helper creating test inbound email messages."""
    return InboundEmailMessage(
        message_id="MSG-TEST-001",
        sender_email=sender,
        subject=subject,
        body_text=body,
        received_at=datetime.now(timezone.utc),
    )


def test_nominal_order_status_classification() -> None:
    """Validate extraction of valid order ID and ORDER_STATUS intent."""
    msg = _create_email(
        "Order update", "Where is my package CMD-10001? Can I track it?"
    )
    demand = classify_inbound_demand(msg)
    assert demand.intent == IntentEnum.ORDER_STATUS
    assert demand.order_id == "CMD-10001"
    assert demand.customer_email == "alice@example.com"
    assert demand.is_legal_threat_or_aggressive is False
    assert demand.sub_queries == ()


def test_nominal_delivery_delay_classification() -> None:
    """Validate extraction of DELIVERY_DELAY intent for delayed orders."""
    msg = _create_email("Shipping delay", "My order CMD-10002 is late and delayed.")
    demand = classify_inbound_demand(msg)
    assert demand.intent == IntentEnum.DELIVERY_DELAY
    assert demand.order_id == "CMD-10002"
    assert demand.is_legal_threat_or_aggressive is False


def test_nominal_refund_request_classification() -> None:
    """Validate extraction of REFUND_REQUEST intent."""
    msg = _create_email(
        "Return Request", "I would like to return order CMD-10003 for a full refund."
    )
    demand = classify_inbound_demand(msg)
    assert demand.intent == IntentEnum.REFUND_REQUEST
    assert demand.order_id == "CMD-10003"


def test_nominal_order_information_classification() -> None:
    """Validate extraction of ORDER_INFORMATION intent for invoices."""
    msg = _create_email(
        "Invoice request", "Please send the invoice and warranty for CMD-10001."
    )
    demand = classify_inbound_demand(msg)
    assert demand.intent == IntentEnum.ORDER_INFORMATION
    assert demand.order_id == "CMD-10001"


def test_tc_05_missing_order_id_triggers_information_missing() -> None:
    """TC-05: Missing order ID in status inquiry flags INFORMATION_MISSING."""
    msg = _create_email("Package inquiry", "Where is my package? I am still waiting!")
    demand = classify_inbound_demand(msg)
    assert demand.intent == IntentEnum.INFORMATION_MISSING
    assert demand.order_id is None
    assert demand.is_legal_threat_or_aggressive is False


@pytest.mark.parametrize(
    "body",
    [
        "I want a full refund for my broken item.",
        "My delivery is 4 days late, what is going on?",
        "Could you send me my invoice please?",
    ],
)
def test_order_dependent_intents_without_order_id_flag_information_missing(
    body: str,
) -> None:
    """Validate any order-dependent inquiry lacking order ID yields INFORMATION_MISSING."""
    msg = _create_email("Help request", body)
    demand = classify_inbound_demand(msg)
    assert demand.intent == IntentEnum.INFORMATION_MISSING
    assert demand.order_id is None


def test_tc_11_hostile_legal_threat_triggers_out_of_scope() -> None:
    """TC-11: Legal threats and aggressive litigation trigger OUT_OF_SCOPE."""
    msg = _create_email(
        "Legal notice",
        "You scammers stole my money! My attorney will sue you in court and file a police report.",
    )
    demand = classify_inbound_demand(msg)
    assert demand.intent == IntentEnum.OUT_OF_SCOPE
    assert demand.is_legal_threat_or_aggressive is True
    assert demand.order_id is None


def test_legal_threat_with_order_id_preserves_order_and_flags_threat() -> None:
    """Validate legal threats with order reference flag hostility and OUT_OF_SCOPE."""
    msg = _create_email(
        "Dispute CMD-10001",
        "Refund order CMD-10001 now or my lawyer will file a lawsuit for fraud.",
    )
    demand = classify_inbound_demand(msg)
    assert demand.intent == IntentEnum.OUT_OF_SCOPE
    assert demand.is_legal_threat_or_aggressive is True
    assert demand.order_id == "CMD-10001"


@pytest.mark.parametrize(
    "text",
    [
        "I am applying for the backend developer job. Here is my resume.",
        "What is the weather in Paris today?",
        "Can you send me a Python script to scrape websites?",
    ],
)
def test_out_of_scope_inquiries(text: str) -> None:
    """Validate non-ecommerce queries are classified as OUT_OF_SCOPE."""
    msg = _create_email("General Inquiry", text)
    demand = classify_inbound_demand(msg)
    assert demand.intent == IntentEnum.OUT_OF_SCOPE
    assert demand.is_legal_threat_or_aggressive is False
    assert demand.order_id is None


def test_mixed_query_multiple_distinct_intents() -> None:
    """Validate inquiries with multiple intents yield MIXED_QUERY and sub_queries."""
    msg = _create_email(
        "Mixed inquiry",
        "Where is order CMD-10001? Also I want to return order CMD-10002 for a refund.",
    )
    demand = classify_inbound_demand(msg)
    assert demand.intent == IntentEnum.MIXED_QUERY
    assert demand.order_id == "CMD-10001"
    assert len(demand.sub_queries) >= 2


def test_mixed_query_without_order_ids_flags_information_missing() -> None:
    """Validate multi-intent query lacking order identifiers yields INFORMATION_MISSING."""
    msg = _create_email(
        "Two questions",
        "Where is my package? Also I want to return another item for a refund.",
    )
    demand = classify_inbound_demand(msg)
    assert demand.intent == IntentEnum.INFORMATION_MISSING
    assert demand.order_id is None


def test_order_id_in_subject_line() -> None:
    """Validate extraction of order ID located in subject header."""
    msg = _create_email("Question regarding CMD-10001", "When will my package arrive?")
    demand = classify_inbound_demand(msg)
    assert demand.order_id == "CMD-10001"
    assert demand.intent == IntentEnum.ORDER_STATUS


def test_case_normalization_and_email_sanitization() -> None:
    """Validate lowercase order ID uppercased and email normalized."""
    demand = PreExtractionClassifier.classify_text(
        text="Where is cmd-10001?",
        sender_email="  BOB.SMITH@DOMAIN.COM  ",
    )
    assert demand.order_id == "CMD-10001"
    assert demand.customer_email == "bob.smith@domain.com"
    assert demand.intent == IntentEnum.ORDER_STATUS


@pytest.mark.parametrize(
    ("text", "expected_intent"),
    [
        ("Où est mon colis CMD-10001 ?", IntentEnum.ORDER_STATUS),
        ("Ma commande CMD-10002 est en retard !", IntentEnum.DELIVERY_DELAY),
        ("Je souhaite un remboursement pour CMD-10003.", IntentEnum.REFUND_REQUEST),
        ("Veuillez m'envoyer la facture de CMD-10001.", IntentEnum.ORDER_INFORMATION),
    ],
)
def test_multilingual_french_support(text: str, expected_intent: IntentEnum) -> None:
    """Validate intent detection on French customer support inquiries."""
    msg = _create_email("Support", text)
    demand = classify_inbound_demand(msg)
    assert demand.intent == expected_intent
    assert demand.order_id is not None


def test_invalid_payload_types_raise_domain_error() -> None:
    """Validate non-string text or invalid emails raise BusinessRuleViolationError."""
    with pytest.raises(BusinessRuleViolationError):
        classify_inbound_demand(None)  # type: ignore[arg-type]

    with pytest.raises(BusinessRuleViolationError):
        PreExtractionClassifier.classify_text(123, "alice@example.com")  # type: ignore[arg-type]

    with pytest.raises(BusinessRuleViolationError):
        PreExtractionClassifier.classify_text("Where is CMD-10001", "not-an-email")


def test_threat_and_out_of_scope_helpers() -> None:
    """Validate helper predicates detect_legal_threat_or_hostility and detect_out_of_scope."""
    assert detect_legal_threat_or_hostility("My lawyer will contact you") is True
    assert detect_legal_threat_or_hostility("Plain inquiry about order") is False
    assert detect_out_of_scope("Here is my CV for job application") is True
    assert detect_out_of_scope("Where is my order CMD-10001") is False
