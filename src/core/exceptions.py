"""Standardized domain exceptions and error taxonomy for 8_support_agent."""

__all__ = [
    "AppBaseError",
    "CircuitBreakerError",
    "ConfigurationError",
    "FSMStateError",
    "OrderNotFoundError",
    "SecurityAccessError",
    "SupportAgentBaseError",
    "ToolExecutionError",
]


class SupportAgentBaseError(Exception):
    """Base exception for all internal support agent domain errors."""

    def __init__(self, message: str, error_code: str = "INTERNAL_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code


# Universal architecture alias for SupportAgentBaseError
AppBaseError = SupportAgentBaseError


class ConfigurationError(SupportAgentBaseError):
    """Raised when application environment or settings are misconfigured."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="CONFIGURATION_ERROR")


class SecurityAccessError(SupportAgentBaseError):
    """Raised when an operation violates security, PII or authorization policies."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="SECURITY_UNAUTHORIZED_ACCESS")


class ToolExecutionError(SupportAgentBaseError):
    """Raised when an internal or external tool fails during execution."""

    def __init__(self, message: str, tool_name: str = "unknown") -> None:
        super().__init__(message, error_code="TOOL_EXECUTION_ERROR")
        self.tool_name = tool_name


class FSMStateError(SupportAgentBaseError):
    """Raised when an invalid state transition is requested in the agent lifecycle."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="FSM_STATE_INVALID")


class CircuitBreakerError(SupportAgentBaseError):
    """Raised when repeated external failures trip the circuit breaker."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="CIRCUIT_BREAKER_TRIPPED")


class OrderNotFoundError(SupportAgentBaseError):
    """Raised when a requested order cannot be found in the ERP database."""

    def __init__(self, order_id: str) -> None:
        super().__init__(f"Order '{order_id}' not found.", error_code="ORDER_NOT_FOUND")
        self.order_id = order_id
