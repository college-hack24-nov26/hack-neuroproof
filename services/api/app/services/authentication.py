"""Authentication and hospital membership business rules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import (
    AuthenticationRequiredError,
    ConflictError,
    ResourceNotFoundError,
)
from app.core.security import JwtTokenService, PasswordHasher, TokenClaims
from app.models.auth import Hospital, HospitalMembership, HospitalRole, User
from app.repositories.auth import AuthRepository
from app.schemas.auth import (
    AccessTokenResponse,
    ActorResponse,
    DoctorCreateRequest,
    HospitalRegistrationRequest,
    LoginRequest,
)


@dataclass(frozen=True)
class Principal:
    """Server-resolved user and active hospital membership for one request."""

    user_id: UUID
    hospital_id: UUID
    role: HospitalRole
    email: str
    full_name: str
    hospital_name: str
    hospital_slug: str


def _slugify(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if len(normalized) < 2:
        raise ValueError("Hospital name must include letters or numbers.")
    return normalized[:120]


class AuthenticationService:
    """Create identities, enforce roles, and issue short-lived JWT access tokens."""

    def __init__(
        self,
        session: Session,
        password_hasher: PasswordHasher,
        token_service: JwtTokenService,
    ) -> None:
        self._session = session
        self._repository = AuthRepository(session)
        self._password_hasher = password_hasher
        self._token_service = token_service

    def register_hospital(
        self, request: HospitalRegistrationRequest
    ) -> AccessTokenResponse:
        """Atomically create a hospital, its first administrator, and membership."""

        slug = _slugify(request.hospital_name)
        if self._repository.hospital_by_slug(slug) is not None:
            raise ConflictError("A hospital with this name already exists.")
        if self._repository.user_by_email(request.email) is not None:
            raise ConflictError("An account with this email already exists.")

        hospital = Hospital(name=request.hospital_name.strip(), slug=slug)
        user = User(
            email=request.email,
            full_name=request.administrator_name.strip(),
            password_hash=self._password_hasher.hash(request.password),
        )
        membership = HospitalMembership(
            hospital=hospital,
            user=user,
            role=HospitalRole.HOSPITAL_ADMIN,
        )
        self._repository.add_hospital(hospital)
        self._repository.add_user(user)
        self._repository.add_membership(membership)
        self._commit_or_conflict()
        return self._token_response(self._principal(user, hospital, membership))

    def login(self, request: LoginRequest) -> AccessTokenResponse:
        """Authenticate a password and require a membership at the selected hospital."""

        user = self._repository.user_by_email(request.email)
        if user is None or not self._password_hasher.verify(request.password, user.password_hash):
            raise AuthenticationRequiredError("Invalid email, password, or hospital context.")
        membership = self._repository.membership_for_login(
            user_id=user.id,
            hospital_slug=request.hospital_slug.strip().lower(),
        )
        if membership is None:
            raise AuthenticationRequiredError("Invalid email, password, or hospital context.")
        hospital = self._repository.hospital_by_id(membership.hospital_id)
        if hospital is None:
            raise AuthenticationRequiredError("Invalid email, password, or hospital context.")
        return self._token_response(self._principal(user, hospital, membership))

    def create_doctor(
        self,
        principal: Principal,
        request: DoctorCreateRequest,
    ) -> ActorResponse:
        """Create a doctor only in the administrator's server-resolved hospital."""

        if self._repository.user_by_email(request.email) is not None:
            raise ConflictError("An account with this email already exists.")
        hospital = self._repository.hospital_by_id(principal.hospital_id)
        if hospital is None:
            raise ResourceNotFoundError()
        user = User(
            email=request.email,
            full_name=request.full_name.strip(),
            password_hash=self._password_hasher.hash(request.password),
        )
        membership = HospitalMembership(
            hospital_id=principal.hospital_id,
            user=user,
            role=HospitalRole.DOCTOR,
        )
        self._repository.add_user(user)
        self._repository.add_membership(membership)
        self._commit_or_conflict()
        return self._actor_response(self._principal(user, hospital, membership))

    def principal_from_claims(self, claims: TokenClaims) -> Principal:
        """Revalidate current membership rather than trusting token claims alone."""

        membership = self._repository.membership(
            user_id=claims.subject,
            hospital_id=claims.hospital_id,
        )
        if membership is None or membership.role.value != claims.role:
            raise AuthenticationRequiredError("Authentication context is no longer valid.")
        user = self._session.get(User, claims.subject)
        hospital = self._repository.hospital_by_id(claims.hospital_id)
        if user is None or hospital is None:
            raise AuthenticationRequiredError("Authentication context is no longer valid.")
        return self._principal(user, hospital, membership)

    def principal_from_token(self, token: str) -> Principal:
        """Validate a bearer token before resolving its live membership server-side."""

        return self.principal_from_claims(self._token_service.validate(token))

    def _token_response(self, principal: Principal) -> AccessTokenResponse:
        token, expires_at = self._token_service.issue(
            user_id=principal.user_id,
            hospital_id=principal.hospital_id,
            role=principal.role.value,
        )
        return AccessTokenResponse(
            access_token=token,
            expires_at=expires_at,
            actor=self._actor_response(principal),
        )

    @staticmethod
    def _actor_response(principal: Principal) -> ActorResponse:
        return ActorResponse(
            user_id=principal.user_id,
            full_name=principal.full_name,
            email=principal.email,
            hospital_id=principal.hospital_id,
            hospital_name=principal.hospital_name,
            hospital_slug=principal.hospital_slug,
            role=principal.role.value,
        )

    @staticmethod
    def _principal(
        user: User,
        hospital: Hospital,
        membership: HospitalMembership,
    ) -> Principal:
        return Principal(
            user_id=user.id,
            hospital_id=hospital.id,
            role=membership.role,
            email=user.email,
            full_name=user.full_name,
            hospital_name=hospital.name,
            hospital_slug=hospital.slug,
        )

    def _commit_or_conflict(self) -> None:
        try:
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise ConflictError("The requested record conflicts with an existing record.") from exc
