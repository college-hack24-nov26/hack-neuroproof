"""PostgreSQL-backed authenticated update-transport API regression coverage.

All update tensors here are synthetic unit-test tensors. This test never reads
or trains on local MRI data.
"""

from __future__ import annotations

import hashlib
import os
from collections import OrderedDict
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import torch
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.main import create_app
from app.models.federation import FederationRoundParticipant, FederationUpdateArtifact
from app.modules.federation.training_agent import AUTHORIZED_CASE_BY_HOSPITAL_SLUG
from app.modules.federation.update_archive import (
    build_model_update_archive,
    parameter_schema_from_state_dict,
)


TEST_OPERATOR_EMAIL = f"operator-{uuid4().hex}@example.test"

@pytest.fixture
def federation_api_client(
    postgres_test_database_url: str,
    tmp_path: Path,
) -> TestClient:
    """Create a migrated test-only API with protected temporary update storage."""

    previous_value = os.environ.get("CEREBRACHAIN_DATABASE_URL")
    os.environ["CEREBRACHAIN_DATABASE_URL"] = postgres_test_database_url
    api_root = Path(__file__).parents[2]
    config = Config(str(api_root / "alembic.ini"))
    try:
        command.upgrade(config, "head")
        settings = Settings(
            model_checkpoint_path=None,
            model_sha256=None,
            result_storage_dir=None,
            database_url=postgres_test_database_url,
            jwt_secret="x" * 32,
            jwt_issuer="federation-update-transport-test",
            federation_operator_emails=frozenset({TEST_OPERATOR_EMAIL}),
            federation_update_storage_dir=tmp_path / "protected-updates",
        )
        (tmp_path / "protected-updates").mkdir(mode=0o700)
        with TestClient(create_app(settings)) as client:
            yield client
    finally:
        if previous_value is None:
            os.environ.pop("CEREBRACHAIN_DATABASE_URL", None)
        else:
            os.environ["CEREBRACHAIN_DATABASE_URL"] = previous_value


