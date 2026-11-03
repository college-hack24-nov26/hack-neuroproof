"""Persist and enforce hospital ownership for filesystem-backed MRI jobs."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import ResourceNotFoundError
from app.models.imaging import MriJobRecord, MriJobState
from app.repositories.imaging import ImagingRepository
from app.services.authentication import Principal


class MriOwnershipService:
    """Bind each MRI job identifier to its requesting hospital before inference begins."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._repository = ImagingRepository(session)

    def reserve(self, principal: Principal) -> MriJobRecord:
        """Commit hospital ownership before protected MRI bytes are persisted."""

        record = MriJobRecord(
            hospital_id=principal.hospital_id,
            requested_by_user_id=principal.user_id,
            status=MriJobState.QUEUED,
        )
        self._repository.add_job(record)
        self._session.commit()
        return record

    def require_owned(self, job_id: str, principal: Principal) -> MriJobRecord:
        """Find a job only within the current hospital, hiding cross-hospital existence."""

        try:
            normalized_id = UUID(job_id)
        except ValueError as exc:
            raise ResourceNotFoundError("MRI segmentation job was not found.") from exc
        record = self._repository.job_for_hospital(
            job_id=normalized_id,
            hospital_id=principal.hospital_id,
        )
        if record is None:
            raise ResourceNotFoundError("MRI segmentation job was not found.")
        return record

    def mark_running(self, record: MriJobRecord) -> None:
        """Record that the protected inference workflow has started."""

        self._repository.update_job(record, status=MriJobState.RUNNING)
        self._session.commit()

    def mark_completed(
        self,
        record: MriJobRecord,
        *,
        model_sha256: str | None,
        model_source: str,
    ) -> None:
        """Store only a safe derived artifact reference after successful inference."""

        self._repository.update_job(
            record,
            status=MriJobState.COMPLETED,
            artifact_reference="segmentation.nii.gz",
            model_sha256=model_sha256,
            model_source=model_source,
        )
        record.completed_at = datetime.now(timezone.utc)
        self._session.commit()

    def mark_failed(self, record: MriJobRecord) -> None:
        """Persist a safe failure state without storing exception details."""

        self._repository.update_job(record, status=MriJobState.FAILED)
        record.completed_at = datetime.now(timezone.utc)
        self._session.commit()
