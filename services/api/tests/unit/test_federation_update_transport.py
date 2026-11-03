"""Synthetic-only tests for Phase 2 protected update transport."""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import torch

from app.core.errors import ConflictError, FederationUpdateRejectedError, ResourceNotFoundError
from app.models.auth import HospitalRole
from app.models.federation import (
    FederationModelVersion,
    FederationRound,
    FederationRoundParticipant,
    FederationTrainingAgent,
    FederationTrainingNode,
    FederationUpdateArtifact,
)
from app.modules.federation.training_agent import dataset_authorization_for_hospital
from app.modules.federation.types import FederationRoundStatus
from app.modules.federation.update_archive import (
    UpdateArchiveError,
    build_model_update_archive,
    parameter_schema_commitment,
    parameter_schema_from_state_dict,
    parse_model_update_archive,
)
from app.modules.federation.update_storage import ModelUpdateArtifactStorage
from app.modules.federation.update_transport import ModelUpdateSubmissionService
from app.services.authentication import Principal


def _principal(hospital_id: UUID, slug: str = "hospital-a") -> Principal:
    return Principal(
        user_id=uuid4(),
        hospital_id=hospital_id,
        role=HospitalRole.HOSPITAL_ADMIN,
        email=f"{slug}@example.test",
        full_name="Test Admin",
        hospital_name=slug,
        hospital_slug=slug,
    )


def _state() -> OrderedDict[str, torch.Tensor]:
    return OrderedDict(
        weight=torch.tensor([1.0, 2.0], dtype=torch.float32),
        counter=torch.tensor(3, dtype=torch.int64),
    )


def _synthetic_training_metadata() -> dict[str, object]:
    """Test-only metadata; it is never evidence of hospital training."""

    return {
        "training_executed": True,
        "local_epochs_completed": 1,
        "training_seconds": 0.01,
    }


class StubRepository:
    """In-memory metadata repository; no MRI or model files are used."""

    def __init__(self) -> None:
        self.node: FederationTrainingNode | None = None
        self.agent: FederationTrainingAgent | None = None
        self._round: FederationRound | None = None
        self.model: FederationModelVersion | None = None
        self.participant: FederationRoundParticipant | None = None
        self.artifacts: dict[UUID, FederationUpdateArtifact] = {}

    def training_node_for_hospital(self, hospital_id: UUID) -> FederationTrainingNode | None:
        return self.node if self.node is not None and self.node.hospital_id == hospital_id else None

    def training_agent_for_hospital(self, hospital_id: UUID) -> FederationTrainingAgent | None:
        return self.agent if self.agent is not None and self.agent.hospital_id == hospital_id else None

    def update_artifact_for_round_hospital(
        self, *, round_id: UUID, hospital_id: UUID,
    ) -> FederationUpdateArtifact | None:
        return next(
            (
                item
                for item in self.artifacts.values()
                if item.federation_round_id == round_id and item.hospital_id == hospital_id
            ),
            None,
        )

    def update_artifact(self, submission_id: UUID) -> FederationUpdateArtifact | None:
        return self.artifacts.get(submission_id)

    def model_version(self, model_version_id: UUID) -> FederationModelVersion | None:
        return self.model if self.model is not None and self.model.id == model_version_id else None

    def round(self, round_id: UUID) -> FederationRound | None:
        return self._round if self._round is not None and self._round.id == round_id else None

    def participant_for_round_hospital(
        self, *, round_id: UUID, hospital_id: UUID,
    ) -> FederationRoundParticipant | None:
        if self.participant is None or self.participant.federation_round_id != round_id:
            return None
        return self.participant if self.participant.hospital_id == hospital_id else None

    def add(self, entity: object) -> None:
        assert isinstance(entity, FederationUpdateArtifact)
        if entity.id is None:
            entity.id = uuid4()
        self.artifacts[entity.id] = entity

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


def _repository() -> tuple[StubRepository, Principal]:
    repository = StubRepository()
    hospital_id = uuid4()
    principal = _principal(hospital_id)
    state = _state()
    schema = parameter_schema_from_state_dict(state)
    model = FederationModelVersion(
        id=uuid4(),
        label="synthetic-model-v1",
        model_commitment="a" * 64,
        parameter_schema=[item.to_record() for item in schema],
        parameter_schema_commitment=parameter_schema_commitment(schema),
        created_by_user_id=principal.user_id,
    )
    node = FederationTrainingNode(
        id=uuid4(),
        hospital_id=hospital_id,
        node_identifier="synthetic-node-a",
        status="enrolled",
    )
    agent = FederationTrainingAgent(
        id=uuid4(),
        hospital_id=hospital_id,
        training_node_id=node.id,
        agent_identifier="synthetic-agent-a",
        status="enrolled",
        authorized_case_reference="BraTS2021_00495",
        dataset_status="authorized_unvalidated",
        training_execution_enabled=False,
    )
    federation_round = FederationRound(
        id=uuid4(),
        base_model_version_id=model.id,
        created_by_user_id=principal.user_id,
        status=FederationRoundStatus.OPEN.value,
        requires_zk_verification=True,
        research_mode=False,
        updated_at=datetime.now(timezone.utc),
    )
    participant = FederationRoundParticipant(
        id=uuid4(),
        federation_round_id=federation_round.id,
        hospital_id=hospital_id,
        training_node_id=node.id,
        status="invited",
        proof_verification_status="not_submitted",
    )
    repository.node = node
    repository.agent = agent
    repository.model = model
    repository._round = federation_round
    repository.participant = participant
    return repository, principal


