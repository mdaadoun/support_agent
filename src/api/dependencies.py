"""FastAPI dependency injection providers for support agent ingress."""

from functools import lru_cache

from fastapi import Depends, Header, Security
from fastapi.security import APIKeyHeader

from agent.loop import ReActLoopEngine
from api.service import AgentService
from core.config import Settings, get_settings
from core.exceptions import APIAuthenticationError
from persistence.repository import AuditLogRepository
from persistence.session_store import SessionStateStore

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

__all__ = [
    "get_agent_engine",
    "get_agent_service",
    "get_audit_repository",
    "get_session_store",
    "get_tenant_id",
    "verify_api_key",
]


def get_tenant_id(
    x_tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
    settings: Settings = Depends(get_settings),
) -> str:
    """Resolve tenant identifier from request header or default configuration."""
    if x_tenant_id and x_tenant_id.strip():
        return x_tenant_id.strip()
    return settings.default_tenant_id


async def verify_api_key(
    x_api_key: str | None = Security(api_key_header),
    authorization: str | None = Header(None, alias="Authorization"),
    settings: Settings = Depends(get_settings),
) -> str | None:
    """Validate API key from X-API-Key or Authorization Bearer header against configured secret."""
    expected_key = settings.api_key
    if not expected_key:
        return None

    provided_key = x_api_key
    if not provided_key and authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            provided_key = parts[1]

    if not provided_key or provided_key != expected_key:
        raise APIAuthenticationError("Invalid or missing API key.")
    return provided_key


@lru_cache(maxsize=1)
def get_session_store() -> SessionStateStore:
    """Provide singleton SessionStateStore instance."""
    return SessionStateStore()


@lru_cache(maxsize=1)
def get_audit_repository() -> AuditLogRepository:
    """Provide singleton AuditLogRepository instance."""
    return AuditLogRepository()


def get_agent_engine() -> ReActLoopEngine:
    """Provide ReAct reasoning engine instance."""
    return ReActLoopEngine()


def get_agent_service(
    engine: ReActLoopEngine = Depends(get_agent_engine),
    session_store: SessionStateStore = Depends(get_session_store),
    audit_repo: AuditLogRepository = Depends(get_audit_repository),
) -> AgentService:
    """Assemble AgentService with injected dependencies."""
    return AgentService(
        engine=engine,
        session_store=session_store,
        audit_repo=audit_repo,
    )
