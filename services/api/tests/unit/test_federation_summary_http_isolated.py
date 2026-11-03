"""HTTP tests for hospital isolation in federation summary.

Uses the real FastAPI federation route and role dependencies,
with synthetic repository records and no PostgreSQL connection.
JWT verification and SQL persistence are outside this test scope.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.v1 import dependencies, federation


API = "/api/v1/federation/summary"
OPERATOR_EMAIL = "operator@example.test"
RECEIPT_READER_EMAIL = "receipt-reader@example.test"


class Serializable:
    def __init__(self, value):
        self.value = value

    def model_dump(self, **kwargs):
        return self.value


class FakeAuthRepository:
    def __init__(self, hospitals):
        self.hospitals = hospitals

    def list_hospitals(self):
        return list(self.hospitals)

    def hospital_by_id(self, hospital_id):
        return next(
            (
                hospital
                for hospital in self.hospitals
                if hospital.id == hospital_id
            ),
            None,
        )


class FakeFederationRepository:
    def __init__(self, hospital_ids):
        self.hospital_ids = hospital_ids

        self.agents = [
            SimpleNamespace(
                hospital_id=hospital_id,
                label=f"agent-{index}",
            )
            for index, hospital_id in enumerate(hospital_ids)
        ]

        self.updates = [
            SimpleNamespace(
                hospital_id=hospital_id,
                label=f"update-{index}",
            )
            for index, hospital_id in enumerate(hospital_ids)
        ]

        self.round = SimpleNamespace(id=uuid4())
        self.model = SimpleNamespace(id=uuid4())

        self.checkpoint = SimpleNamespace(
            checkpoint_sha256="a" * 64,
        )

        self.update_scopes = []
        self.round_reads = 0
        self.model_reads = 0
        self.checkpoint_reads = 0

    def list_training_agents(self):
        return list(self.agents)

    def list_update_artifacts(self, *, hospital_id=None, limit=100):
        self.update_scopes.append(hospital_id)

        if hospital_id is None:
            return list(self.updates)

        return [
            item
            for item in self.updates
            if item.hospital_id == hospital_id
        ]

    def list_rounds(self):
        self.round_reads += 1
        return [self.round]

    def participants_for_round(self, round_id):
        assert round_id == self.round.id

        return [
            SimpleNamespace(hospital_id=hospital_id)
            for hospital_id in self.hospital_ids
        ]

    def list_model_versions(self):
        self.model_reads += 1
        return [self.model]

    def list_checkpoints(self):
        self.checkpoint_reads += 1
        return [self.checkpoint]


def make_principal(*, email, hospital_id, role=None):
    return SimpleNamespace(
        email=email,
        hospital_id=hospital_id,
        role=role or dependencies.HospitalRole.HOSPITAL_ADMIN,
    )


@pytest.fixture
def summary_api(monkeypatch, tmp_path):
    expected_source = (
        Path(__file__).resolve().parents[2]
        / "app/api/v1/federation.py"
    )

    assert (
        Path(federation.__file__).resolve()
        == expected_source.resolve()
    ), "Unexpected federation module imported"

    hospital_ids = [uuid4(), uuid4()]

    hospitals = [
        SimpleNamespace(
            id=hospital_id,
            slug=f"synthetic-hospital-{index}",
        )
        for index, hospital_id in enumerate(hospital_ids)
    ]

    repository = FakeFederationRepository(hospital_ids)
    auth_repository = FakeAuthRepository(hospitals)

    monkeypatch.setattr(
        federation,
        "SqlAlchemyFederationRepository",
        lambda session: repository,
    )

    monkeypatch.setattr(
        federation,
        "AuthRepository",
        lambda session: auth_repository,
    )

    monkeypatch.setattr(
        federation,
        "HospitalNodeRegistry",
        lambda repo: SimpleNamespace(
            dashboard_hospitals=lambda records: [
                SimpleNamespace(hospital=record)
                for record in records
            ]
        ),
    )

    monkeypatch.setattr(
        federation,
        "_coordinator_hospital_response",
        lambda item, agent: Serializable({
            "hospital_id": str(item.hospital.id),
            "slug": item.hospital.slug,
        }),
    )

    monkeypatch.setattr(
        federation,
        "training_agent_response",
        lambda agent: Serializable({
            "hospital_id": str(agent.hospital_id),
            "label": agent.label,
        }),
    )

    monkeypatch.setattr(
        federation,
        "update_artifact_response",
        lambda item: Serializable({
            "hospital_id": str(item.hospital_id),
            "label": item.label,
        }),
    )

    monkeypatch.setattr(
        federation,
        "round_response",
        lambda item, participants: Serializable({
            "id": str(item.id),
            "participants": [
                {"hospital_id": str(part.hospital_id)}
                for part in participants
            ],
        }),
    )

    monkeypatch.setattr(
        federation,
        "model_response",
        lambda item: Serializable({
            "id": str(item.id),
        }),
    )

    monkeypatch.setattr(
        federation,
        "checkpoint_response",
        lambda item: Serializable({
            "checkpoint_sha256": item.checkpoint_sha256,
        }),
    )

    monkeypatch.setattr(
        federation,
        "historical_evidence_summary",
        lambda: {
            "source": "synthetic-global-history",
            "experiments": ["operator-only-marker"],
        },
    )

    monkeypatch.setattr(
        federation,
        "verifier_from_settings",
        lambda settings: SimpleNamespace(
            is_ready=False,
            is_available=False,
        ),
    )

    monkeypatch.setattr(
        federation,
        "ModelUpdateArtifactStorage",
        lambda path: SimpleNamespace(is_configured=True),
    )

    app = FastAPI()
    app.include_router(federation.router, prefix="/api/v1")

    state = {
        "principal": make_principal(
            email="admin@example.test",
            hospital_id=hospital_ids[0],
        )
    }

    app.dependency_overrides[
        dependencies.get_current_principal
    ] = lambda: state["principal"]

    app.dependency_overrides[
        dependencies.get_database_session
    ] = lambda: object()

    app.dependency_overrides[
        dependencies.get_settings
    ] = lambda: SimpleNamespace(
        federation_operator_emails=frozenset({
            OPERATOR_EMAIL,
        }),
        proof_receipt_reader_emails=frozenset({RECEIPT_READER_EMAIL}),
        federation_checkpoint_storage_is_configured=True,
        federation_update_storage_dir=tmp_path,
    )

    @app.exception_handler(
        dependencies.AuthorizationDeniedError
    )
    async def authorization_denied(request, exc):
        return JSONResponse(
            status_code=403,
            content={"detail": "Access denied"},
        )

    with TestClient(app) as client:
        yield client, repository, state, hospital_ids


@pytest.mark.parametrize("selected", [0, 1])
def test_hospital_admin_summary_contains_only_own_metadata(
    summary_api,
    selected,
):
    client, repository, state, hospital_ids = summary_api

    own = hospital_ids[selected]
    other = hospital_ids[1 - selected]

    state["principal"] = make_principal(
        email="admin@example.test",
        hospital_id=own,
    )

    response = client.get(API)

    assert response.status_code == 200, response.text

    body = response.json()
    coordinator = body["coordinator"]

    assert [
        item["hospital_id"]
        for item in coordinator["hospitals"]
    ] == [str(own)]

    assert [
        item["hospital_id"]
        for item in coordinator["training_agents"]
    ] == [str(own)]

    assert [
        item["hospital_id"]
        for item in coordinator["submitted_updates"]
    ] == [str(own)]

    assert coordinator["rounds"] == []
    assert coordinator["models"] == []
    assert coordinator["global_checkpoints"] == []

    assert body["historical_evidence"]["available"] is False

    assert repository.update_scopes == [own]

    assert repository.round_reads == 0
    assert repository.model_reads == 0
    assert repository.checkpoint_reads == 0

    serialized = json.dumps(body)

    assert str(other) not in serialized
    assert "operator-only-marker" not in serialized


def test_receipt_reader_summary_remains_hospital_scoped(summary_api):
    client, repository, state, hospital_ids = summary_api
    own, other = hospital_ids

    state["principal"] = make_principal(
        email=RECEIPT_READER_EMAIL,
        hospital_id=own,
    )

    response = client.get(API)

    assert response.status_code == 200, response.text
    coordinator = response.json()["coordinator"]
    assert [item["hospital_id"] for item in coordinator["hospitals"]] == [str(own)]
    assert [item["hospital_id"] for item in coordinator["training_agents"]] == [str(own)]
    assert [item["hospital_id"] for item in coordinator["submitted_updates"]] == [str(own)]
    assert coordinator["rounds"] == []
    assert coordinator["models"] == []
    assert coordinator["global_checkpoints"] == []
    assert response.json()["historical_evidence"]["available"] is False
    assert repository.update_scopes == [own]
    assert repository.round_reads == 0
    assert repository.model_reads == 0
    assert repository.checkpoint_reads == 0
    assert str(other) not in json.dumps(response.json())


def test_operator_summary_contains_global_metadata(summary_api):
    client, repository, state, hospital_ids = summary_api

    state["principal"] = make_principal(
        email=OPERATOR_EMAIL,
        hospital_id=hospital_ids[0],
    )

    response = client.get(API)

    assert response.status_code == 200, response.text

    body = response.json()
    coordinator = body["coordinator"]

    expected = {str(item) for item in hospital_ids}

    assert {
        item["hospital_id"]
        for item in coordinator["hospitals"]
    } == expected

    assert {
        item["hospital_id"]
        for item in coordinator["training_agents"]
    } == expected

    assert {
        item["hospital_id"]
        for item in coordinator["submitted_updates"]
    } == expected

    assert len(coordinator["rounds"]) == 1
    assert len(coordinator["models"]) == 1
    assert len(coordinator["global_checkpoints"]) == 1

    assert {
        item["hospital_id"]
        for item in coordinator["rounds"][0]["participants"]
    } == expected

    assert "operator-only-marker" in json.dumps(
        body["historical_evidence"]
    )

    assert repository.update_scopes == [None]
    assert repository.round_reads == 1
    assert repository.model_reads == 1
    assert repository.checkpoint_reads == 1


def test_doctor_summary_forbidden(summary_api):
    client, repository, state, hospital_ids = summary_api

    state["principal"] = make_principal(
        email="doctor@example.test",
        hospital_id=hospital_ids[0],
        role=dependencies.HospitalRole.DOCTOR,
    )

    response = client.get(API)

    assert response.status_code == 403
    assert repository.update_scopes == []


def test_missing_hospital_id_summary_forbidden(summary_api):
    client, repository, state, _ = summary_api

    state["principal"] = make_principal(
        email="admin@example.test",
        hospital_id=None,
    )

    response = client.get(API)

    assert response.status_code == 403

    assert repository.update_scopes == []
    assert repository.round_reads == 0
    assert repository.model_reads == 0
