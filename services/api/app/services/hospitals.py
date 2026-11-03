"""Hospital-scoped read services with no caller-controlled tenancy input."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import ResourceNotFoundError
from app.repositories.auth import AuthRepository
from app.repositories.imaging import ImagingRepository
from app.schemas.hospitals import (
    DoctorListResponse,
    DoctorResponse,
    HospitalResponse,
    MriCaseListResponse,
    MriCaseResponse,
)
from app.services.authentication import Principal


class HospitalService:
    """Produce safe hospital dashboard data from the authenticated hospital scope."""

    def __init__(self, session: Session) -> None:
        self._auth_repository = AuthRepository(session)
        self._imaging_repository = ImagingRepository(session)

    def active_hospital(self, principal: Principal) -> HospitalResponse:
        """Return the authenticated member's hospital without accepting an ID from clients."""

        hospital = self._auth_repository.hospital_by_id(principal.hospital_id)
        if hospital is None:
            raise ResourceNotFoundError()
        return HospitalResponse(
            id=hospital.id,
            name=hospital.name,
            slug=hospital.slug,
            role=principal.role.value,
            created_at=hospital.created_at,
        )

    def doctors(self, principal: Principal) -> DoctorListResponse:
        """List doctors constrained to the principal's hospital only."""

        doctors = self._auth_repository.doctors_for_hospital(principal.hospital_id)
        return DoctorListResponse(
            doctors=[
                DoctorResponse(
                    user_id=doctor.id,
                    full_name=doctor.full_name,
                    email=doctor.email,
                    created_at=doctor.created_at,
                )
                for doctor in doctors
            ]
        )

    def mri_cases(self, principal: Principal) -> MriCaseListResponse:
        """List only de-identified cases belonging to the active hospital."""

        cases = self._imaging_repository.list_cases(principal.hospital_id)
        return MriCaseListResponse(
            cases=[
                MriCaseResponse(
                    id=case.id,
                    case_reference=case.case_reference,
                    created_at=case.created_at,
                )
                for case in cases
            ]
        )
