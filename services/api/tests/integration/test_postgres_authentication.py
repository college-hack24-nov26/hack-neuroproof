"""Real PostgreSQL migration, authentication, and hospital-isolation tests."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.core.errors import AuthenticationRequiredError, ResourceNotFoundError
from app.core.security import JwtTokenService, PasswordHasher
from app.models.imaging import MriCase, MriJobState
from app.schemas.auth import DoctorCreateRequest, HospitalRegistrationRequest, LoginRequest
from app.services.authentication import AuthenticationService
from app.services.hospitals import HospitalService
from app.services.mri_ownership import MriOwnershipService


@pytest.fixture
def postgres_session(postgres_test_database_url: str) -> Session:
    """Migrate a dedicated PostgreSQL test DB and provide a transaction session."""

    previous_value = os.environ.get("CEREBRACHAIN_DATABASE_URL")
    os.environ["CEREBRACHAIN_DATABASE_URL"] = postgres_test_database_url
    api_root = Path(__file__).parents[2]
    config = Config(str(api_root / "alembic.ini"))
    try:
        command.upgrade(config, "head")
        engine = create_engine(postgres_test_database_url)
        expected_tables = {
            "hospitals",
            "users",
            "hospital_memberships",
            "mri_cases",
            "mri_jobs",
            "federation_training_agents",
            "federation_update_artifacts",
        }
        assert expected_tables.issubset(set(inspect(engine).get_table_names()))
        with Session(engine) as session:
            yield session
    finally:
        if previous_value is None:
            os.environ.pop("CEREBRACHAIN_DATABASE_URL", None)
        else:
            os.environ["CEREBRACHAIN_DATABASE_URL"] = previous_value


def _authentication_service(session: Session) -> AuthenticationService:
    return AuthenticationService(
        session,
        PasswordHasher(),
        JwtTokenService("x" * 32, "postgres-integration-test", ttl_seconds=60),
    )


def test_postgres_migration_registration_login_and_hospital_isolation(
    postgres_session: Session,
) -> None:
    """Exercise migration-backed registration, doctor login, and tenancy boundaries."""

    authentication = _authentication_service(postgres_session)
    suffix = uuid4().hex[:10]
    first_admin = authentication.register_hospital(
        HospitalRegistrationRequest(
            hospital_name=f"North Hospital {suffix}",
            administrator_name="North Admin",
            email=f"north-admin-{suffix}@example.test",
            password="north-admin-password",
        )
    )
    first_principal = authentication.principal_from_token(first_admin.access_token)
    doctor = authentication.create_doctor(
        first_principal,
        DoctorCreateRequest(
            full_name="North Doctor",
            email=f"north-doctor-{suffix}@example.test",
            password="north-doctor-password",
        ),
    )
    doctor_login = authentication.login(
        LoginRequest(
            email=doctor.email,
            password="north-doctor-password",
            hospital_slug=f"north-hospital-{suffix}",
        )
    )
    assert doctor_login.actor.role == "doctor"
    with pytest.raises(AuthenticationRequiredError):
        authentication.login(
            LoginRequest(
                email=doctor.email,
                password="wrong-password",
                hospital_slug=f"north-hospital-{suffix}",
            )
        )

    second_admin = authentication.register_hospital(
        HospitalRegistrationRequest(
            hospital_name=f"South Hospital {suffix}",
            administrator_name="South Admin",
            email=f"south-admin-{suffix}@example.test",
            password="south-admin-password",
        )
    )
    second_principal = authentication.principal_from_token(second_admin.access_token)
    south_doctor = authentication.create_doctor(
        second_principal,
        DoctorCreateRequest(
            full_name="South Doctor",
            email=f"south-doctor-{suffix}@example.test",
            password="south-doctor-password",
        ),
    )
    postgres_session.add(
        MriCase(
            hospital_id=second_principal.hospital_id,
            created_by_user_id=second_principal.user_id,
            case_reference="deidentified-south-case",
        )
    )
    postgres_session.commit()

    north_dashboard = HospitalService(postgres_session)
    doctors = north_dashboard.doctors(first_principal).doctors
    assert [item.user_id for item in doctors] == [doctor.user_id]
    south_doctors = north_dashboard.doctors(second_principal).doctors
    assert [item.user_id for item in south_doctors] == [south_doctor.user_id]
    assert north_dashboard.mri_cases(first_principal).cases == []

    ownership = MriOwnershipService(postgres_session)
    south_job = ownership.reserve(second_principal)
    ownership.mark_running(south_job)
    assert south_job.status is MriJobState.RUNNING
    ownership.mark_completed(
        south_job,
        model_sha256="a" * 64,
        model_source="global_fedavg_abc",
    )
    assert south_job.status is MriJobState.COMPLETED
    assert south_job.model_sha256 == "a" * 64
    assert south_job.model_source == "global_fedavg_abc"
    with pytest.raises(ResourceNotFoundError):
        ownership.require_owned(str(south_job.id), first_principal)
