"""Nominal domain scenarios TC-01 through TC-06 for qualification matrix."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.enums import IntentEnum, ResolutionStatusEnum
from tests.agent.scenario_helpers import (
    build_scenario_service,
    llm_text_response,
    llm_tool_call_response,
    make_email,
    make_synthesis,
    order_tool_call,
)


@pytest.mark.asyncio
async def test_tc01_nominal_delivered_order_status() -> None:
    """TC-01: Nominal delivered order status query with 1 tool call."""
    mock_llm = MagicMock()
    service, _ = build_scenario_service(mock_llm)
    email = make_email(
        "alice@example.com", "CMD-10001 status", "Where is my package CMD-10001?"
    )
    t1 = order_tool_call("c1", "CMD-10001", "alice@example.com")
    mock_llm.generate_with_tools = AsyncMock(
        side_effect=[t1, llm_text_response("Verified")]
    )
    mock_llm.generate_structured = AsyncMock(
        return_value=make_synthesis(
            IntentEnum.ORDER_STATUS,
            "Re: Status",
            "Delivered August 24 via Colissimo.",
            "CMD-10001",
        )
    )
    resp = await service.process_email(email, tenant_id="t_tc")
    snap = await service.get_session(resp.session_id, "t_tc")
    assert resp.status_resolution == ResolutionStatusEnum.RESOLVED_AUTOMATICALLY
    assert len(snap.tool_traces) == 1
    assert snap.tool_traces[0].result.data["status"] == "DELIVERED"  # type: ignore[index]


@pytest.mark.asyncio
async def test_tc02_chained_delivery_delay_computation() -> None:
    """TC-02: Chained dependency inspecting delayed order and computing delay days."""
    mock_llm = MagicMock()
    service, _ = build_scenario_service(mock_llm)
    email = make_email(
        "bob@example.com", "CMD-10002 delay", "Is order CMD-10002 delayed?"
    )
    t1 = order_tool_call("c1", "CMD-10002", "bob@example.com")
    t2 = llm_tool_call_response(
        [
            (
                "c2",
                "calculate_delivery_delay",
                {
                    "estimated_delivery_date": "2026-08-17T12:00:00Z",
                    "reference_date": "2026-08-25T12:00:00Z",
                },
            )
        ]
    )
    mock_llm.generate_with_tools = AsyncMock(
        side_effect=[t1, t2, llm_text_response("Done")]
    )
    mock_llm.generate_structured = AsyncMock(
        return_value=make_synthesis(
            IntentEnum.DELIVERY_DELAY,
            "Re: Delay",
            "Order is delayed by 8 days.",
            "CMD-10002",
        )
    )
    resp = await service.process_email(email, tenant_id="t_tc")
    snap = await service.get_session(resp.session_id, "t_tc")
    assert resp.status_resolution == ResolutionStatusEnum.RESOLVED_AUTOMATICALLY
    assert len(snap.tool_traces) == 2
    assert snap.tool_traces[1].result.data["delay_days"] == 8  # type: ignore[index]


@pytest.mark.asyncio
async def test_tc03_eligible_statutory_return_window() -> None:
    """TC-03: Return request within 14-day statutory cooling-off window."""
    mock_llm = MagicMock()
    service, _ = build_scenario_service(mock_llm)
    email = make_email(
        "grace@example.com",
        "Return CMD-10007",
        "Return order CMD-10007",
        received_at=datetime(2026, 9, 9, 10, 0, tzinfo=timezone.utc),
    )
    t1 = order_tool_call("c1", "CMD-10007", "grace@example.com")
    t2 = llm_tool_call_response(
        [
            (
                "c2",
                "calculate_refund_eligibility",
                {
                    "delivery_date": "2026-09-01T14:20:00Z",
                    "request_date": "2026-09-09T10:00:00Z",
                    "item_prices_cents": [4500],
                    "shipping_fee_cents": 490,
                    "is_express": False,
                    "delay_days": 0,
                },
            )
        ]
    )
    mock_llm.generate_with_tools = AsyncMock(
        side_effect=[t1, t2, llm_text_response("Done")]
    )
    mock_llm.generate_structured = AsyncMock(
        return_value=make_synthesis(
            IntentEnum.REFUND_REQUEST,
            "Re: Return",
            "Eligible. Refund €45.00.",
            "CMD-10007",
        )
    )
    resp = await service.process_email(email, tenant_id="t_tc")
    snap = await service.get_session(resp.session_id, "t_tc")
    assert snap.tool_traces[1].result.data["is_eligible_for_return"] is True  # type: ignore[index]
    assert snap.tool_traces[1].result.data["refundable_items_total_cents"] == 4500  # type: ignore[index]


@pytest.mark.asyncio
async def test_tc04_expired_return_statutory_refusal() -> None:
    """TC-04: Return request exceeding 14-day statutory period polite denial."""
    mock_llm = MagicMock()
    service, _ = build_scenario_service(mock_llm)
    email = make_email(
        "charlie@example.com",
        "Return CMD-10003",
        "Return CMD-10003",
        received_at=datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc),
    )
    t1 = order_tool_call("c1", "CMD-10003", "charlie@example.com")
    t2 = llm_tool_call_response(
        [
            (
                "c2",
                "calculate_refund_eligibility",
                {
                    "delivery_date": "2026-07-14T11:45:00Z",
                    "request_date": "2026-08-08T10:00:00Z",
                    "item_prices_cents": [5900],
                    "shipping_fee_cents": 500,
                    "is_express": False,
                    "delay_days": 0,
                },
            )
        ]
    )
    mock_llm.generate_with_tools = AsyncMock(
        side_effect=[t1, t2, llm_text_response("Done")]
    )
    mock_llm.generate_structured = AsyncMock(
        return_value=make_synthesis(
            IntentEnum.REFUND_REQUEST,
            "Re: Return",
            "Expired statutory window.",
            "CMD-10003",
        )
    )
    resp = await service.process_email(email, tenant_id="t_tc")
    snap = await service.get_session(resp.session_id, "t_tc")
    assert snap.tool_traces[1].result.data["is_eligible_for_return"] is False  # type: ignore[index]
    assert snap.tool_traces[1].result.data["reason_code"] == "TIMEFRAME_EXCEEDED"  # type: ignore[index]


@pytest.mark.asyncio
async def test_tc05_missing_order_id_clarification() -> None:
    """TC-05: Inquiry missing order ID triggers clarification with 0 tool calls."""
    mock_llm = MagicMock()
    service, _ = build_scenario_service(mock_llm)
    email = make_email(
        "alice@example.com", "Missing", "Where is my package? I am waiting!"
    )
    mock_llm.generate_with_tools = AsyncMock(
        return_value=llm_text_response("Ask for ID")
    )
    mock_llm.generate_structured = AsyncMock(
        return_value=make_synthesis(
            IntentEnum.INFORMATION_MISSING, "Re: Missing", "Please provide order ID."
        )
    )
    resp = await service.process_email(email, tenant_id="t_tc")
    snap = await service.get_session(resp.session_id, "t_tc")
    assert resp.intent == IntentEnum.INFORMATION_MISSING
    assert resp.order_id is None
    assert len(snap.tool_traces) == 0


@pytest.mark.asyncio
async def test_tc06_unknown_order_not_found_handling() -> None:
    """TC-06: Valid syntax ID missing in DB returns ORDER_NOT_FOUND without hallucination."""
    mock_llm = MagicMock()
    service, _ = build_scenario_service(mock_llm)
    email = make_email(
        "alice@example.com", "Order status CMD-99999", "Where is my order CMD-99999?"
    )
    t1 = order_tool_call("c1", "CMD-99999", "alice@example.com")
    mock_llm.generate_with_tools = AsyncMock(
        side_effect=[t1, llm_text_response("Not found")]
    )
    mock_llm.generate_structured = AsyncMock(
        return_value=make_synthesis(
            IntentEnum.ORDER_STATUS, "Re: Query", "Order CMD-99999 not found."
        )
    )
    resp = await service.process_email(email, tenant_id="t_tc")
    snap = await service.get_session(resp.session_id, "t_tc")
    assert snap.tool_traces[0].result.error_code == "ORDER_NOT_FOUND"
    assert resp.order_id == "CMD-99999"
