"""Non-persistent response-contract regressions for federation metadata."""

from datetime import datetime, timezone
from uuid import uuid4

from app.api.v1.federation import update_artifact_response
from app.models.federation import FederationUpdateArtifact


def test_update_artifact_response_includes_persisted_proof_receipt_hash() -> None:
    """Expose the proof receipt hash without treating it as proof verification."""

    receipt_hash = "c" * 64
    artifact = FederationUpdateArtifact(
        id=uuid4(),
        federation_round_id=uuid4(),
        hospital_id=uuid4(),
        training_node_id=uuid4(),
        training_agent_id=uuid4(),
        model_version_id=uuid4(),
        status="submitted",
        proof_verification_status="pending_verification",
        prepared_at=datetime.now(timezone.utc),
        proof_artifact_sha256=receipt_hash,
    )

    response = update_artifact_response(artifact)

    assert response.proof_artifact_sha256 == receipt_hash
    assert response.proof_verification_status == "pending_verification"
    assert response.aggregation_eligible is False
