"""Read-only model metadata endpoint."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.api.v1.dependencies import get_current_principal, get_mri_service
from app.schemas.mri import ModelInfoResponse
from app.services.authentication import Principal
from app.services.mri_segmentation import MriSegmentationService

router = APIRouter(prefix="/model", tags=["Model"])


@router.get("/info", response_model=ModelInfoResponse, summary="Inspect an authorized model selection")
def model_info(
    model_source: Literal["local", "global_fedavg_abc"] = Query("local"),
    service: MriSegmentationService = Depends(get_mri_service),
    _: Principal = Depends(get_current_principal),
) -> ModelInfoResponse:
    """Return selected-model integrity metadata without exposing its path."""

    return ModelInfoResponse.model_validate(service.model_info(model_source))
