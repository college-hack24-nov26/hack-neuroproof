"""Hospital-scoped response schemas for the future React client."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class HospitalResponse(BaseModel):
    """Safe hospital profile for the caller's active membership."""

    id: UUID
    name: str
    slug: str
    role: str
    created_at: datetime


class DoctorResponse(BaseModel):
    """Doctor metadata available only to a hospital administrator."""

    user_id: UUID
    full_name: str
    email: str
    created_at: datetime


class DoctorListResponse(BaseModel):
    """Hospital-scoped doctor list with no cross-tenant identifiers."""

    doctors: list[DoctorResponse]


class MriCaseResponse(BaseModel):
    """De-identified MRI case metadata scoped to the active hospital."""

    id: UUID
    case_reference: str
    created_at: datetime


class MriCaseListResponse(BaseModel):
    """Response wrapper for the active hospital's MRI cases."""

    cases: list[MriCaseResponse]
