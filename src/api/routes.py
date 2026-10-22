"""HTTP route handlers for support agent ingestion and monitoring."""

from fastapi import APIRouter, Depends, Header, status
from pydantic import ConfigDict

from api.dependencies import get_agent_service, get_tenant_id, verify_api_key
from api.service import AgentService
from models.base import BaseDTO
from models.email import InboundEmailMessage
from models.response import AgentFinalResponse
from models.session import AgentSessionSnapshot

router = APIRouter()

__all__ = ["HealthResponse", "router"]


class HealthResponse(BaseDTO):
    """Healthcheck payload response model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    version: str


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Healthcheck probe",
)
async def healthcheck() -> HealthResponse:
    """Return service liveness status and version metadata."""
    return HealthResponse(status="healthy", version="0.1.0")


@router.post(
    "/agent/process",
    response_model=AgentFinalResponse,
    status_code=status.HTTP_200_OK,
    summary="Process inbound customer email",
    dependencies=[Depends(verify_api_key)],
)
async def process_email(
    message: InboundEmailMessage,
    x_session_id: str | None = Header(None, alias="X-Session-ID"),
    tenant_id: str = Depends(get_tenant_id),
    service: AgentService = Depends(get_agent_service),
) -> AgentFinalResponse:
    """Ingest customer email, execute autonomous reasoning loop, and return certified response."""
    return await service.process_email(
        message=message,
        tenant_id=tenant_id,
        session_id=x_session_id,
    )


@router.get(
    "/agent/sessions/{session_id}",
    response_model=AgentSessionSnapshot,
    status_code=status.HTTP_200_OK,
    summary="Retrieve session state snapshot",
    dependencies=[Depends(verify_api_key)],
)
async def get_session(
    session_id: str,
    tenant_id: str = Depends(get_tenant_id),
    service: AgentService = Depends(get_agent_service),
) -> AgentSessionSnapshot:
    """Retrieve immutable snapshot of active or completed agent session."""
    return await service.get_session(
        session_id=session_id,
        tenant_id=tenant_id,
    )
