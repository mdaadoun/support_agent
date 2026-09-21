"""Unit tests verifying domain exception shielding hierarchy and taxonomy."""

import pytest

from core.exceptions import (
    AppBaseError,
    BusinessRuleViolationError,
    CircuitBreakerError,
    ConfigurationError,
    FSMStateError,
    OrderNotFoundError,
    SecurityAccessError,
    SupportAgentBaseError,
    ToolExecutionError,
)


def test_support_agent_base_error_attributes() -> None:
    """Validate root domain exception attributes, inheritance, and string representation."""
    err = SupportAgentBaseError("Generic fault")
    assert isinstance(err, Exception)
    assert err.message == "Generic fault"
    assert err.error_code == "INTERNAL_ERROR"
    assert str(err) == "Generic fault"

    custom_err = SupportAgentBaseError("Custom fault", error_code="CUSTOM_CODE")
    assert custom_err.error_code == "CUSTOM_CODE"


def test_app_base_error_alias() -> None:
    """Validate AppBaseError alias points directly to SupportAgentBaseError."""
    assert AppBaseError is SupportAgentBaseError


def test_configuration_error() -> None:
    """Validate ConfigurationError attributes and hierarchy."""
    err = ConfigurationError("Missing REDIS_URL")
    assert isinstance(err, SupportAgentBaseError)
    assert isinstance(err, AppBaseError)
    assert err.error_code == "CONFIGURATION_ERROR"
    assert err.message == "Missing REDIS_URL"


def test_security_access_error() -> None:
    """Validate SecurityAccessError attributes and hierarchy."""
    err = SecurityAccessError("PII email mismatch")
    assert isinstance(err, SupportAgentBaseError)
    assert isinstance(err, AppBaseError)
    assert err.error_code == "SECURITY_UNAUTHORIZED_ACCESS"
    assert err.message == "PII email mismatch"


def test_tool_execution_error() -> None:
    """Validate ToolExecutionError attributes, default and custom tool_name."""
    default_err = ToolExecutionError("Tool failed")
    assert default_err.tool_name == "unknown"
    assert default_err.error_code == "TOOL_EXECUTION_ERROR"

    custom_err = ToolExecutionError(
        "Order lookup timed out", tool_name="get_order_details"
    )
    assert custom_err.tool_name == "get_order_details"
    assert custom_err.error_code == "TOOL_EXECUTION_ERROR"
    assert custom_err.message == "Order lookup timed out"


def test_fsm_state_error() -> None:
    """Validate FSMStateError attributes and hierarchy."""
    err = FSMStateError("Invalid transition: RECEIVED -> COMPLETED")
    assert isinstance(err, SupportAgentBaseError)
    assert err.error_code == "FSM_STATE_INVALID"
    assert "Invalid transition" in str(err)


def test_circuit_breaker_error() -> None:
    """Validate CircuitBreakerError attributes and hierarchy."""
    err = CircuitBreakerError("ERP client tripped after 3 consecutive failures")
    assert isinstance(err, SupportAgentBaseError)
    assert err.error_code == "CIRCUIT_BREAKER_TRIPPED"


def test_order_not_found_error() -> None:
    """Validate OrderNotFoundError attributes, formatting, and order_id."""
    err = OrderNotFoundError("CMD-88888")
    assert isinstance(err, SupportAgentBaseError)
    assert err.order_id == "CMD-88888"
    assert err.error_code == "ORDER_NOT_FOUND"
    assert err.message == "Order 'CMD-88888' not found."
    assert str(err) == "Order 'CMD-88888' not found."


def test_business_rule_violation_error() -> None:
    """Validate BusinessRuleViolationError attributes and inheritance."""
    err = BusinessRuleViolationError("Item price negative")
    assert isinstance(err, SupportAgentBaseError)
    assert isinstance(err, AppBaseError)
    assert err.error_code == "BUSINESS_RULE_VIOLATION"
    assert err.message == "Item price negative"

    custom_err = BusinessRuleViolationError("Invalid", error_code="INVALID_VAL")
    assert custom_err.error_code == "INVALID_VAL"


@pytest.mark.parametrize(
    "sub_exception",
    [
        ConfigurationError("Config fault"),
        SecurityAccessError("Security fault"),
        ToolExecutionError("Tool fault", tool_name="calculator"),
        FSMStateError("State fault"),
        CircuitBreakerError("Circuit breaker fault"),
        OrderNotFoundError("CMD-12345"),
        BusinessRuleViolationError("Rule fault"),
    ],
)
def test_all_exceptions_caught_by_app_base_error(
    sub_exception: SupportAgentBaseError,
) -> None:
    """Validate that every domain sub-exception is catchable via AppBaseError."""
    try:
        raise sub_exception
    except AppBaseError as caught:
        assert caught is sub_exception
        assert isinstance(caught.error_code, str)
        assert len(caught.error_code) > 0


def test_third_party_exception_shielding_pattern() -> None:
    """Validate wrapping third-party infrastructure exceptions with cause chaining."""
    raw_error = ConnectionResetError("Connection reset by peer")
    try:
        try:
            raise raw_error
        except ConnectionError as exc:
            raise CircuitBreakerError("Upstream ERP connection dropped") from exc
    except AppBaseError as domain_err:
        assert isinstance(domain_err, CircuitBreakerError)
        assert domain_err.__cause__ is raw_error
        assert domain_err.error_code == "CIRCUIT_BREAKER_TRIPPED"
