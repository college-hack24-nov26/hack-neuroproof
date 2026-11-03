"""Persistent domain models for MRI segmentation jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Final, Literal
from uuid import UUID, uuid4

from cerebrachain_ml.statistics import TumorStatistics


class MriJobStatus(str, Enum):
    """The lifecycle states exposed by a synchronous, serialized inference service."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


ModelSource = Literal["local", "global_fedavg_abc"]
MODEL_SOURCES: Final[frozenset[str]] = frozenset({"local", "global_fedavg_abc"})


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


@dataclass
class MriJob:
    """Non-identifying metadata for an MRI segmentation request."""

    job_id: str
    status: MriJobStatus
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    model_sha256: str | None = None
    model_source: ModelSource = "local"
    input_shape: tuple[int, int, int, int, int] | None = None
    segmentation_shape: tuple[int, int, int] | None = None
    labels: list[int] = field(default_factory=list)
    statistics: TumorStatistics | None = None
    inference_seconds: float | None = None
    error_code: str | None = None
    error_message: str | None = None

    @classmethod
    def create(cls, job_id: str | None = None) -> "MriJob":
        """Create a new non-identifying queued job."""

        now = utc_now()
        if job_id is not None:
            job_id = str(UUID(job_id))
        return cls(
            job_id=job_id or str(uuid4()),
            status=MriJobStatus.QUEUED,
            created_at=now,
            updated_at=now,
        )

    def touch(self) -> None:
        """Update job modification time after a state transition."""

        self.updated_at = utc_now()

    def to_record(self) -> dict[str, Any]:
        """Serialize metadata without MRI contents or original upload names."""

        statistics = None
        if self.statistics is not None:
            statistics = {
                "tumor_voxels": self.statistics.tumor_voxels,
                "label_voxels": self.statistics.label_voxels,
                "voxel_volume_mm3": self.statistics.voxel_volume_mm3,
                "tumor_volume_mm3": self.statistics.tumor_volume_mm3,
                "tumor_volume_ml": self.statistics.tumor_volume_ml,
            }

        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "model_sha256": self.model_sha256,
            "model_source": self.model_source,
            "input_shape": list(self.input_shape) if self.input_shape else None,
            "segmentation_shape": list(self.segmentation_shape) if self.segmentation_shape else None,
            "labels": self.labels,
            "statistics": statistics,
            "inference_seconds": self.inference_seconds,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "MriJob":
        """Rebuild a job from repository-owned JSON metadata."""

        statistics_record = record.get("statistics")
        statistics = None
        if statistics_record is not None:
            statistics = TumorStatistics(
                tumor_voxels=int(statistics_record["tumor_voxels"]),
                label_voxels={
                    str(label): int(count)
                    for label, count in statistics_record["label_voxels"].items()
                },
                voxel_volume_mm3=float(statistics_record["voxel_volume_mm3"]),
                tumor_volume_mm3=float(statistics_record["tumor_volume_mm3"]),
                tumor_volume_ml=float(statistics_record["tumor_volume_ml"]),
            )

        model_source = record.get("model_source", "local")
        if model_source not in MODEL_SOURCES:
            raise ValueError("MRI job metadata has an unsupported model source.")

        input_shape = record.get("input_shape")
        segmentation_shape = record.get("segmentation_shape")
        return cls(
            job_id=str(record["job_id"]),
            status=MriJobStatus(record["status"]),
            created_at=datetime.fromisoformat(record["created_at"]),
            updated_at=datetime.fromisoformat(record["updated_at"]),
            started_at=(
                datetime.fromisoformat(record["started_at"])
                if record.get("started_at")
                else None
            ),
            completed_at=(
                datetime.fromisoformat(record["completed_at"])
                if record.get("completed_at")
                else None
            ),
            model_sha256=record.get("model_sha256"),
            model_source=model_source,
            input_shape=tuple(int(value) for value in input_shape) if input_shape else None,
            segmentation_shape=(
                tuple(int(value) for value in segmentation_shape)
                if segmentation_shape
                else None
            ),
            labels=[int(value) for value in record.get("labels", [])],
            statistics=statistics,
            inference_seconds=(
                float(record["inference_seconds"])
                if record.get("inference_seconds") is not None
                else None
            ),
            error_code=record.get("error_code"),
            error_message=record.get("error_message"),
        )
