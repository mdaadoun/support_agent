"""Unit tests verifying PII access control and cross-authorization guard."""

from typing import Any

import pytest
from pydantic import BaseModel, EmailStr

from core.exceptions import BusinessRuleViolationError, SecurityAccessError
from models.tools import ToolExecutionResult
from security.access_control import AccessControlGuard


class MockOrderModel(BaseModel):
    """Simple test model representing an order record."""

    order_id: str
    customer_email: EmailStr


def test_normalize_email_valid_and_case_insensitive() -> None:
    """Validate email normalization strips whitespace and converts to lowercase."""
    raw = "   Alice.Smith+Tag@Domain.CO.UK   "
    normalized = AccessControlGuard.normalize_email(raw)
    assert normalized == "alice.smith+tag@domain.co.uk"


def test_normalize_email_invalid_types_raise_domain_error() -> None:
    """Validate non-string or empty inputs raise BusinessRuleViolationError."""
    with pytest.raises(BusinessRuleViolationError) as exc_info:
        AccessControlGuard.normalize_email(None)  # type: ignore[arg-type]
    assert exc_info.value.error_code == "INVALID_PAYLOAD_TYPE"

    with pytest.raises(BusinessRuleViolationError) as exc_info2:
        AccessControlGuard.normalize_email("   ")
    assert exc_info2.value.error_code == "INVALID_PAYLOAD_TYPE"

    with pytest.raises(BusinessRuleViolationError) as exc_info3:
        AccessControlGuard.normalize_email("invalid-email-address")
    assert exc_info3.value.error_code == "INVALID_EMAIL_SYNTAX"


def test_is_authorized_predicate() -> None:
    """Validate is_authorized returns boolean without raising exceptions."""
    assert (
        AccessControlGuard.is_authorized("alice@example.com", "alice@example.com")
        is True
    )
    assert (
        AccessControlGuard.is_authorized("  Alice@Example.com  ", "ALICE@EXAMPLE.COM")
        is True
    )

    # Mismatch
    assert (
        AccessControlGuard.is_authorized("mallory@evil.com", "alice@example.com")
        is False
    )

    # Invalid input
    assert (
        AccessControlGuard.is_authorized("not-an-email", "alice@example.com") is False
    )
    assert AccessControlGuard.is_authorized(None, "alice@example.com") is False  # type: ignore[arg-type]


def test_verify_order_access_matching_passes() -> None:
    """Validate matching sender email passes access verification."""
    AccessControlGuard.verify_order_access(
        sender_email="customer@example.com",
        order_customer_email="customer@example.com",
    )
    # Case and space variations
    AccessControlGuard.verify_order_access(
        sender_email="  CUSTOMER@example.com  ",
        order_customer_email="customer@EXAMPLE.COM",
    )


def test_verify_order_access_mismatch_fails_closed_without_metadata_leakage() -> None:
    """Validate unauthorized inquiry raises SecurityAccessError without leaking order owner PII."""
    sender = "attacker@evil.com"
    owner = "victim.private@example.com"

    with pytest.raises(SecurityAccessError) as exc_info:
        AccessControlGuard.verify_order_access(sender, owner)

    err = exc_info.value
    assert err.error_code == "SECURITY_UNAUTHORIZED_ACCESS"
    # Ensure zero metadata leakage: victim's email must NOT appear in the exception message
    assert owner not in err.message
    assert "Unauthorized access attempt" in err.message


def test_verify_order_access_invalid_parameters_raise_domain_error() -> None:
    """Validate malformed parameters raise BusinessRuleViolationError."""
    with pytest.raises(BusinessRuleViolationError) as exc_info:
        AccessControlGuard.verify_order_access("valid@example.com", 12345)  # type: ignore[arg-type]
    assert exc_info.value.error_code == "INVALID_PAYLOAD_TYPE"

    with pytest.raises(BusinessRuleViolationError) as exc_info2:
        AccessControlGuard.verify_order_access("bad-sender", "valid@example.com")
    assert exc_info2.value.error_code == "INVALID_EMAIL_SYNTAX"


def test_verify_order_record_access_dict() -> None:
    """Validate authorization against raw dictionary order records."""
    order_dict = {
        "order_id": "CMD-10001",
        "customer_email": "alice@example.com",
        "status": "DELIVERED",
    }

    # Authorized
    AccessControlGuard.verify_order_record_access("alice@example.com", order_dict)

    # Unauthorized
    with pytest.raises(SecurityAccessError) as sec_exc:
        AccessControlGuard.verify_order_record_access("bob@example.com", order_dict)
    assert sec_exc.value.error_code == "SECURITY_UNAUTHORIZED_ACCESS"

    # Missing email field
    corrupt_dict = {"order_id": "CMD-10001"}
    with pytest.raises(BusinessRuleViolationError) as rule_exc:
        AccessControlGuard.verify_order_record_access("alice@example.com", corrupt_dict)
    assert rule_exc.value.error_code == "MISSING_CUSTOMER_EMAIL"


def test_verify_order_record_access_model() -> None:
    """Validate authorization against Pydantic model order records."""
    order_model = MockOrderModel(
        order_id="CMD-10001", customer_email="alice@example.com"
    )

    # Authorized
    AccessControlGuard.verify_order_record_access("alice@example.com", order_model)

    # Unauthorized
    with pytest.raises(SecurityAccessError) as sec_exc:
        AccessControlGuard.verify_order_record_access("bob@example.com", order_model)
    assert sec_exc.value.error_code == "SECURITY_UNAUTHORIZED_ACCESS"

    # Invalid object type
    invalid_record: Any = ["invalid_type"]
    with pytest.raises(BusinessRuleViolationError) as rule_exc:
        AccessControlGuard.verify_order_record_access(
            "alice@example.com", invalid_record
        )
    assert rule_exc.value.error_code == "INVALID_PAYLOAD_TYPE"


def test_shield_unauthorized_access() -> None:
    """Validate tool shielding returns ToolExecutionResult on mismatch and None on match."""
    # Authorized
    assert (
        AccessControlGuard.shield_unauthorized_access(
            tool_name="get_order_details",
            sender_email="alice@example.com",
            order_customer_email="alice@example.com",
        )
        is None
    )

    # Unauthorized
    result = AccessControlGuard.shield_unauthorized_access(
        tool_name="get_order_details",
        sender_email="mallory@evil.com",
        order_customer_email="alice@example.com",
    )
    assert isinstance(result, ToolExecutionResult)
    assert result.success is False
    assert result.tool_name == "get_order_details"
    assert result.error_code == "SECURITY_UNAUTHORIZED_ACCESS"
    assert "alice@example.com" not in (result.error_message or "")
