"""Password hashing and compact HS256 JWT primitives for API authentication."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4


class PasswordHashError(ValueError):
    """A password hash cannot be parsed or verified safely."""


class TokenValidationError(ValueError):
    """A token is malformed, expired, incorrectly issued, or unsigned."""


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    try:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(value + padding)
    except (ValueError, UnicodeEncodeError) as exc:
        raise TokenValidationError("Token encoding is invalid.") from exc


class PasswordHasher:
    """Use Python's memory-hard scrypt implementation with per-password salt."""

    _PREFIX = "scrypt"
    _N = 2**14
    _R = 8
    _P = 1
    _DKLEN = 64

    def hash(self, password: str) -> str:
        """Return a self-describing salted scrypt hash without retaining plaintext."""

        salt = secrets.token_bytes(16)
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=self._N,
            r=self._R,
            p=self._P,
            dklen=self._DKLEN,
        )
        return "$".join(
            (
                self._PREFIX,
                str(self._N),
                str(self._R),
                str(self._P),
                _base64url_encode(salt),
                _base64url_encode(digest),
            )
        )

    def verify(self, password: str, encoded_hash: str) -> bool:
        """Compare a password against one stored scrypt hash in constant time."""

        try:
            prefix, n, r, p, encoded_salt, expected_digest = encoded_hash.split("$")
            if prefix != self._PREFIX:
                return False
            actual_digest = hashlib.scrypt(
                password.encode("utf-8"),
                salt=_base64url_decode(encoded_salt),
                n=int(n),
                r=int(r),
                p=int(p),
                dklen=self._DKLEN,
            )
            return hmac.compare_digest(actual_digest, _base64url_decode(expected_digest))
        except (TypeError, ValueError, PasswordHashError, TokenValidationError):
            return False


@dataclass(frozen=True)
class TokenClaims:
    """Validated token data used to load the server-side membership."""

    subject: UUID
    hospital_id: UUID
    role: str
    expires_at: datetime


class JwtTokenService:
    """Issue and validate short-lived HS256 access tokens without a default secret."""

    def __init__(self, secret: str, issuer: str, ttl_seconds: int) -> None:
        if len(secret) < 32:
            raise ValueError("JWT signing secret must be at least 32 characters.")
        if not issuer:
            raise ValueError("JWT issuer must not be empty.")
        self._secret = secret.encode("utf-8")
        self._issuer = issuer
        self._ttl_seconds = ttl_seconds

    def issue(self, *, user_id: UUID, hospital_id: UUID, role: str) -> tuple[str, datetime]:
        """Issue a signed access token for one explicit hospital membership."""

        issued_at = datetime.now(timezone.utc)
        expires_at = issued_at + timedelta(seconds=self._ttl_seconds)
        payload = {
            "sub": str(user_id),
            "hospital_id": str(hospital_id),
            "role": role,
            "iss": self._issuer,
            "iat": int(issued_at.timestamp()),
            "exp": int(expires_at.timestamp()),
            "jti": str(uuid4()),
        }
        header = {"alg": "HS256", "typ": "JWT"}
        encoded_header = _base64url_encode(
            json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
        encoded_payload = _base64url_encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
        signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
        signature = hmac.new(self._secret, signing_input, hashlib.sha256).digest()
        return f"{encoded_header}.{encoded_payload}.{_base64url_encode(signature)}", expires_at

    def validate(self, token: str, *, now: datetime | None = None) -> TokenClaims:
        """Validate signature, issuer, expiry, and identity claims before use."""

        try:
            encoded_header, encoded_payload, encoded_signature = token.split(".")
            signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
            expected_signature = hmac.new(
                self._secret, signing_input, hashlib.sha256
            ).digest()
            if not hmac.compare_digest(expected_signature, _base64url_decode(encoded_signature)):
                raise TokenValidationError("Token signature is invalid.")
            header: dict[str, Any] = json.loads(_base64url_decode(encoded_header))
            payload: dict[str, Any] = json.loads(_base64url_decode(encoded_payload))
            if header != {"alg": "HS256", "typ": "JWT"}:
                raise TokenValidationError("Token header is invalid.")
            if payload.get("iss") != self._issuer:
                raise TokenValidationError("Token issuer is invalid.")
            expires_at = datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc)
            current_time = now or datetime.now(timezone.utc)
            if expires_at <= current_time:
                raise TokenValidationError("Token has expired.")
            return TokenClaims(
                subject=UUID(str(payload["sub"])),
                hospital_id=UUID(str(payload["hospital_id"])),
                role=str(payload["role"]),
                expires_at=expires_at,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            if isinstance(exc, TokenValidationError):
                raise
            raise TokenValidationError("Token claims are invalid.") from exc
