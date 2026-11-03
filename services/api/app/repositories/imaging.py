"""Hospital-scoped SQLAlchemy queries for MRI metadata ownership."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.imaging import MriCase, MriJobRecord, MriJobState


class ImagingRepository:
    """Restrict every MRI metadata query by a server-derived hospital identifier."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_cases(self, hospital_id: UUID) -> list[MriCase]:
        return list(
            self._session.scalars(
                select(MriCase)
                .where(MriCase.hospital_id == hospital_id)
                .order_by(MriCase.created_at.desc())
            )
        )

    def add_job(self, job: MriJobRecord) -> None:
        self._session.add(job)

    def job_for_hospital(self, *, job_id: UUID, hospital_id: UUID) -> MriJobRecord | None:
        return self._session.scalar(
            select(MriJobRecord).where(
                MriJobRecord.id == job_id,
                MriJobRecord.hospital_id == hospital_id,
            )
        )

    def update_job(
        self,
        job: MriJobRecord,
        *,
        status: MriJobState,
        artifact_reference: str | None = None,
        model_sha256: str | None = None,
        model_source: str | None = None,
    ) -> None:
        job.status = status
        if artifact_reference is not None:
            job.artifact_reference = artifact_reference
        if model_sha256 is not None:
            job.model_sha256 = model_sha256
        if model_source is not None:
            job.model_source = model_source
