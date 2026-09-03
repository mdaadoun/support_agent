"""PII access control and cross-authorization verification guard."""

from core.exceptions import SecurityAccessError
from observability.logger import get_logger

logger = get_logger(__name__)


class AccessControlGuard:
    """Enforces customer ownership verification to prevent unauthorized data access."""

    @staticmethod
    def verify_order_access(sender_email: str, order_customer_email: str) -> None:
        """Assert sender email matches the customer email recorded on the order.

        Raises:
            SecurityAccessError: If sender email does not match order owner.
        """
        normalized_sender = sender_email.strip().lower()
        normalized_owner = order_customer_email.strip().lower()

        if normalized_sender != normalized_owner:
            logger.warning(
                "security_access_denied",
                sender_email=normalized_sender,
                order_owner=normalized_owner,
            )
            raise SecurityAccessError(
                "Unauthorized access attempt: Sender email does not match order record."
            )
