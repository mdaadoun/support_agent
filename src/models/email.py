"""Ingestion schemas for inbound customer email messages."""

from datetime import datetime

from pydantic import EmailStr, Field

from models.base import BaseDTO


class InboundEmailMessage(BaseDTO):
    """Raw validated inbound email payload before agent processing."""

    message_id: str = Field(min_length=1)
    sender_email: EmailStr
    subject: str = Field(min_length=1)
    body_text: str = Field(min_length=1)
    received_at: datetime
