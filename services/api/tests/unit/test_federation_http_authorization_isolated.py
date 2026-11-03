"""FastAPI HTTP authorization tests using synthetic dependencies.

Exercises the real federation router and authorization dependencies.
Does not test JWT validation, database persistence, or production startup.
No PostgreSQL connection, MRI reads, or model training.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.v1 import dependencies, federation


API_PREFIX = "/api/v1/federation"

OPERATOR_EMAIL = "operator@example.test"
RECEIPT_READER_EMAIL = "receipt-reader@example.test"


class FakeFederationRepository:
    def __init__(self):
        self.update_scopes = []
        self.model_reads = 0
        self.round_reads = 0

    def list_update_artifacts(self, *, hospital_id=None, limit=100):
        self.update_scopes.append(hospital_id)
        return []

    def list_model_versions(self):
        self.model_reads += 1
        return []

    def list_rounds(self):
        self.round_reads += 1
        return []


def make_principal(*, role, email, hospital_id):
    return SimpleNamespace(
        role=role,
        email=email,
        hospital_id=hospital_id,
    )


@pytest.fixture
def isolated_http_api(monkeypatch):
    expected_source = (
        Path(__file__).resolve().parents[2]
        / "app/api/v1/federation.py"
    )

    assert (
        Path(federation.__file__).resolve()
        == expected_source.resolve()
    ), "STOP: Unexpected federation module imported"

    repository = FakeFederationRepository()

    monkeypatch.setattr(
        federation,
        "SqlAlchemyFederationRepository",
        lambda session: repository,
    )

    app = FastAPI()

    app.include_router(
        federation.router,
        prefix="/api/v1",
    )

    state = {
        "principal": make_principal(
            role=dependencies.HospitalRole.HOSPITAL_ADMIN,
            email="admin@example.test",
            hospital_id=uuid4(),
        )
    }

    # Replace principal resolution and database session only.
    # The real require_hospital_admin and
    # require_federation_operator functions remain active.
    app.dependency_overrides[
        dependencies.get_current_principal
    ] = lambda: state["principal"]

    app.dependency_overrides[
        dependencies.get_database_session
    ] = lambda: object()

    app.dependency_overrides[
        dependencies.get_settings
    ] = lambda: SimpleNamespace(
        federation_operator_emails=frozenset(
            {OPERATOR_EMAIL}
        ),
        proof_receipt_reader_emails=frozenset({RECEIPT_READER_EMAIL}),
    )

    # The minimal test app has no production exception handlers.
    # Map its real authorization exception to HTTP 403.
    @app.exception_handler(
        dependencies.AuthorizationDeniedError
    )
    async def authorization_denied(request, exc):
        return JSONResponse(
            status_code=403,
            content={"detail": "Access denied"},
        )

    with TestClient(app) as client:
        yield client, repository, state


@pytest.mark.parametrize("hospital_number", [0, 1])
def test_hospital_admin_update_listing_uses_own_scope(
    isolated_http_api,
    hospital_number,
):
    client, repository, state = isolated_http_api

    hospital_ids = [uuid4(), uuid4()]

    state["principal"] = make_principal(
        role=dependencies.HospitalRole.HOSPITAL_ADMIN,
        email="admin@example.test",
        hospital_id=hospital_ids[hospital_number],
    )

    response = client.get(f"{API_PREFIX}/updates")

    assert response.status_code == 200, response.text
    assert response.json() == []
    assert repository.update_scopes == [
        hospital_ids[hospital_number]
    ]


def test_operator_update_listing_uses_global_scope(
    isolated_http_api,
):
    client, repository, state = isolated_http_api

    state["principal"] = make_principal(
        role=dependencies.HospitalRole.HOSPITAL_ADMIN,
        email=OPERATOR_EMAIL.upper(),
        hospital_id=uuid4(),
    )

    response = client.get(f"{API_PREFIX}/updates")

    assert response.status_code == 200, response.text
    assert repository.update_scopes == [None]


def test_receipt_reader_update_listing_remains_hospital_scoped(
    isolated_http_api,
):
    client, repository, state = isolated_http_api
    hospital_id = uuid4()

    state["principal"] = make_principal(
        role=dependencies.HospitalRole.HOSPITAL_ADMIN,
        email=RECEIPT_READER_EMAIL,
        hospital_id=hospital_id,
    )

    response = client.get(f"{API_PREFIX}/updates")

    assert response.status_code == 200, response.text
    assert repository.update_scopes == [hospital_id]


@pytest.mark.parametrize(
    "endpoint",
    ["updates", "summary", "models", "rounds"],
)
def test_doctor_cannot_access_federation_admin_routes(
    isolated_http_api,
    endpoint,
):
    client, repository, state = isolated_http_api

    state["principal"] = make_principal(
        role=dependencies.HospitalRole.DOCTOR,
        email="doctor@example.test",
        hospital_id=uuid4(),
    )

    response = client.get(f"{API_PREFIX}/{endpoint}")

    assert response.status_code == 403
    assert repository.update_scopes == []


@pytest.mark.parametrize("endpoint", ["models", "rounds"])
def test_nonoperator_admin_cannot_read_global_resources(
    isolated_http_api,
    endpoint,
):
    client, repository, state = isolated_http_api

    state["principal"] = make_principal(
        role=dependencies.HospitalRole.HOSPITAL_ADMIN,
        email="admin@example.test",
        hospital_id=uuid4(),
    )

    response = client.get(f"{API_PREFIX}/{endpoint}")

    assert response.status_code == 403
    assert repository.model_reads == 0
    assert repository.round_reads == 0


@pytest.mark.parametrize(
    "endpoint",
    ["models", "rounds"],
)
def test_receipt_reader_cannot_read_global_resources(
    isolated_http_api,
    endpoint,
):
    client, repository, state = isolated_http_api

    state["principal"] = make_principal(
        role=dependencies.HospitalRole.HOSPITAL_ADMIN,
        email=RECEIPT_READER_EMAIL,
        hospital_id=uuid4(),
    )

    response = client.get(f"{API_PREFIX}/{endpoint}")

    assert response.status_code == 403
    assert repository.model_reads == 0
    assert repository.round_reads == 0


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("models", {"label": "base-v1", "model_commitment": "a" * 64}),
        (
            "rounds",
            {
                "base_model_version_id": str(uuid4()),
                "participant_hospital_ids": [str(uuid4())],
            },
        ),
        (f"rounds/{uuid4()}/open", None),
    ],
)
def test_receipt_reader_cannot_change_federation_control_plane(
    isolated_http_api,
    path,
    payload,
):
    client, _, state = isolated_http_api
    state["principal"] = make_principal(
        role=dependencies.HospitalRole.HOSPITAL_ADMIN,
        email=RECEIPT_READER_EMAIL,
        hospital_id=uuid4(),
    )

    response = client.post(
        f"{API_PREFIX}/{path}",
        json=payload,
    )

    assert response.status_code == 403


@pytest.mark.parametrize("endpoint", ["updates", "summary"])
def test_missing_hospital_identity_fails_closed(
    isolated_http_api,
    endpoint,
):
    client, repository, state = isolated_http_api

    state["principal"] = make_principal(
        role=dependencies.HospitalRole.HOSPITAL_ADMIN,
        email="admin@example.test",
        hospital_id=None,
    )

    response = client.get(f"{API_PREFIX}/{endpoint}")

    assert response.status_code == 403
    assert repository.update_scopes == []


@pytest.mark.parametrize("endpoint", ["models", "rounds"])
def test_operator_can_read_global_resource_endpoints(
    isolated_http_api,
    endpoint,
):
    client, repository, state = isolated_http_api

    state["principal"] = make_principal(
        role=dependencies.HospitalRole.HOSPITAL_ADMIN,
        email=OPERATOR_EMAIL,
        hospital_id=uuid4(),
    )

    response = client.get(f"{API_PREFIX}/{endpoint}")

    assert response.status_code == 200, response.text
    assert response.json() == []

    if endpoint == "models":
        assert repository.model_reads == 1
    else:
        assert repository.round_reads == 1
