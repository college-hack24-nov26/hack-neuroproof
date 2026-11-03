"""Liveness endpoint for the MRI API."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1.dependencies import get_mri_service
from app.schemas.common import HealthResponse
from app.services.mri_segmentation import MriSegmentationService

router = APIRouter(tags=["Operations"])


@router.get("/health", response_model=HealthResponse, summary="Report MRI API liveness")
def health(service: MriSegmentationService = Depends(get_mri_service)) -> HealthResponse:
    """Return liveness and configuration readiness without revealing protected paths."""

    return HealthResponse.model_validate(service.health_status())
