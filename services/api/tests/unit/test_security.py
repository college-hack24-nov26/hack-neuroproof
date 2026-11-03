"""Unit tests for password hashing and JWT expiry without database substitution."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest

from app.core.security import JwtTokenService, PasswordHasher, TokenValidationError


def test_scrypt_hash_verifies_without_retaining_plaintext() -> None:
    """A correct password verifies and a wrong password cannot verify."""

    hasher = PasswordHasher()
    encoded = hasher.hash("safe-demo-password")

    assert "safe-demo-password" not in encoded
    assert hasher.verify("safe-demo-password", encoded)
    assert not hasher.verify("incorrect-password", encoded)


def test_jwt_validation_rejects_expired_and_tampered_tokens() -> None:
    """JWT validation enforces the issued expiry and HS256 signature."""

    service = JwtTokenService("x" * 32, "test-issuer", ttl_seconds=60)
    token, expires_at = service.issue(
        user_id=uuid4(),
        hospital_id=uuid4(),
        role="doctor",
    )

    claims = service.validate(token, now=expires_at - timedelta(seconds=1))
    assert claims.role == "doctor"
    with pytest.raises(TokenValidationError):
        service.validate(token, now=expires_at)
    with pytest.raises(TokenValidationError):
        service.validate(token + "tampered")
