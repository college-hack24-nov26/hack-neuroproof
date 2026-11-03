"""PostgreSQL metadata entities for hospital-owned MRI cases and jobs."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.auth import utc_now


class MriJobState(str, Enum):
    """Lifecycle state mirrored from the protected inference job metadata."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class MriCase(Base):
    """A de-identified hospital-owned MRI case metadata record."""

    __tablename__ = "mri_cases"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    hospital_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("hospitals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    case_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class MriJobRecord(Base):
    """Hospital ownership and safe artifact reference for one MRI inference job."""

    __tablename__ = "mri_jobs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    hospital_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("hospitals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    mri_case_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("mri_cases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[MriJobState] = mapped_column(
        SqlEnum(
            MriJobState,
            name="mri_job_state",
            values_callable=lambda states: [state.value for state in states],
        ),
        nullable=False,
        default=MriJobState.QUEUED,
    )
    artifact_reference: Mapped[str | None] = mapped_column(String(512), nullable=True)
    model_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_source: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="local",
        server_default="local",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
