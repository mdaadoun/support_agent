"""HTTP route handlers for support agent ingestion and monitoring."""

from fastapi import APIRouter, status
from pydantic import BaseModel

from models.email import InboundEmailMessage

router = APIRouter()


class HealthResponse(BaseModel):
    """Healthcheck payload response model."""

    status: str
    version: str


@router.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def healthcheck() -> HealthResponse:
    """Return service liveness status and version metadata."""
    return HealthResponse(status="healthy", version="0.1.0")


@router.post("/agent/process", status_code=status.HTTP_202_ACCEPTED)
async def process_email(message: InboundEmailMessage) -> dict[str, str]:
    """Ingest customer email and schedule agent reasoning cycle."""
    return {
        "status": "ACCEPTED",
        "message_id": message.message_id,
        "note": "Agent execution pipeline ready for Phase 8 integration.",
    }
