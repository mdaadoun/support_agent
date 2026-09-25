"""PII access control and cross-authorization verification guard."""

from typing import Any

from pydantic import BaseModel

from core.exceptions import BusinessRuleViolationError, SecurityAccessError
from models.tools import ToolExecutionResult
from observability.logger import get_logger
from security.sanitizer import is_valid_email

__all__ = ["AccessControlGuard"]

logger = get_logger(__name__)


class AccessControlGuard:
    """Enforces customer ownership verification to prevent unauthorized PII data access."""

    @staticmethod
    def normalize_email(email: str) -> str:
        """Strip whitespace, lowercase, and validate email syntax.

        Args:
            email: Candidate email string.

        Returns:
            Normalized lowercase email address.

        Raises:
            BusinessRuleViolationError: If input is not a non-empty string or has invalid format.
        """
        if not isinstance(email, str):
            raise BusinessRuleViolationError(
                f"Expected email string, got {type(email).__name__}",
                error_code="INVALID_PAYLOAD_TYPE",
            )
        cleaned = email.strip().lower()
        if not cleaned:
            raise BusinessRuleViolationError(
                "Email address cannot be empty.",
                error_code="INVALID_PAYLOAD_TYPE",
            )
        if not is_valid_email(cleaned):
            raise BusinessRuleViolationError(
                f"Malformed email address syntax: '{cleaned}'",
                error_code="INVALID_EMAIL_SYNTAX",
            )
        return cleaned

    @classmethod
    def is_authorized(cls, sender_email: str, order_customer_email: str) -> bool:
        """Safely evaluate if sender email matches order owner without raising exceptions.

        Args:
            sender_email: Authenticated sender address from inbound message.
            order_customer_email: Registered customer email on order record.

        Returns:
            True if normalized addresses strictly match, False otherwise.
        """
        try:
            norm_sender = cls.normalize_email(sender_email)
            norm_owner = cls.normalize_email(order_customer_email)
            return norm_sender == norm_owner
        except Exception:
            return False

    @classmethod
    def verify_order_access(cls, sender_email: str, order_customer_email: str) -> None:
        """Assert sender email strictly matches the customer email recorded on the order.

        Fails closed on mismatch and logs a security event without leaking PII
        or order details in the raised exception message.

        Args:
            sender_email: Authenticated sender address from inbound message.
            order_customer_email: Customer email associated with order record.

        Raises:
            BusinessRuleViolationError: If either email parameter is invalid.
            SecurityAccessError: If sender email does not match order record owner.
        """
        normalized_sender = cls.normalize_email(sender_email)
        normalized_owner = cls.normalize_email(order_customer_email)

        if normalized_sender != normalized_owner:
            logger.warning(
                "security_access_denied",
                sender_email=normalized_sender,
                order_owner=normalized_owner,
            )
            # Fail closed: Do NOT disclose order owner email in the exception message
            raise SecurityAccessError(
                "Unauthorized access attempt: Sender email does not match order record."
            )

    @classmethod
    def verify_order_record_access(
        cls, sender_email: str, order_record: dict[str, Any] | BaseModel
    ) -> None:
        """Verify sender authorization against an order dictionary or domain model.

        Args:
            sender_email: Authenticated sender address.
            order_record: Dictionary or Pydantic model containing 'customer_email'.

        Raises:
            BusinessRuleViolationError: If order record lacks customer_email.
            SecurityAccessError: If sender email does not match order record owner.
        """
        if isinstance(order_record, dict):
            owner_email = order_record.get("customer_email")
        elif isinstance(order_record, BaseModel):
            owner_email = getattr(order_record, "customer_email", None)
        else:
            raise BusinessRuleViolationError(
                f"Expected dict or BaseModel order record, got {type(order_record).__name__}",
                error_code="INVALID_PAYLOAD_TYPE",
            )

        if not isinstance(owner_email, str):
            raise BusinessRuleViolationError(
                "Order record is missing a valid 'customer_email' attribute.",
                error_code="MISSING_CUSTOMER_EMAIL",
            )

        cls.verify_order_access(sender_email, owner_email)

    @classmethod
    def shield_unauthorized_access(
        cls,
        tool_name: str,
        sender_email: str,
        order_customer_email: str,
    ) -> ToolExecutionResult | None:
        """Shield tool invocations by returning a structured failure result on mismatch.

        Args:
            tool_name: Name of tool requesting authorization check.
            sender_email: Authenticated sender address.
            order_customer_email: Target order customer email.

        Returns:
            None if authorized; ToolExecutionResult with error code on mismatch.
        """
        if not cls.is_authorized(sender_email, order_customer_email):
            logger.warning(
                "security_tool_access_shielded",
                tool_name=tool_name,
                sender_email=sender_email,
            )
            return ToolExecutionResult(
                success=False,
                tool_name=tool_name,
                error_code="SECURITY_UNAUTHORIZED_ACCESS",
                error_message="Unauthorized access attempt: Sender email does not match order record.",
            )
        return None
