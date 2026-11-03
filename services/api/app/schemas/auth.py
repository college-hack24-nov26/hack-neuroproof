"""Public request and response schemas for authentication workflows."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


def normalize_email(value: str) -> str:
    """Normalize a simple email address without a network-backed validator."""

    email = value.strip().lower()
    if len(email) > 320 or "@" not in email or email.startswith("@") or email.endswith("@"):
        raise ValueError("A valid email address is required.")
    return email


class HospitalRegistrationRequest(BaseModel):
    """Public hospital and initial administrator registration payload."""

    hospital_name: str = Field(min_length=2, max_length=200)
    administrator_name: str = Field(min_length=2, max_length=200)
    email: str
    password: str = Field(min_length=12, max_length=256)

    _normalize_email = field_validator("email")(normalize_email)


class LoginRequest(BaseModel):
    """One account login bound to a hospital slug."""

    email: str
    password: str = Field(min_length=1, max_length=256)
    hospital_slug: str = Field(min_length=2, max_length=120)

    _normalize_email = field_validator("email")(normalize_email)


class DoctorCreateRequest(BaseModel):
    """Hospital-administrator-only doctor account creation payload."""

    full_name: str = Field(min_length=2, max_length=200)
    email: str
    password: str = Field(min_length=12, max_length=256)

    _normalize_email = field_validator("email")(normalize_email)


class ActorResponse(BaseModel):
    """Safe authenticated identity representation; never includes a password hash."""

    user_id: UUID
    full_name: str
    email: str
    hospital_id: UUID
    hospital_name: str
    hospital_slug: str
    role: str


class AccessTokenResponse(BaseModel):
    """Bearer access token and current authenticated context."""

    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    actor: ActorResponse
