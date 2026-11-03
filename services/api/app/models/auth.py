"""PostgreSQL entities for hospital identity and membership authorization."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp for persistence defaults."""

    return datetime.now(timezone.utc)


class HospitalRole(str, Enum):
    """Roles granted through a hospital membership."""

    HOSPITAL_ADMIN = "hospital_admin"
    DOCTOR = "doctor"


class Hospital(Base):
    """A hospital tenancy boundary; no patient data is stored on this entity."""

    __tablename__ = "hospitals"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    memberships: Mapped[list[HospitalMembership]] = relationship(
        back_populates="hospital",
        cascade="all, delete-orphan",
    )


class User(Base):
    """A user identity with a salted password hash and no role outside membership."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    memberships: Mapped[list[HospitalMembership]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class HospitalMembership(Base):
    """Explicit role assignment between one user and one hospital."""

    __tablename__ = "hospital_memberships"
    __table_args__ = (UniqueConstraint("hospital_id", "user_id", name="uq_membership_hospital_user"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    hospital_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("hospitals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[HospitalRole] = mapped_column(
        SqlEnum(
            HospitalRole,
            name="hospital_role",
            values_callable=lambda roles: [role.value for role in roles],
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    hospital: Mapped[Hospital] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")
