"""Standardized domain exceptions and error taxonomy for 8_support_agent."""

__all__ = [
    "APIAuthenticationError",
    "AppBaseError",
    "BusinessRuleViolationError",
    "CacheError",
    "CircuitBreakerError",
    "ConfigurationError",
    "FSMStateError",
    "LLMAuthenticationError",
    "LLMAuthorityViolationError",
    "LLMInferenceError",
    "LLMResponseValidationError",
    "LLMTimeoutError",
    "OrderNotFoundError",
    "PersistenceError",
    "SecurityAccessError",
    "SessionNotFoundError",
    "SupportAgentBaseError",
    "ToolExecutionError",
    "TracingError",
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


class APIAuthenticationError(SupportAgentBaseError):
    """Raised when REST API authentication fails or API key is invalid."""

    def __init__(self, message: str = "Invalid or missing API key.") -> None:
        super().__init__(message, error_code="API_AUTHENTICATION_ERROR")


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


class BusinessRuleViolationError(SupportAgentBaseError):
    """Raised when an operation violates domain business rules or boundary constraints."""

    def __init__(
        self, message: str, error_code: str = "BUSINESS_RULE_VIOLATION"
    ) -> None:
        super().__init__(message, error_code=error_code)


class LLMInferenceError(SupportAgentBaseError):
    """Raised when upstream LLM inference fails or exhausts retry attempts."""

    def __init__(self, message: str, error_code: str = "LLM_INFERENCE_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class LLMResponseValidationError(SupportAgentBaseError):
    """Raised when the LLM outputs malformed JSON or violates expected Pydantic schema."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="LLM_RESPONSE_VALIDATION_ERROR")


class LLMAuthenticationError(SupportAgentBaseError):
    """Raised when authentication with LLM provider fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="LLM_AUTHENTICATION_ERROR")


class LLMTimeoutError(SupportAgentBaseError):
    """Raised when an LLM inference call times out."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="LLM_TIMEOUT_ERROR")


class LLMAuthorityViolationError(SupportAgentBaseError):
    """Raised when the LLM attempts uncertified financial or operational commitments."""

    def __init__(self, message: str, violations: tuple[str, ...] = ()) -> None:
        super().__init__(message, error_code="LLM_AUTHORITY_VIOLATION")
        self.violations = violations


class PersistenceError(SupportAgentBaseError):
    """Raised when persistence or storage operations encounter failures."""

    def __init__(self, message: str, error_code: str = "PERSISTENCE_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class CacheError(PersistenceError):
    """Raised when Redis or in-memory caching operations fail."""

    def __init__(self, message: str, error_code: str = "CACHE_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class SessionNotFoundError(PersistenceError):
    """Raised when a requested session cannot be found in persistent storage."""

    def __init__(self, session_id: str) -> None:
        super().__init__(
            f"Session '{session_id}' not found.", error_code="SESSION_NOT_FOUND"
        )
        self.session_id = session_id


class TracingError(SupportAgentBaseError):
    """Raised when OpenInference or OpenTelemetry tracing operations fail."""

    def __init__(self, message: str, error_code: str = "TRACING_ERROR") -> None:
        super().__init__(message, error_code=error_code)
