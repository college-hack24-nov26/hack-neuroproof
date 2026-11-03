"""FastAPI application factory for the real MRI segmentation service."""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.v1 import health
from app.api.v1.router import router as api_v1_router
from app.core.config import Settings
from app.core.errors import ApiServiceError
from app.core.logging import configure_logging
from app.db.session import Database
from app.schemas.common import ErrorDetail, ErrorResponse
from app.services.mri_segmentation import MriSegmentationService

logger = logging.getLogger("cerebrachain.api")


def _request_id(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) else str(uuid4())


async def handle_service_error(request: Request, error: ApiServiceError) -> JSONResponse:
    """Serialize expected application errors without internal exception details."""

    payload = ErrorResponse(
        error=ErrorDetail(
            code=error.code,
            message=error.message,
            request_id=_request_id(request),
        )
    )
    return JSONResponse(status_code=error.status_code, content=payload.model_dump())


async def handle_request_validation_error(
    request: Request,
    _: RequestValidationError,
) -> JSONResponse:
    """Return a stable validation envelope without echoing multipart input content."""

    payload = ErrorResponse(
        error=ErrorDetail(
            code="request_validation_failed",
            message="Request content validation failed.",
            request_id=_request_id(request),
        )
    )
    return JSONResponse(status_code=422, content=payload.model_dump())


async def handle_unexpected_error(request: Request, _: Exception) -> JSONResponse:
    """Prevent unexpected exceptions from leaking paths, model details, or multipart data."""

    logger.exception("unhandled_api_error", extra={"request_id": _request_id(request)})
    payload = ErrorResponse(
        error=ErrorDetail(
            code="internal_error",
            message="An unexpected server error occurred.",
            request_id=_request_id(request),
        )
    )
    return JSONResponse(status_code=500, content=payload.model_dump())


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an API instance that can be configured directly in integration tests."""

    configure_logging()
    resolved_settings = settings or Settings.from_environment()
    app = FastAPI(
        title="ZKP-CerebraChain V2 MRI API",
        version="0.1.0",
        description=(
            "Research-only, hospital-scoped MRI segmentation API using a verified "
            "MONAI 3D U-Net checkpoint. It does not provide clinical diagnosis."
        ),
    )
    app.state.settings = resolved_settings
    app.state.database = (
        Database(resolved_settings.database_url)
        if resolved_settings.database_is_configured and resolved_settings.database_url is not None
        else None
    )
    app.state.mri_service = MriSegmentationService(resolved_settings)

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    app.add_exception_handler(ApiServiceError, handle_service_error)
    app.add_exception_handler(RequestValidationError, handle_request_validation_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
    app.include_router(health.router)
    app.include_router(api_v1_router)
    return app


app = create_app()
