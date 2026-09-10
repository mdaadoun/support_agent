"""Tests asserting schema immutability, extra field rejection, and boundary constraints."""

import pytest
from pydantic import ValidationError

from models.base import BaseDTO
from models.enums import (
    IntentEnum,
    OrderStatusEnum,
    RefundReasonCode,
    ResolutionStatusEnum,
)


class DummyDTO(BaseDTO):
    """Test concrete model derived from BaseDTO."""

    field_a: str
    field_b: int = 42


class TicketRecord(BaseDTO):
    """Concrete DTO validating enum integration within BaseDTO."""

    intent: IntentEnum
    status: OrderStatusEnum
    resolution: ResolutionStatusEnum
    reason: RefundReasonCode | None = None


def test_base_dto_immutability() -> None:
    """Validate that BaseDTO enforces frozen immutability."""
    dto = DummyDTO(field_a="immutable_value")
    with pytest.raises(ValidationError):
        dto.field_a = "mutated_value"


def test_base_dto_forbids_extra_attributes() -> None:
    """Validate that BaseDTO rejects undeclared extra attributes."""
    with pytest.raises(ValidationError):
        DummyDTO(field_a="test", unexpected_field="rejected")  # type: ignore[call-arg]


def test_base_dto_hashability() -> None:
    """Validate that frozen BaseDTO instances are hashable for sets and mappings."""
    dto1 = DummyDTO(field_a="alpha", field_b=1)
    dto2 = DummyDTO(field_a="alpha", field_b=1)
    dto3 = DummyDTO(field_a="beta", field_b=2)

    dto_set = {dto1, dto2, dto3}
    assert len(dto_set) == 2
    assert dto1 in dto_set


@pytest.mark.parametrize(
    ("enum_cls", "expected"),
    [
        (
            OrderStatusEnum,
            {
                "PENDING",
                "PROCESSING",
                "SHIPPED",
                "IN_TRANSIT",
                "DELIVERED",
                "DELAYED",
                "CANCELLED",
                "RETURNED",
                "UNKNOWN",
            },
        ),
        (
            IntentEnum,
            {
                "ORDER_STATUS",
                "DELIVERY_DELAY",
                "REFUND_REQUEST",
                "ORDER_INFORMATION",
                "MIXED_QUERY",
                "OUT_OF_SCOPE",
                "INFORMATION_MISSING",
            },
        ),
        (
            RefundReasonCode,
            {
                "WITHIN_LEGAL_TIMEFRAME",
                "TIMEFRAME_EXCEEDED",
                "NOT_DELIVERED_YET",
                "EXPRESS_DELAY_COMPENSATED",
            },
        ),
        (
            ResolutionStatusEnum,
            {"RESOLVED_AUTOMATICALLY", "REQUIRES_HUMAN_REVIEW"},
        ),
    ],
)
def test_business_enums_members(
    enum_cls: type[
        OrderStatusEnum | IntentEnum | RefundReasonCode | ResolutionStatusEnum
    ],
    expected: set[str],
) -> None:
    """Validate all enum members, values, and string subclass behaviors."""
    assert {e.value for e in enum_cls} == expected
    for val in expected:
        member = enum_cls(val)
        assert isinstance(member, str)
        assert member == val
    with pytest.raises(ValueError):
        enum_cls("INVALID_ENUM_VALUE")


def test_base_dto_enum_validation() -> None:
    """Validate that BaseDTO validates enum fields and rejects invalid values."""
    record = TicketRecord(
        intent=IntentEnum.REFUND_REQUEST,
        status=OrderStatusEnum.RETURNED,
        resolution=ResolutionStatusEnum.RESOLVED_AUTOMATICALLY,
        reason=RefundReasonCode.WITHIN_LEGAL_TIMEFRAME,
    )
    assert record.intent == "REFUND_REQUEST"
    assert record.reason == RefundReasonCode.WITHIN_LEGAL_TIMEFRAME

    with pytest.raises(ValidationError):
        TicketRecord(
            intent="UNKNOWN_INTENT",  # type: ignore[arg-type]
            status=OrderStatusEnum.DELIVERED,
            resolution=ResolutionStatusEnum.RESOLVED_AUTOMATICALLY,
        )
