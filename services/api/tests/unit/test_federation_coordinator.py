"""Coordinator lifecycle, dynamic enrollment, checkpoint, and ZK-boundary tests."""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import torch

from app.core.errors import ConflictError
from app.models.auth import Hospital, HospitalRole
from app.models.federation import FederationRound, FederationTrainingNode
from app.modules.federation.checkpoints import CheckpointPersistenceError, GlobalCheckpointManager
from app.modules.federation.coordinator import HospitalNodeRegistry, ModelUpdateValidator, RoundManager
from app.modules.federation.fedavg import FedAvgValidationError, ModelUpdate, state_dict_sha256
from app.modules.federation.types import FederationRoundStatus, ProofVerificationStatus
from app.modules.federation.verification import Groth16ChunkProof, Groth16ProofEnvelope
from app.services.authentication import Principal


class StubFederationRepository:
    """In-memory repository double; it never represents a production database."""

    def __init__(self) -> None:
        self.nodes: dict[UUID, FederationTrainingNode] = {}

    def training_node_for_hospital(self, hospital_id: UUID) -> FederationTrainingNode | None:
        return self.nodes.get(hospital_id)

    def list_training_nodes(self) -> list[FederationTrainingNode]:
        return list(self.nodes.values())

    def add(self, entity: object) -> None:
        assert isinstance(entity, FederationTrainingNode)
        self.nodes[entity.hospital_id] = entity

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


def _hospital(slug: str) -> Hospital:
    return Hospital(id=uuid4(), name=slug.replace("-", " ").title(), slug=slug)


def _principal(hospital: Hospital) -> Principal:
    return Principal(
        user_id=uuid4(),
        hospital_id=hospital.id,
        role=HospitalRole.HOSPITAL_ADMIN,
        email="admin@example.test",
        full_name="Test Administrator",
        hospital_name=hospital.name,
        hospital_slug=hospital.slug,
    )


def _round(*, requires_zk_verification: bool, research_mode: bool) -> FederationRound:
    return FederationRound(
        id=uuid4(),
        base_model_version_id=uuid4(),
        created_by_user_id=uuid4(),
        status=FederationRoundStatus.OPEN.value,
        requires_zk_verification=requires_zk_verification,
        research_mode=research_mode,
        updated_at=datetime.now(timezone.utc),
    )


def _model_update(*, proof_artifact_reference: str | None = None) -> ModelUpdate:
    state = OrderedDict(weight=torch.tensor([1.0, 2.0], dtype=torch.float32))
    return ModelUpdate(
        hospital_id=uuid4(),
        training_node_id=uuid4(),
        sample_count=1,
        state_dict=state,
        model_version_commitment="b" * 64,
        hospital_update_commitment=state_dict_sha256(state),
        proof_artifact_reference=proof_artifact_reference,
        artifact_sha256="c" * 64 if proof_artifact_reference else None,
        proof_envelope=(
            Groth16ProofEnvelope(
                circuit_version="quantized-update-chunk-v1",
                verification_key_id="d" * 64,
                proofs=(
                    Groth16ChunkProof(
                        proof={"pi_a": ["0", "0", "1"], "pi_b": [["0", "0"], ["0", "0"], ["1", "0"]], "pi_c": ["0", "0", "1"], "protocol": "groth16", "curve": "bn128"},
                        public_signals=("0",) * 7,
                    ),
                ),
            )
            if proof_artifact_reference
            else None
        ),
    )


def test_registered_hospitals_are_dynamic_and_enrollment_is_explicit() -> None:
    hospital_a = _hospital("hospital-a")
    hospital_f = _hospital("hospital-f")
    repository = StubFederationRepository()
    registry = HospitalNodeRegistry(repository)

    node = registry.enroll_current_hospital(
        principal=_principal(hospital_a),
        node_identifier="hospital-a-node-1",
    )
    statuses = registry.dashboard_hospitals([hospital_a, hospital_f])

    assert node.hospital_id == hospital_a.id
    assert {item.hospital.slug: item.training_node_status for item in statuses} == {
        "hospital-a": "enrolled",
        "hospital-f": "not_enrolled",
    }


def test_round_manager_allows_only_forward_transitions() -> None:
    federation_round = _round(requires_zk_verification=True, research_mode=False)
    federation_round.status = FederationRoundStatus.DRAFT.value
    manager = RoundManager()

    manager.transition(federation_round, FederationRoundStatus.OPEN)
    manager.transition(federation_round, FederationRoundStatus.AGGREGATING)
    manager.transition(federation_round, FederationRoundStatus.COMPLETED)

    assert federation_round.status == FederationRoundStatus.COMPLETED.value
    assert federation_round.completed_at is not None
    with pytest.raises(ConflictError):
        manager.transition(federation_round, FederationRoundStatus.OPEN)


def test_production_update_verification_fails_closed_without_real_groth16_verifier() -> None:
    federation_round = _round(requires_zk_verification=True, research_mode=False)

    with pytest.raises(FedAvgValidationError) as error:
        ModelUpdateValidator().validate(
            federation_round=federation_round,
            expected_model_commitment="b" * 64,
            update=_model_update(proof_artifact_reference="proofs/round-1/update-a.json"),
        )

    assert error.value.code == "verifier_unavailable"


def test_research_non_zk_update_is_explicitly_not_submitted_not_verified() -> None:
    result = ModelUpdateValidator().validate(
        federation_round=_round(requires_zk_verification=False, research_mode=True),
        expected_model_commitment="b" * 64,
        update=_model_update(),
    )

    assert result.proof_status is ProofVerificationStatus.NOT_SUBMITTED
    assert "Research-only" in (result.verification_reason or "")


def test_global_checkpoint_manager_uses_new_namespace_and_refuses_overwrite(tmp_path: Path) -> None:
    manager = GlobalCheckpointManager(tmp_path)
    model_version_id = uuid4()
    state = OrderedDict(weight=torch.tensor([1.0], dtype=torch.float32))

    saved = manager.save(model_version_id=model_version_id, state_dict=state, metadata={"round_id": "test"})

    assert saved.storage_reference == f"custom-coordinator/{model_version_id}.pt"
    assert (tmp_path / saved.storage_reference).is_file()
    with pytest.raises(CheckpointPersistenceError, match="already exists"):
        manager.save(model_version_id=model_version_id, state_dict=state, metadata={"round_id": "test"})
