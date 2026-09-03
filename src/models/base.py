"""Base model specifications ensuring immutability and schema rigidity."""

from pydantic import BaseModel, ConfigDict


class BaseDTO(BaseModel):
    """Immutable base data transfer object rejecting extra attributes."""

    model_config = ConfigDict(frozen=True, extra="forbid")
