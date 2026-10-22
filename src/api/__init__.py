"""API presentation layer containing routes, dependencies, and application factory."""

from api.app import app, create_app
from api.dependencies import (
    get_agent_engine,
    get_agent_service,
    get_audit_repository,
    get_session_store,
    get_tenant_id,
    verify_api_key,
)
from api.middleware import ErrorHandlingMiddleware, setup_exception_handlers
from api.routes import HealthResponse, router
from api.service import AgentService

__all__ = [
    "AgentService",
    "ErrorHandlingMiddleware",
    "HealthResponse",
    "app",
    "create_app",
    "get_agent_engine",
    "get_agent_service",
    "get_audit_repository",
    "get_session_store",
    "get_tenant_id",
    "router",
    "setup_exception_handlers",
    "verify_api_key",
]
