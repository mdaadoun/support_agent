"""Error handling middleware and standardized exception handlers."""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from core.exceptions import (
    APIAuthenticationError,
    BusinessRuleViolationError,
    CircuitBreakerError,
    ConfigurationError,
    FSMStateError,
    OrderNotFoundError,
    SecurityAccessError,
    SessionNotFoundError,
    SupportAgentBaseError,
    ToolExecutionError,
)
from observability.logger import get_logger

logger = get_logger(__name__)

__all__ = [
    "ERROR_STATUS_MAP",
    "ErrorHandlingMiddleware",
    "build_error_response",
    "setup_exception_handlers",
]

ERROR_STATUS_MAP: dict[type[SupportAgentBaseError], int] = {
    SessionNotFoundError: status.HTTP_404_NOT_FOUND,
    OrderNotFoundError: status.HTTP_404_NOT_FOUND,
    SecurityAccessError: status.HTTP_403_FORBIDDEN,
    APIAuthenticationError: status.HTTP_401_UNAUTHORIZED,
    FSMStateError: status.HTTP_409_CONFLICT,
    BusinessRuleViolationError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    CircuitBreakerError: status.HTTP_503_SERVICE_UNAVAILABLE,
    ToolExecutionError: status.HTTP_502_BAD_GATEWAY,
    ConfigurationError: status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def build_error_response(
    status_code: int,
    error_code: str,
    message: str,
    details: Any | None = None,
) -> JSONResponse:
    """Construct standardized error response payload."""
    content: dict[str, Any] = {
        "error_code": error_code,
        "message": message,
    }
    if details is not None:
        content["details"] = details
    return JSONResponse(status_code=status_code, content=content)


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """ASGI middleware shielding against unhandled runtime exceptions."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            return await call_next(request)
        except SupportAgentBaseError as exc:
            status_code = ERROR_STATUS_MAP.get(
                type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            logger.warning(
                "middleware_domain_error",
                error_code=exc.error_code,
                path=request.url.path,
                message=exc.message,
            )
            return build_error_response(
                status_code=status_code,
                error_code=exc.error_code,
                message=exc.message,
            )
        except Exception as exc:
            logger.error(
                "middleware_unhandled_exception",
                path=request.url.path,
                error=str(exc),
            )
            return build_error_response(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                error_code="INTERNAL_SERVER_ERROR",
                message="An unexpected internal server error occurred.",
            )


def setup_exception_handlers(app: FastAPI) -> None:
    """Register custom exception handlers for domain and framework errors."""

    @app.exception_handler(SupportAgentBaseError)
    async def domain_exception_handler(
        request: Request, exc: SupportAgentBaseError
    ) -> JSONResponse:
        status_code = ERROR_STATUS_MAP.get(
            type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR
        )
        logger.warning(
            "api_domain_exception",
            error_code=exc.error_code,
            path=request.url.path,
            message=exc.message,
        )
        return build_error_response(
            status_code=status_code,
            error_code=exc.error_code,
            message=exc.message,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return build_error_response(
            status_code=exc.status_code,
            error_code="HTTP_ERROR",
            message=str(exc.detail),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.warning(
            "api_validation_error",
            path=request.url.path,
            errors=exc.errors(),
        )
        return build_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="VALIDATION_ERROR",
            message="Request schema validation failed.",
            details=exc.errors(),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.error(
            "api_generic_unhandled_exception",
            path=request.url.path,
            error=str(exc),
        )
        return build_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="INTERNAL_SERVER_ERROR",
            message="An unexpected internal server error occurred.",
        )
