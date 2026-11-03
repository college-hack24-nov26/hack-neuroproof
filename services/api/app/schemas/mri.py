"""Pydantic response schemas for MRI model metadata and segmentation jobs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.mri import ModelSource, MriJob


class CheckpointResponse(BaseModel):
    """Non-sensitive verified checkpoint metadata."""

    sha256: str
    size_bytes: int


class ModelInfoResponse(BaseModel):
    """Model architecture and runtime-integrity status."""

    model_source: ModelSource
    model_name: str
    modality_order: list[str]
    architecture: dict[str, Any]
    expected_parameter_count: int
    configured: bool
    integrity_status: str
    checkpoint: CheckpointResponse | None = None
    model_loaded: bool


class TumorStatisticsResponse(BaseModel):
    """Actual voxel and physical-volume values derived from a result mask."""

    tumor_voxels: int
    label_voxels: dict[str, int]
    voxel_volume_mm3: float
    tumor_volume_mm3: float
    tumor_volume_ml: float


class MriJobResponse(BaseModel):
    """Non-identifying lifecycle metadata for a segmentation request."""

    job_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None


class MriSegmentationResultResponse(BaseModel):
    """Viewer-ready metadata and URL for an authorized derived NIfTI artifact."""

    job_id: str
    status: str
    model_sha256: str
    model_source: ModelSource = "local"
    input_shape: list[int]
    segmentation_shape: list[int]
    labels: list[int]
    statistics: TumorStatisticsResponse
    inference_seconds: float
    artifact_download_url: str


def serialize_job(job: MriJob) -> MriJobResponse:
    """Map a domain job to the public lifecycle schema."""

    return MriJobResponse(
        job_id=job.job_id,
        status=job.status.value,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_code=job.error_code,
        error_message=job.error_message,
    )
