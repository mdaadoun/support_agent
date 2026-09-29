"""Integration tests verifying tools runtime, argument validation, exception shielding, and idempotency caching."""

import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from clients.erp_client import MockERPClient
from persistence.cache import IdempotencyCache
from tools.registry import create_default_registry

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "mock_orders.json"


@pytest.mark.asyncio
async def test_tools_runtime_order_status_success_and_caching() -> None:
    """Validate order retrieval, result structure, and duplicate call caching."""
    erp_client = MockERPClient(data_path=DATA_PATH)
    cache = IdempotencyCache(ttl_seconds=900)
    registry = create_default_registry(erp_client=erp_client, cache=cache)

    session_id = "test_session_101"
    args = {"order_id": "CMD-10001", "customer_email": "alice@example.com"}

    with patch.object(
        erp_client, "get_order_by_id_async", wraps=erp_client.get_order_by_id_async
    ) as spy_lookup:
        # First execution (cache miss)
        res1 = await registry.execute(
            "get_order_details", session_id=session_id, **args
        )
        assert res1.success is True
        assert res1.tool_name == "get_order_details"
        assert res1.data is not None
        assert res1.data["order_id"] == "CMD-10001"
        assert spy_lookup.call_count == 1

        # Second execution with identical session and args (cache hit)
        res2 = await registry.execute(
            "get_order_details", session_id=session_id, **args
        )
        assert res2.success is True
        assert res2.data == res1.data
        assert spy_lookup.call_count == 1  # Not called again!


@pytest.mark.asyncio
async def test_tools_runtime_order_status_pii_and_missing_order_shielding() -> None:
    """Validate that unauthorized access and missing orders are shielded into error codes."""
    erp_client = MockERPClient(data_path=DATA_PATH)
    registry = create_default_registry(erp_client=erp_client)

    # Unauthorized access (mismatched email)
    res_pii = await registry.execute(
        "get_order_details",
        order_id="CMD-10001",
        customer_email="unauthorized@example.com",
    )
    assert res_pii.success is False
    assert res_pii.error_code == "SECURITY_UNAUTHORIZED_ACCESS"
    assert res_pii.data is None

    # Missing order ID
    res_missing = await registry.execute(
        "get_order_details",
        order_id="CMD-99999",
        customer_email="alice@example.com",
    )
    assert res_missing.success is False
    assert res_missing.error_code == "ORDER_NOT_FOUND"


@pytest.mark.asyncio
async def test_tools_runtime_refund_calculator_and_caching() -> None:
    """Validate statutory refund calculation and caching."""
    cache = IdempotencyCache(ttl_seconds=900)
    registry = create_default_registry(cache=cache)

    session_id = "test_session_202"
    delivery_date = datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc)
    request_date = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)

    args = {
        "delivery_date": delivery_date,
        "request_date": request_date,
        "item_prices_cents": [3000, 2000],
        "shipping_fee_cents": 500,
        "is_express": False,
        "delay_days": 0,
    }

    res1 = await registry.execute(
        "calculate_refund_eligibility", session_id=session_id, **args
    )
    assert res1.success is True
    assert res1.data is not None
    assert res1.data["is_eligible_for_return"] is True
    assert res1.data["refundable_items_total_cents"] == 5000

    # Cache hit on duplicate call
    res2 = await registry.execute(
        "calculate_refund_eligibility", session_id=session_id, **args
    )
    assert res2.success is True
    assert res2.data == res1.data


@pytest.mark.asyncio
async def test_tools_runtime_delay_calculator_and_caching() -> None:
    """Validate delay calculation and caching."""
    cache = IdempotencyCache(ttl_seconds=900)
    registry = create_default_registry(cache=cache)

    session_id = "test_session_303"
    est_date = datetime(2026, 9, 10, tzinfo=timezone.utc)
    ref_date = datetime(2026, 9, 17, tzinfo=timezone.utc)

    args = {
        "estimated_delivery_date": est_date,
        "reference_date": ref_date,
        "is_express": True,
        "shipping_fee_cents": 1500,
    }

    res1 = await registry.execute(
        "calculate_delivery_delay", session_id=session_id, **args
    )
    assert res1.success is True
    assert res1.data is not None
    assert res1.data["is_delayed"] is True
    assert res1.data["delay_days"] == 7
    assert res1.data["voucher_compensation_cents"] == 1500

    # Cache hit
    res2 = await registry.execute(
        "calculate_delivery_delay", session_id=session_id, **args
    )
    assert res2.success is True
    assert res2.data == res1.data


@pytest.mark.asyncio
async def test_tools_runtime_argument_validation_shielding() -> None:
    """Validate that invalid arguments are caught and shielded without crashing."""
    registry = create_default_registry()

    # Invalid email format for get_order_details (Pydantic ValidationError)
    res_bad_email = await registry.execute(
        "get_order_details",
        order_id="CMD-10001",
        customer_email="not-an-email",
    )
    assert res_bad_email.success is False
    assert res_bad_email.error_code == "INVALID_ARGUMENTS"

    # Invalid schema type for refund calculator (Pydantic ValidationError)
    now = datetime(2026, 9, 20, tzinfo=timezone.utc)
    res_bad_schema = await registry.execute(
        "calculate_refund_eligibility",
        delivery_date=now,
        request_date=now,
        item_prices_cents="not-a-list",
    )
    assert res_bad_schema.success is False
    assert res_bad_schema.error_code == "INVALID_ARGUMENTS"

    # Negative price for refund calculator (Domain BusinessRuleViolationError)
    res_bad_price = await registry.execute(
        "calculate_refund_eligibility",
        delivery_date=now,
        request_date=now,
        item_prices_cents=[-500],
    )
    assert res_bad_price.success is False
    assert res_bad_price.error_code == "INVALID_MONETARY_VALUE"


@pytest.mark.asyncio
async def test_tools_runtime_session_isolation_and_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validate session isolation and TTL eviction."""
    erp_client = MockERPClient(data_path=DATA_PATH)
    cache = IdempotencyCache(ttl_seconds=10)
    registry = create_default_registry(erp_client=erp_client, cache=cache)

    args = {"order_id": "CMD-10001", "customer_email": "alice@example.com"}

    current_time = 1000.0
    monkeypatch.setattr(time, "time", lambda: current_time)

    with patch.object(
        erp_client, "get_order_by_id_async", wraps=erp_client.get_order_by_id_async
    ) as spy_lookup:
        # Call with session 1
        await registry.execute("get_order_details", session_id="sess_1", **args)
        assert spy_lookup.call_count == 1

        # Call with session 2 (different session -> cache miss)
        await registry.execute("get_order_details", session_id="sess_2", **args)
        assert spy_lookup.call_count == 2

        # Duplicate call on session 1 before expiry -> cache hit
        await registry.execute("get_order_details", session_id="sess_1", **args)
        assert spy_lookup.call_count == 2

        # Advance past TTL
        current_time = 1015.0
        # Call on session 1 after expiry -> cache miss, re-executed
        await registry.execute("get_order_details", session_id="sess_1", **args)
        assert spy_lookup.call_count == 3
