"""Integration tests verifying MockERPClient order retrieval, Tenacity retries, and error mapping."""

import json
from pathlib import Path

import pytest

from clients.erp_client import MockERPClient
from core.exceptions import (
    AppBaseError,
    CircuitBreakerError,
    ConfigurationError,
    OrderNotFoundError,
)

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "mock_orders.json"


def test_erp_client_nominal_sync_lookup() -> None:
    """Validate synchronous retrieval of delivered order metadata."""
    client = MockERPClient(data_path=DATA_PATH)
    order = client.get_order_by_id("CMD-10001")

    assert order["order_id"] == "CMD-10001"
    assert order["status"] == "DELIVERED"
    assert order["customer_email"] == "alice@example.com"
    assert order["carrier"] == "Colissimo"
    assert order["items_total_ttc_cents"] == 8990
    assert order["shipping_fee_ttc_cents"] == 490
    assert order["is_express"] is False
    assert len(order["items"]) == 1


def test_erp_client_delayed_order_lookup() -> None:
    """Validate retrieval of delayed express order metadata."""
    client = MockERPClient(data_path=DATA_PATH)
    order = client.get_order_by_id("CMD-10002")

    assert order["order_id"] == "CMD-10002"
    assert order["status"] == "DELAYED"
    assert order["customer_email"] == "bob@example.com"
    assert order["carrier"] == "Chronopost Express"
    assert order["is_express"] is True
    assert order["actual_delivery"] is None


@pytest.mark.asyncio
async def test_erp_client_nominal_async_lookup() -> None:
    """Validate asynchronous order retrieval."""
    client = MockERPClient(data_path=DATA_PATH)
    order = await client.get_order_by_id_async("CMD-10001")

    assert order["order_id"] == "CMD-10001"
    assert order["customer_email"] == "alice@example.com"


def test_erp_client_order_not_found_error_mapping() -> None:
    """Validate missing order ID maps cleanly to OrderNotFoundError without raw leak."""
    client = MockERPClient(data_path=DATA_PATH)

    with pytest.raises(OrderNotFoundError) as exc_info:
        client.get_order_by_id("CMD-99999")

    assert issubclass(OrderNotFoundError, AppBaseError)
    assert exc_info.value.order_id == "CMD-99999"
    assert exc_info.value.error_code == "ORDER_NOT_FOUND"


@pytest.mark.asyncio
async def test_erp_client_async_order_not_found() -> None:
    """Validate missing order ID in async lookup raises OrderNotFoundError."""
    client = MockERPClient(data_path=DATA_PATH)

    with pytest.raises(OrderNotFoundError) as exc_info:
        await client.get_order_by_id_async("CMD-88888")

    assert exc_info.value.order_id == "CMD-88888"


def test_erp_client_transient_retry_success() -> None:
    """Validate Tenacity retries transient failure (attempt 1 fails, attempt 2 succeeds)."""
    client = MockERPClient(data_path=DATA_PATH, max_attempts=2)
    client.simulate_transient_network_failure(failure_count=1)

    order = client.get_order_by_id("CMD-10001")
    assert order["order_id"] == "CMD-10001"
    assert client._transient_failures_remaining == 0


@pytest.mark.asyncio
async def test_erp_client_async_transient_retry_success() -> None:
    """Validate async Tenacity retry recovers on second attempt."""
    client = MockERPClient(data_path=DATA_PATH, max_attempts=2)
    client.simulate_transient_network_failure(failure_count=1)

    order = await client.get_order_by_id_async("CMD-10001")
    assert order["order_id"] == "CMD-10001"
    assert client._transient_failures_remaining == 0


def test_erp_client_retries_exhausted_trips_circuit_breaker() -> None:
    """Validate persistent network failures exhaust retries and trip CircuitBreakerError."""
    client = MockERPClient(data_path=DATA_PATH, max_attempts=2)
    client.simulate_transient_network_failure(failure_count=2)

    with pytest.raises(CircuitBreakerError) as exc_info:
        client.get_order_by_id("CMD-10001")

    assert issubclass(CircuitBreakerError, AppBaseError)
    assert exc_info.value.error_code == "CIRCUIT_BREAKER_TRIPPED"
    assert isinstance(exc_info.value.__cause__, ConnectionError)


@pytest.mark.asyncio
async def test_erp_client_async_retries_exhausted() -> None:
    """Validate async persistent failures raise CircuitBreakerError."""
    client = MockERPClient(data_path=DATA_PATH, max_attempts=2)
    client.simulate_transient_network_failure(failure_count=2)

    with pytest.raises(CircuitBreakerError) as exc_info:
        await client.get_order_by_id_async("CMD-10001")

    assert exc_info.value.error_code == "CIRCUIT_BREAKER_TRIPPED"


def test_erp_client_corrupt_data_file_raises_configuration_error(
    tmp_path: Path,
) -> None:
    """Validate malformed JSON data file is wrapped in ConfigurationError."""
    corrupt_file = tmp_path / "corrupt_orders.json"
    corrupt_file.write_text("{malformed: json", encoding="utf-8")

    client = MockERPClient(data_path=corrupt_file)
    with pytest.raises(ConfigurationError) as exc_info:
        client.get_order_by_id("CMD-10001")

    assert issubclass(ConfigurationError, AppBaseError)
    assert exc_info.value.error_code == "CONFIGURATION_ERROR"
    assert isinstance(exc_info.value.__cause__, json.JSONDecodeError)


def test_erp_client_missing_data_file_raises_order_not_found(
    tmp_path: Path,
) -> None:
    """Validate non-existent file path results in OrderNotFoundError without crashing."""
    missing_file = tmp_path / "non_existent.json"
    client = MockERPClient(data_path=missing_file)

    with pytest.raises(OrderNotFoundError) as exc_info:
        client.get_order_by_id("CMD-10001")

    assert exc_info.value.error_code == "ORDER_NOT_FOUND"


def test_erp_client_list_orders() -> None:
    """Validate list_orders returns all stored orders."""
    client = MockERPClient(data_path=DATA_PATH)
    orders = client.list_orders()

    assert len(orders) >= 6
    order_ids = {o["order_id"] for o in orders}
    assert "CMD-10001" in order_ids
    assert "CMD-10002" in order_ids
