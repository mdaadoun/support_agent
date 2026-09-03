"""Pre-extraction intent and entity schemas."""

from pydantic import EmailStr, Field

from models.base import BaseDTO
from models.enums import IntentEnum


class ExtractedDemand(BaseDTO):
    """Structured demand extracted from inbound customer email."""

    intent: IntentEnum
    order_id: str | None = Field(default=None, pattern=r"^CMD-[0-9]{5,8}$")
    customer_email: EmailStr
    is_legal_threat_or_aggressive: bool = False
    sub_queries: tuple[str, ...] = Field(default_factory=tuple)
