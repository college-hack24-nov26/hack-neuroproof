"""Role checks for hospital-scoped administration and model access."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.api.v1.dependencies import (
    require_federation_operator,
    require_hospital_admin,
    require_proof_receipt_reader,
)
from app.core.config import Settings
from app.core.errors import AuthenticationRequiredError, AuthorizationDeniedError
from app.core.security import TokenClaims
from app.models.auth import HospitalRole
from app.services.authentication import AuthenticationService, Principal


def _principal(role: HospitalRole) -> Principal:
    return Principal(
        user_id=uuid4(),
        hospital_id=uuid4(),
        role=role,
        email="actor@example.test",
        full_name="Actor",
        hospital_name="Research Hospital",
        hospital_slug="research-hospital",
    )


def test_hospital_admin_authorization_allows_only_admin_membership() -> None:
    admin = _principal(HospitalRole.HOSPITAL_ADMIN)

    assert require_hospital_admin(admin) is admin
    with pytest.raises(AuthorizationDeniedError):
        require_hospital_admin(_principal(HospitalRole.DOCTOR))


def test_federation_operator_requires_server_side_allowlist() -> None:
    admin = _principal(HospitalRole.HOSPITAL_ADMIN)
    settings = Settings(
        model_checkpoint_path=None,
        model_sha256=None,
        result_storage_dir=None,
        federation_operator_emails=frozenset({admin.email}),
    )

    assert require_federation_operator(admin, settings) is admin
    with pytest.raises(AuthorizationDeniedError):
        require_federation_operator(
            admin,
            Settings(
                model_checkpoint_path=None,
                model_sha256=None,
                result_storage_dir=None,
            ),
        )


def test_proof_receipt_reader_requires_exact_server_side_allowlist() -> None:
    admin = _principal(HospitalRole.HOSPITAL_ADMIN)
    admin = Principal(
        user_id=admin.user_id,
        hospital_id=admin.hospital_id,
        role=admin.role,
        email="Receipt.Reader@Example.Test",
        full_name=admin.full_name,
        hospital_name=admin.hospital_name,
        hospital_slug=admin.hospital_slug,
    )
    settings = Settings(
        model_checkpoint_path=None,
        model_sha256=None,
        result_storage_dir=None,
        proof_receipt_reader_emails=frozenset({"receipt.reader@example.test"}),
    )

    assert require_proof_receipt_reader(admin, settings) is admin
    with pytest.raises(AuthorizationDeniedError):
        require_proof_receipt_reader(
            admin,
            Settings(
                model_checkpoint_path=None,
                model_sha256=None,
                result_storage_dir=None,
                proof_receipt_reader_emails=frozenset({"reader@example.test"}),
            ),
        )


def test_empty_proof_receipt_reader_allowlist_fails_closed() -> None:
    admin = _principal(HospitalRole.HOSPITAL_ADMIN)

    with pytest.raises(AuthorizationDeniedError):
        require_proof_receipt_reader(
            admin,
            Settings(
                model_checkpoint_path=None,
                model_sha256=None,
                result_storage_dir=None,
            ),
        )


def test_proof_receipt_reader_email_configuration_is_exact_and_normalized(monkeypatch) -> None:
    monkeypatch.setenv(
        "CEREBRACHAIN_PROOF_RECEIPT_READER_EMAILS",
        " Receipt.Reader@Example.Test,other@example.test ,,",
    )

    settings = Settings.from_environment()

    assert settings.proof_receipt_reader_emails == frozenset(
        {"receipt.reader@example.test", "other@example.test"}
    )


def test_removed_hospital_membership_cannot_reach_reader_authorization() -> None:
    session = Mock()
    session.scalar.return_value = None
    service = AuthenticationService(session, Mock(), Mock())
    claims = TokenClaims(
        subject=uuid4(),
        hospital_id=uuid4(),
        role=HospitalRole.HOSPITAL_ADMIN.value,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )

    with pytest.raises(AuthenticationRequiredError):
        service.principal_from_claims(claims)