def _register_hospital(client: TestClient, *, name: str, email: str) -> dict[str, object]:
    response = client.post(
        "/api/v1/auth/hospitals/register",
        json={
            "hospital_name": name,
            "administrator_name": "Test Administrator",
            "email": email,
            "password": "a-test-only-password",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _headers(token_response: dict[str, object]) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_response['access_token']}"}


def test_authenticated_update_transport_persists_proof_artifact_hash_after_reload(
    federation_api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    postgres_test_database_url: str,
) -> None:
    """Persist synthetic proof receipts without exposing a real proof or update."""

    suffix = uuid4().hex[:10]
    model_commitment = hashlib.sha256(
        f"synthetic-model-{suffix}".encode("utf-8")
    ).hexdigest()
    operator = _register_hospital(
        federation_api_client,
        name=f"Hospital A {suffix}",
        email=TEST_OPERATOR_EMAIL,
    )

    # Test-only authorization for the synthetic hospital.
    # No real MRI files are accessed or validated.
    monkeypatch.setitem(
        AUTHORIZED_CASE_BY_HOSPITAL_SLUG,
        f"hospital-a-{suffix}",
        "synthetic-integration-case",
    )
    other = _register_hospital(
        federation_api_client,
        name=f"Other Hospital {suffix}",
        email=f"other-{suffix}@example.test",
    )
    operator_headers = _headers(operator)
    other_headers = _headers(other)
    actor = operator["actor"]
    assert isinstance(actor, dict)

    node = federation_api_client.post(
        "/api/v1/federation/training-nodes/enroll",
        headers=operator_headers,
        json={"node_identifier": f"operator-node-{suffix}"},
    )
    assert node.status_code == 201, node.text
    agent = federation_api_client.post(
        "/api/v1/federation/training-agents/enroll",
        headers=operator_headers,
        json={"agent_identifier": f"operator-agent-{suffix}"},
    )
    assert agent.status_code == 201, agent.text
    assert agent.json()["dataset_status"] == "authorized_unvalidated"

    state = OrderedDict(weight=torch.tensor([1.0, 2.0], dtype=torch.float32))
    schema = parameter_schema_from_state_dict(state)
    model = federation_api_client.post(
        "/api/v1/federation/models",
        headers=operator_headers,
        json={
            "label": f"synthetic-model-{suffix}",
            "model_commitment": model_commitment,
            "parameter_schema": [item.to_record() for item in schema],
        },
    )
    assert model.status_code == 201, model.text
    model_id = model.json()["id"]
    federation_round = federation_api_client.post(
        "/api/v1/federation/rounds",
        headers=operator_headers,
        json={
            "base_model_version_id": model_id,
            "participant_hospital_ids": [actor["hospital_id"]],
            "requires_zk_verification": True,
            "research_mode": False,
        },
    )
    assert federation_round.status_code == 201, federation_round.text
    round_id = federation_round.json()["id"]
    assert federation_api_client.post(
        f"/api/v1/federation/rounds/{round_id}/open",
        headers=operator_headers,
    ).status_code == 200
    prepared = federation_api_client.post(
        f"/api/v1/federation/rounds/{round_id}/updates/prepare",
        headers=operator_headers,
        json={"model_version_id": model_id},
    )
    assert prepared.status_code == 201, prepared.text
    submission_id = prepared.json()["id"]
    archive = build_model_update_archive(
        state_dict=state,
        model_version_commitment=model_commitment,
        sample_count=1,
        training_metadata={
            "training_executed": True,
            "local_epochs_completed": 1,
            "training_seconds": 0.01,
        },
    )

    rejected = federation_api_client.post(
        f"/api/v1/federation/updates/{submission_id}/artifact",
        headers=operator_headers,
        files={"artifact": ("synthetic-update.zip", archive, "application/zip")},
    )
    assert rejected.status_code == 200, rejected.text
    submitted_artifact = rejected.json()
    assert submitted_artifact["status"] == "submitted"
    assert submitted_artifact["proof_verification_status"] == "not_submitted"
    assert submitted_artifact["aggregation_eligible"] is False
    cross_hospital = federation_api_client.post(
        f"/api/v1/federation/updates/{submission_id}/artifact",
        headers=other_headers,
        files={"artifact": ("synthetic-update.zip", archive, "application/zip")},
    )
    assert cross_hospital.status_code == 404
    duplicate = federation_api_client.post(
        f"/api/v1/federation/rounds/{round_id}/updates/prepare",
        headers=operator_headers,
        json={"model_version_id": model_id},
    )
    assert duplicate.status_code == 409

    synthetic_artifact_hash = hashlib.sha256(
        b"step-159-synthetic-proof-artifact"
    ).hexdigest()
    synthetic_participant_hash = hashlib.sha256(
        b"step-159-synthetic-participant-proof"
    ).hexdigest()

    assert "proof_artifact_sha256" in FederationUpdateArtifact.__table__.columns
    assert "proof_artifact_sha256" in FederationRoundParticipant.__table__.columns

    engine = create_engine(postgres_test_database_url)
    try:
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version"))
                .scalar_one()
                == "20261103_06"
            )

        with Session(engine) as session:
            artifact = session.get(FederationUpdateArtifact, UUID(submission_id))
            participant = session.scalar(
                select(FederationRoundParticipant).where(
                    FederationRoundParticipant.federation_round_id == UUID(round_id),
                    FederationRoundParticipant.hospital_id
                    == UUID(str(actor["hospital_id"])),
                )
            )
            assert artifact is not None
            assert participant is not None
            assert artifact.proof_artifact_sha256 is None
            assert participant.proof_artifact_sha256 is None

            artifact.proof_artifact_sha256 = synthetic_artifact_hash
            participant.proof_artifact_sha256 = synthetic_participant_hash
            session.commit()

        with Session(engine) as session:
            artifact = session.get(FederationUpdateArtifact, UUID(submission_id))
            participant = session.scalar(
                select(FederationRoundParticipant).where(
                    FederationRoundParticipant.federation_round_id == UUID(round_id),
                    FederationRoundParticipant.hospital_id
                    == UUID(str(actor["hospital_id"])),
                )
            )
            assert artifact is not None
            assert participant is not None
            assert artifact.proof_artifact_sha256 == synthetic_artifact_hash
            assert participant.proof_artifact_sha256 == synthetic_participant_hash

            artifact.proof_artifact_sha256 = None
            session.commit()

        with Session(engine) as session:
            artifact = session.get(FederationUpdateArtifact, UUID(submission_id))
            assert artifact is not None
            assert artifact.proof_artifact_sha256 is None
    finally:
        engine.dispose()
