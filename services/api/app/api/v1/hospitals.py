"""Authenticated hospital-scoped administration endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies import (
    get_authentication_service,
    get_current_principal,
    get_database_session,
    require_hospital_admin,
)
from app.schemas.auth import ActorResponse, DoctorCreateRequest
from app.schemas.hospitals import (
    DoctorListResponse,
    HospitalResponse,
    MriCaseListResponse,
)
from app.services.authentication import AuthenticationService, Principal
from app.services.hospitals import HospitalService

router = APIRouter(prefix="/hospitals/me", tags=["Hospitals"])


def get_hospital_service(
    session: Session = Depends(get_database_session),
) -> HospitalService:
    """Construct hospital read services with the request transaction."""

    return HospitalService(session)


@router.get("", response_model=HospitalResponse, summary="Read the active hospital profile")
def current_hospital(
    principal: Principal = Depends(get_current_principal),
    service: HospitalService = Depends(get_hospital_service),
) -> HospitalResponse:
    """Return only the hospital selected by the authenticated membership."""

    return service.active_hospital(principal)


@router.get("/doctors", response_model=DoctorListResponse, summary="List active-hospital doctors")
def list_doctors(
    principal: Principal = Depends(require_hospital_admin),
    service: HospitalService = Depends(get_hospital_service),
) -> DoctorListResponse:
    """List doctors only for a hospital administrator's own hospital."""

    return service.doctors(principal)


@router.post(
    "/doctors",
    response_model=ActorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a doctor in the active hospital",
)
def create_doctor(
    request: DoctorCreateRequest,
    principal: Principal = Depends(require_hospital_admin),
    service: AuthenticationService = Depends(get_authentication_service),
) -> ActorResponse:
    """Create a doctor without accepting a client-provided hospital identifier."""

    return service.create_doctor(principal, request)


@router.get("/mri-cases", response_model=MriCaseListResponse, summary="List active-hospital MRI cases")
def list_mri_cases(
    principal: Principal = Depends(get_current_principal),
    service: HospitalService = Depends(get_hospital_service),
) -> MriCaseListResponse:
    """List only cases with a matching server-derived hospital identifier."""

    return service.mri_cases(principal)