def test_safe_update_archive_round_trips_only_matching_synthetic_schema() -> None:
    state = _state()
    schema = parameter_schema_from_state_dict(state)
    archive = build_model_update_archive(
        state_dict=state,
        model_version_commitment="a" * 64,
        sample_count=2,
        training_metadata=_synthetic_training_metadata(),
    )

    parsed = parse_model_update_archive(
        archive,
        expected_schema=schema,
        expected_schema_commitment=parameter_schema_commitment(schema),
        max_bytes=1_000_000,
    )

    assert parsed.sample_count == 2
    assert torch.equal(parsed.state_dict["weight"], state["weight"])
    assert parsed.training_metadata is not None


def test_safe_update_archive_rejects_schema_mismatch() -> None:
    archive = build_model_update_archive(
        state_dict=_state(),
        model_version_commitment="a" * 64,
        sample_count=1,
        training_metadata=_synthetic_training_metadata(),
    )
    wrong_state = OrderedDict(weight=torch.tensor([1.0], dtype=torch.float32))
    wrong_schema = parameter_schema_from_state_dict(wrong_state)

    with pytest.raises(UpdateArchiveError) as error:
        parse_model_update_archive(
            archive,
            expected_schema=wrong_schema,
            expected_schema_commitment=parameter_schema_commitment(wrong_schema),
            max_bytes=1_000_000,
        )
    assert error.value.code == "parameter_schema_mismatch"


def test_safe_update_archive_preserves_bfloat16_bits() -> None:
    state = OrderedDict(weight=torch.tensor([1.0, -2.5], dtype=torch.bfloat16))
    schema = parameter_schema_from_state_dict(state)
    archive = build_model_update_archive(
        state_dict=state,
        model_version_commitment="a" * 64,
        sample_count=1,
        training_metadata=_synthetic_training_metadata(),
    )

    parsed = parse_model_update_archive(
        archive,
        expected_schema=schema,
        expected_schema_commitment=parameter_schema_commitment(schema),
        max_bytes=1_000_000,
    )

    assert parsed.state_dict["weight"].dtype is torch.bfloat16
    assert torch.equal(parsed.state_dict["weight"], state["weight"])


def test_update_submission_is_hospital_scoped_duplicate_safe_and_awaits_a_proof(tmp_path: Path) -> None:
    repository, principal = _repository()
    service = ModelUpdateSubmissionService(
        repository,
        storage=ModelUpdateArtifactStorage(tmp_path),
        max_bytes=1_000_000,
    )
    assert repository._round is not None
    assert repository.model is not None
    submission = service.prepare(
        principal=principal,
        round_id=repository._round.id,
        model_version_id=repository.model.id,
    )
    archive = build_model_update_archive(
        state_dict=_state(),
        model_version_commitment="a" * 64,
        sample_count=1,
        training_metadata=_synthetic_training_metadata(),
    )

    submitted = service.submit_artifact(
        principal=principal,
        submission_id=submission.id,
        content=archive,
    )

    assert submitted.status == "submitted"
    assert submission.proof_verification_status == "not_submitted"
    assert submission.artifact_sha256 is not None
    assert submission.artifact_reference is not None
    with pytest.raises(ConflictError):
        service.prepare(
            principal=principal,
            round_id=repository._round.id,
            model_version_id=repository.model.id,
        )
    with pytest.raises(ResourceNotFoundError):
        service.submit_artifact(
            principal=_principal(uuid4(), "hospital-b"),
            submission_id=submission.id,
            content=archive,
        )


def test_hospital_e_has_no_approved_training_dataset() -> None:
    assert dataset_authorization_for_hospital("hospital-a").case_reference == "BraTS2021_00495"
    assert dataset_authorization_for_hospital("hospital-b").case_reference == "BraTS2021_00000"
    assert dataset_authorization_for_hospital("hospital-c").case_reference == "BraTS2021_00002"
    assert dataset_authorization_for_hospital("hospital-d").case_reference == "BraTS2021_00130"
    assert dataset_authorization_for_hospital("hospital-e").case_reference is None
    assert dataset_authorization_for_hospital("hospital-f").status == "not_approved"
