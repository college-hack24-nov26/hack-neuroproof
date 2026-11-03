"""FastAPI dependencies for application services."""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import (
    AuthenticationRequiredError,
    AuthorizationDeniedError,
    ConfigurationUnavailableError,
)
from app.core.security import JwtTokenService, PasswordHasher, TokenValidationError
from app.db.session import Database
from app.models.auth import HospitalRole
from app.services.authentication import AuthenticationService, Principal
from app.services.mri_segmentation import MriSegmentationService

_bearer_scheme = HTTPBearer(auto_error=False)


def get_mri_service(request: Request) -> MriSegmentationService:
    """Return the application-scoped serialized MRI service."""

    return request.app.state.mri_service


def get_settings(request: Request) -> Settings:
    """Return application configuration without exposing its values to routes."""

    return request.app.state.settings


def get_database_session(request: Request) -> Generator[Session, None, None]:
    """Yield one SQLAlchemy session only when PostgreSQL is configured."""

    database: Database | None = request.app.state.database
    if database is None:
        raise ConfigurationUnavailableError(
            "Database-backed authentication is unavailable.",
            code="authentication_unavailable",
        )
    yield from database.session()


def get_authentication_service(
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_database_session),
) -> AuthenticationService:
    """Construct an authentication service from runtime secret configuration."""

    if not settings.authentication_is_configured or settings.jwt_secret is None:
        raise ConfigurationUnavailableError(
            "Authentication is not configured.",
            code="authentication_unavailable",
        )
    return AuthenticationService(
        session,
        PasswordHasher(),
        JwtTokenService(
            settings.jwt_secret,
            settings.jwt_issuer,
            settings.access_token_ttl_seconds,
        ),
    )


def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    authentication_service: AuthenticationService = Depends(get_authentication_service),
) -> Principal:
    """Validate a bearer token and re-resolve its live hospital membership."""

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationRequiredError()
    try:
        return authentication_service.principal_from_token(credentials.credentials)
    except TokenValidationError as exc:
        raise AuthenticationRequiredError("Invalid or expired access token.") from exc


def require_hospital_admin(
    principal: Principal = Depends(get_current_principal),
) -> Principal:
    """Require a server-validated hospital administrator membership."""

    if principal.role is not HospitalRole.HOSPITAL_ADMIN:
        raise AuthorizationDeniedError()
    return principal


def require_federation_operator(
    principal: Principal = Depends(require_hospital_admin),
    settings: Settings = Depends(get_settings),
) -> Principal:
    """Require an explicitly configured coordinator operator identity.

    A hospital administrator is allowed to enroll only its own node.  Creating
    global model versions or rounds additionally requires an allowlisted
    server-side operator identity, so a browser cannot self-grant that power.
    """

    if principal.email.lower() not in settings.federation_operator_emails:
        raise AuthorizationDeniedError("Federation operator authorization is required.")
    return principal


def require_proof_receipt_reader(
    principal: Principal = Depends(require_hospital_admin),
    settings: Settings = Depends(get_settings),
) -> Principal:
    """Allow only an exact, server-configured read-only receipt viewer.

    Existing federation operators retain V2 receipt-read access, but this
    dependency grants no federation control-plane permissions to a dedicated
    viewer. The principal has already been resolved from a valid JWT and an
    active hospital-admin membership by ``require_hospital_admin``.
    """

    normalized_email = principal.email.lower()
    if normalized_email not in (
        settings.proof_receipt_reader_emails
        | settings.federation_operator_emails
    ):
        raise AuthorizationDeniedError("Proof receipt viewer authorization is required.")
    return principal
