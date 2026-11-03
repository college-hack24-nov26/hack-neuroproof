"""PostgreSQL-backed authenticated update-transport API regression coverage.

All update tensors here are synthetic unit-test tensors. This test never reads
or trains on local MRI data.
"""

from __future__ import annotations

import hashlib

import json
import shutil
import subprocess
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.federation import FederationUpdateArtifact
from app.modules.federation.groth16 import hash_to_field, quantize_state_dict
import os
from collections import OrderedDict
from pathlib import Path
from uuid import uuid4

import pytest
import torch
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
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

            groth16_artifacts_dir=(
                Path.home()
                / ".local/share/cerebrachain-v2/groth16-dev-verifier"
            ),
            groth16_manifest_sha256=(
                "958d1e268a9af2afdc4f7bdf267d800"
                "006303652572ae64f390d855c2de86d86"
            ),
            groth16_snarkjs_binary=(
                Path(__file__).resolve().parents[4]
                / "tools/zk/node_modules/.bin/snarkjs"
            ),
            groth16_node_binary=Path(shutil.which("node") or "/nonexistent"),
            groth16_poseidon_script=(
                Path(__file__).resolve().parents[4]
                / "tools/zk/scripts/poseidon_commitment.mjs"
            ),
            groth16_timeout_seconds=60,
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


def test_authenticated_real_groth16_proof_api(
    federation_api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    postgres_test_database_url: str,
) -> None:
    """Exercise server-derived tenancy, duplicate prevention, and ZK fail-closed state."""

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


    # The cross-hospital proof attempt must not reveal the submission.
    verifier_dir = (
        Path.home()
        / ".local/share/cerebrachain-v2/groth16-dev-verifier"
    )

    manifest_bytes = (verifier_dir / "manifest.json").read_bytes()
    expected_manifest_hash = (
        "958d1e268a9af2afdc4f7bdf267d800"
        "006303652572ae64f390d855c2de86d86"
    )
    assert hashlib.sha256(manifest_bytes).hexdigest() == expected_manifest_hash

    manifest = json.loads(manifest_bytes)
    verification_key_bytes = (
        verifier_dir / "verification_key.json"
    ).read_bytes()

    verification_key_id = hashlib.sha256(
        verification_key_bytes
    ).hexdigest()

    assert verification_key_id == manifest["verification_key_sha256"]

    # The actual submitted artifact hash must be used for proof binding.
    artifact_sha256 = submitted_artifact["artifact_sha256"]
    assert isinstance(artifact_sha256, str)

    proof_input = {
        "circuit_version": manifest["circuit_version"],
        "verification_key_id": verification_key_id,
        "round_context": hash_to_field(
            "cerebrachain/v2/groth16/round",
            str(round_id),
        ),
        "model_context": hash_to_field(
            "cerebrachain/v2/groth16/model",
            model_commitment.lower(),
        ),
        "artifact_context": hash_to_field(
            "cerebrachain/v2/groth16/artifact",
            artifact_sha256.lower(),
        ),
        "chunks": [
            list(chunk)
            for chunk in quantize_state_dict(state).chunks
        ],
    }

    project_root = Path(__file__).resolve().parents[4]
    prover_dir = Path("/tmp/cerebrachain-zk-artifacts.ANjp7V")

    wasm = (
        prover_dir
        / "quantized_update_chunk_v1_js"
        / "quantized_update_chunk_v1.wasm"
    )
    zkey = prover_dir / "quantized_update_chunk_v1_final.zkey"

    assert wasm.is_file(), "Development WASM unavailable"
    assert zkey.is_file(), "Development proving key unavailable"

    proof_input_path = tmp_path / "proof-input.json"
    proof_output_path = tmp_path / "proof-output.json"

    proof_input_path.write_text(json.dumps(proof_input))

    completed = subprocess.run(
        [
            shutil.which("node") or "node",
            str(project_root / "tools/zk/scripts/prove-dev.mjs"),
            "--wasm", str(wasm),
            "--zkey", str(zkey),
            "--input", str(proof_input_path),
            "--output", str(proof_output_path),
        ],
        cwd=str(project_root / "tools/zk"),
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )

    assert completed.returncode == 0, (
        "Groth16 development proof generation failed"
    )
    assert proof_output_path.is_file()

    proof_envelope = json.loads(proof_output_path.read_text())

    # Unauthorized hospital must be rejected before verification.
    cross_hospital_proof = federation_api_client.post(
        f"/api/v1/federation/updates/{submission_id}/proof",
        headers=other_headers,
        json=proof_envelope,
    )
    assert cross_hospital_proof.status_code == 404

    # Real cryptographic verification through authenticated FastAPI.
    verified = federation_api_client.post(
        f"/api/v1/federation/updates/{submission_id}/proof",
        headers=operator_headers,
        json=proof_envelope,
    )

    assert verified.status_code == 200, verified.text

    result = verified.json()

    assert result["status"] == "accepted"
    assert result["proof_verification_status"] == "verified"
    assert result["zk_coverage_complete"] is True
    assert result["aggregation_eligible"] is False

    # Confirm database persistence, not just the HTTP response.
    engine = create_engine(postgres_test_database_url)

    try:
        with Session(engine) as session:
            record = session.get(
                FederationUpdateArtifact,
                UUID(submission_id),
            )

            assert record is not None
            assert record.proof_verification_status == "verified"
            assert record.aggregation_eligible is False
            assert record.zk_coverage_complete is True
    finally:
        engine.dispose()
