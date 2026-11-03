"""Database queries for identity and membership, isolated from API routes."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auth import Hospital, HospitalMembership, HospitalRole, User


class AuthRepository:
    """Perform identity and membership queries within a supplied transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def user_by_email(self, email: str) -> User | None:
        return self._session.scalar(select(User).where(User.email == email))

    def hospital_by_slug(self, slug: str) -> Hospital | None:
        return self._session.scalar(select(Hospital).where(Hospital.slug == slug))

    def hospital_by_id(self, hospital_id: UUID) -> Hospital | None:
        return self._session.get(Hospital, hospital_id)

    def list_hospitals(self) -> list[Hospital]:
        """List registered hospitals for an administrator-only federation view."""

        return list(
            self._session.scalars(
                select(Hospital).order_by(Hospital.created_at, Hospital.slug)
            )
        )

    def membership(self, *, user_id: UUID, hospital_id: UUID) -> HospitalMembership | None:
        return self._session.scalar(
            select(HospitalMembership).where(
                HospitalMembership.user_id == user_id,
                HospitalMembership.hospital_id == hospital_id,
            )
        )

    def membership_for_login(self, *, user_id: UUID, hospital_slug: str) -> HospitalMembership | None:
        return self._session.scalar(
            select(HospitalMembership)
            .join(Hospital)
            .where(
                HospitalMembership.user_id == user_id,
                Hospital.slug == hospital_slug,
            )
        )

    def doctors_for_hospital(self, hospital_id: UUID) -> list[User]:
        return list(
            self._session.scalars(
                select(User)
                .join(HospitalMembership)
                .where(
                    HospitalMembership.hospital_id == hospital_id,
                    HospitalMembership.role == HospitalRole.DOCTOR,
                )
                .order_by(User.full_name, User.email)
            )
        )

    def add_hospital(self, hospital: Hospital) -> None:
        self._session.add(hospital)

    def add_user(self, user: User) -> None:
        self._session.add(user)

    def add_membership(self, membership: HospitalMembership) -> None:
        self._session.add(membership)
