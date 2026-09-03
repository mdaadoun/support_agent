"""Domain enumerations for customer support operations."""

from enum import StrEnum


class OrderStatusEnum(StrEnum):
    """Lifecycle statuses of orders within ERP/carrier systems."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SHIPPED = "SHIPPED"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"
    DELAYED = "DELAYED"
    CANCELLED = "CANCELLED"
    RETURNED = "RETURNED"
    UNKNOWN = "UNKNOWN"


class IntentEnum(StrEnum):
    """Categorized intents detected in inbound customer inquiries."""

    ORDER_STATUS = "ORDER_STATUS"
    DELIVERY_DELAY = "DELIVERY_DELAY"
    REFUND_REQUEST = "REFUND_REQUEST"
    ORDER_INFORMATION = "ORDER_INFORMATION"
    MIXED_QUERY = "MIXED_QUERY"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    INFORMATION_MISSING = "INFORMATION_MISSING"


class RefundReasonCode(StrEnum):
    """Deterministic eligibility rationale for returns and vouchers."""

    WITHIN_LEGAL_TIMEFRAME = "WITHIN_LEGAL_TIMEFRAME"
    TIMEFRAME_EXCEEDED = "TIMEFRAME_EXCEEDED"
    NOT_DELIVERED_YET = "NOT_DELIVERED_YET"
    EXPRESS_DELAY_COMPENSATED = "EXPRESS_DELAY_COMPENSATED"


class ResolutionStatusEnum(StrEnum):
    """Resolution outcome of ticket processing."""

    RESOLVED_AUTOMATICALLY = "RESOLVED_AUTOMATICALLY"
    REQUIRES_HUMAN_REVIEW = "REQUIRES_HUMAN_REVIEW"
