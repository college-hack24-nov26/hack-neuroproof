"""Shared response schemas and domain-error serialization."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """A stable safe error shape for all documented API failures."""

    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    """Envelope used by documented error responses."""

    error: ErrorDetail


class HealthResponse(BaseModel):
    """Liveness and configuration readiness without secret disclosure."""

    status: Literal["ok", "degraded"]
    service: str
    model_configured: bool
    result_storage_configured: bool
