"""Public and authenticated identity endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from app.api.v1.dependencies import get_authentication_service, get_current_principal
from app.schemas.auth import (
    AccessTokenResponse,
    ActorResponse,
    HospitalRegistrationRequest,
    LoginRequest,
)
from app.services.authentication import AuthenticationService, Principal

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/hospitals/register",
    response_model=AccessTokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a hospital and its initial administrator",
)
def register_hospital(
    request: HospitalRegistrationRequest,
    service: AuthenticationService = Depends(get_authentication_service),
) -> AccessTokenResponse:
    """Create a new hospital tenancy with one hospital-administrator membership."""

    return service.register_hospital(request)


@router.post("/login", response_model=AccessTokenResponse, summary="Log in to a hospital context")
def login(
    request: LoginRequest,
    service: AuthenticationService = Depends(get_authentication_service),
) -> AccessTokenResponse:
    """Issue a short-lived bearer token for one verified hospital membership."""

    return service.login(request)


@router.get("/me", response_model=ActorResponse, summary="Read the authenticated account context")
def current_account(
    principal: Principal = Depends(get_current_principal),
) -> ActorResponse:
    """Return the server-resolved user and active hospital membership."""

    return ActorResponse(
        user_id=principal.user_id,
        full_name=principal.full_name,
        email=principal.email,
        hospital_id=principal.hospital_id,
        hospital_name=principal.hospital_name,
        hospital_slug=principal.hospital_slug,
        role=principal.role.value,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Discard the current access token")
def logout(_: Principal = Depends(get_current_principal)) -> Response:
    """Confirm stateless logout; clients must discard their short-lived access token."""

    return Response(status_code=status.HTTP_204_NO_CONTENT)
