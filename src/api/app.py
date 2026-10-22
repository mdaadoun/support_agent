"""FastAPI application factory and middleware configuration."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.middleware import ErrorHandlingMiddleware, setup_exception_handlers
from api.routes import router
from core.config import Settings, get_settings
from observability.logger import get_logger, setup_logger

logger = get_logger(__name__)

__all__ = ["app", "create_app", "lifespan"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown events."""
    settings = get_settings()
    setup_logger(settings.log_level)
    logger.info("support_agent_startup", env=settings.support_agent_env)
    yield
    logger.info("support_agent_shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Instantiate and configure FastAPI application with middleware and routes."""
    app_settings = settings or get_settings()

    app = FastAPI(
        title="Customer Support Automation Agent",
        description="Autonomous Tier-1 agent with deterministic business rules",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(ErrorHandlingMiddleware)

    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: app_settings

    setup_exception_handlers(app)
    app.include_router(router)
    return app


app = create_app()
