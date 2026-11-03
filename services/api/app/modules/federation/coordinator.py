"""Coordinator-facing business rules independent from FastAPI route handlers."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.core.errors import ConflictError, ResourceNotFoundError
from app.models.auth import Hospital
from app.models.federation import (
    FederationGlobalCheckpoint,
    FederationModelVersion,
    FederationRound,
    FederationRoundParticipant,
    FederationTrainingNode,
)
from app.modules.federation.checkpoints import GlobalCheckpointManager
from app.modules.federation.fedavg import (
    AggregationResult,
    FedAvgAggregator,
    FedAvgValidationError,
    ModelUpdate,
    state_dict_sha256,
)
from app.modules.federation.update_archive import (
    normalize_parameter_schema,
    parameter_schema_commitment,
)
from app.modules.federation.types import (
    FederationRoundStatus,
    ProofVerificationStatus,
    RoundParticipantStatus,
    TrainingNodeStatus,
)
from app.modules.federation.verification import (
    Groth16VerificationResult,
    Groth16VerificationRequest,
    Groth16Verifier,
    UnavailableGroth16Verifier,
)
from app.services.authentication import Principal


class FederationRepository(Protocol):
    """Persistence operations used by the coordinator service."""

    def training_node_for_hospital(self, hospital_id: UUID) -> FederationTrainingNode | None: ...

    def list_training_nodes(self) -> list[FederationTrainingNode]: ...

    def model_version(self, model_version_id: UUID) -> FederationModelVersion | None: ...

    def round(self, round_id: UUID) -> FederationRound | None: ...

    def participants_for_round(self, round_id: UUID) -> list[FederationRoundParticipant]: ...

    def add(self, entity: object) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class CoordinatorHospital:
    """Dashboard-safe enrollment status for one dynamically discovered hospital."""

    hospital: Hospital
    training_node_status: str


class HospitalNodeRegistry:
    """Discover registered hospitals and require a separate explicit enrollment."""

    def __init__(self, repository: FederationRepository) -> None:
        self._repository = repository

    def enroll_current_hospital(
        self,
        *,
        principal: Principal,
        node_identifier: str,
    ) -> FederationTrainingNode:
        """Enroll only the caller's server-resolved hospital tenancy."""

        node = self._repository.training_node_for_hospital(principal.hospital_id)
        if node is None:
            node = FederationTrainingNode(
                hospital_id=principal.hospital_id,
                node_identifier=node_identifier,
                status=TrainingNodeStatus.ENROLLED.value,
            )
            self._repository.add(node)
        else:
            node.node_identifier = node_identifier
            node.status = TrainingNodeStatus.ENROLLED.value
            node.updated_at = _now()
        self._commit_or_conflict("Training node enrollment conflicts with an existing record.")
        return node

    def dashboard_hospitals(self, hospitals: Iterable[Hospital]) -> list[CoordinatorHospital]:
        """Join all registered hospitals with enrollment without hardcoded names."""

        node_by_hospital = {
            node.hospital_id: node
            for node in self._repository.list_training_nodes()
        }
        result: list[CoordinatorHospital] = []
        for hospital in hospitals:
            node = node_by_hospital.get(hospital.id)
            status = node.status if node is not None else "not_enrolled"
            result.append(CoordinatorHospital(hospital=hospital, training_node_status=status))
        return result

    def _commit_or_conflict(self, message: str) -> None:
        try:
            self._repository.commit()
        except IntegrityError as exc:
            self._repository.rollback()
            raise ConflictError(message) from exc


class RoundManager:
    """Validate explicit and auditable round lifecycle transitions."""

    _transitions = {
        FederationRoundStatus.DRAFT: {FederationRoundStatus.OPEN, FederationRoundStatus.FAILED},
        FederationRoundStatus.OPEN: {FederationRoundStatus.AGGREGATING, FederationRoundStatus.FAILED},
        FederationRoundStatus.AGGREGATING: {FederationRoundStatus.COMPLETED, FederationRoundStatus.FAILED},
        FederationRoundStatus.COMPLETED: set(),
        FederationRoundStatus.FAILED: set(),
    }

    def transition(self, federation_round: FederationRound, target: FederationRoundStatus) -> None:
        """Move a round only through its allowed forward lifecycle."""

        current = FederationRoundStatus(federation_round.status)
        if target not in self._transitions[current]:
            raise ConflictError(f"Round cannot transition from {current.value} to {target.value}.")
        federation_round.status = target.value
        federation_round.updated_at = _now()
        if target in {FederationRoundStatus.COMPLETED, FederationRoundStatus.FAILED}:
            federation_round.completed_at = federation_round.updated_at


@dataclass(frozen=True)
class ValidatedModelUpdate:
    """An update whose public bindings and proof status were evaluated."""

    update: ModelUpdate
    proof_status: ProofVerificationStatus
    verification_reason: str | None
    verification_result: Groth16VerificationResult | None = None


class ProofVerificationError(FedAvgValidationError):
    """A validation failure with an explicit persisted Groth16 status."""

    def __init__(
        self,
        code: str,
        message: str,
        proof_status: ProofVerificationStatus,
    ) -> None:
        super().__init__(code, message)
        self.proof_status = proof_status


class ModelUpdateValidator:
    """Validate update/public-proof bindings before aggregation is considered."""

    def __init__(self, verifier: Groth16Verifier | None = None) -> None:
        self._verifier = verifier or UnavailableGroth16Verifier()

    @property
    def production_aggregation_ready(self) -> bool:
        """Expose whether a reviewed verifier permits any aggregation attempt."""

        return self._verifier.is_ready

    @property
    def verification_available(self) -> bool:
        """Whether a pinned verifier can perform cryptographic checks at all."""

        return self._verifier.is_available

    def validate(
        self,
        *,
        federation_round: FederationRound,
        expected_model_commitment: str,
        update: ModelUpdate,
    ) -> ValidatedModelUpdate:
        """Fail closed for production ZK rounds unless a verifier returns verified."""

        if update.model_version_commitment != expected_model_commitment:
            raise FedAvgValidationError(
                "model_version_commitment_mismatch",
                "Model update is not bound to this round's base model version.",
            )
        calculated_commitment = state_dict_sha256(update.state_dict)
        if update.hospital_update_commitment.lower() != calculated_commitment:
            raise FedAvgValidationError(
                "update_commitment_mismatch",
                "Model update commitment does not match the submitted state dict.",
            )

        if not federation_round.requires_zk_verification:
            if not federation_round.research_mode:
                raise FedAvgValidationError(
                    "unsafe_non_zk_round",
                    "Non-ZK aggregation is permitted only for explicitly labeled research rounds.",
                )
            return ValidatedModelUpdate(
                update=update,
                proof_status=ProofVerificationStatus.NOT_SUBMITTED,
                verification_reason="Research-only non-ZK aggregation; no Groth16 verification was requested.",
            )

        if update.proof_artifact_reference is None or update.proof_envelope is None:
            raise ProofVerificationError(
                "proof_not_submitted",
                "Production aggregation requires a submitted Groth16 proof artifact.",
                ProofVerificationStatus.NOT_SUBMITTED,
            )
        if update.artifact_sha256 is None:
            raise ProofVerificationError(
                "artifact_binding_missing",
                "Groth16 verification requires a protected update-artifact binding.",
                ProofVerificationStatus.REJECTED,
            )
        if not self._verifier.is_available:
            raise ProofVerificationError(
                "verifier_unavailable",
                "A pinned Groth16 verifier is not configured.",
                ProofVerificationStatus.PENDING_VERIFICATION,
            )
        result = self._verifier.verify(
            Groth16VerificationRequest(
                training_round_identifier=str(federation_round.id),
                model_version_commitment=expected_model_commitment,
                hospital_update_commitment=update.hospital_update_commitment,
                proof_artifact_reference=update.proof_artifact_reference,
                hospital_id=update.hospital_id,
                artifact_sha256=update.artifact_sha256,
                state_dict=update.state_dict,
                proof_envelope=update.proof_envelope,
            )
        )
        if result.status is not ProofVerificationStatus.VERIFIED:
            raise ProofVerificationError(
                "proof_not_verified",
                result.reason or "Groth16 proof verification did not succeed.",
                result.status,
            )
        return ValidatedModelUpdate(
            update=update,
            proof_status=result.status,
            verification_reason=result.reason,
            verification_result=result,
        )


class FederationCoordinator:
    """Orchestrate custom round records, validation, aggregation, and provenance."""

    def __init__(
        self,
        repository: FederationRepository,
        *,
        round_manager: RoundManager | None = None,
        validator: ModelUpdateValidator | None = None,
        aggregator: FedAvgAggregator | None = None,
        checkpoint_manager: GlobalCheckpointManager | None = None,
    ) -> None:
        self._repository = repository
        self._round_manager = round_manager or RoundManager()
        self._validator = validator or ModelUpdateValidator()
        self._aggregator = aggregator or FedAvgAggregator()
        self._checkpoint_manager = checkpoint_manager or GlobalCheckpointManager(None)

    def register_model_version(
        self,
        *,
        label: str,
        model_commitment: str,
        created_by_user_id: UUID,
        artifact_reference: str | None = None,
        parameter_schema: list[dict[str, object]] | None = None,
    ) -> FederationModelVersion:
        """Register immutable base-model metadata; no checkpoint bytes enter HTTP."""

        normalized_schema = (
            normalize_parameter_schema(parameter_schema)
            if parameter_schema is not None
            else None
        )
        version = FederationModelVersion(
            label=label,
            model_commitment=model_commitment,
            artifact_reference=artifact_reference,
            parameter_schema=(
                [item.to_record() for item in normalized_schema]
                if normalized_schema is not None
                else None
            ),
            parameter_schema_commitment=(
                parameter_schema_commitment(normalized_schema)
                if normalized_schema is not None
                else None
            ),
            created_by_user_id=created_by_user_id,
        )
        self._repository.add(version)
        self._commit_or_conflict("A model version with this label or commitment already exists.")
        return version

    def create_round(
        self,
        *,
        base_model_version_id: UUID,
        participant_hospital_ids: Sequence[UUID],
        created_by_user_id: UUID,
        requires_zk_verification: bool,
        research_mode: bool,
    ) -> FederationRound:
        """Create a draft only from explicitly enrolled distinct hospital nodes."""

        if not requires_zk_verification and not research_mode:
            raise ConflictError("Non-ZK aggregation is allowed only for a labeled research round.")
        if not participant_hospital_ids:
            raise ConflictError("A training round requires at least one participant.")
        if len(set(participant_hospital_ids)) != len(participant_hospital_ids):
            raise ConflictError("A hospital may appear only once in a training round.")
        if self._repository.model_version(base_model_version_id) is None:
            raise ResourceNotFoundError("The requested base model version was not found.")

        nodes: list[FederationTrainingNode] = []
        for hospital_id in participant_hospital_ids:
            node = self._repository.training_node_for_hospital(hospital_id)
            if node is None or node.status != TrainingNodeStatus.ENROLLED.value:
                raise ConflictError("Every round participant must have an enrolled training node.")
            nodes.append(node)

        federation_round = FederationRound(
            base_model_version_id=base_model_version_id,
            created_by_user_id=created_by_user_id,
            status=FederationRoundStatus.DRAFT.value,
            requires_zk_verification=requires_zk_verification,
            research_mode=research_mode,
        )
        self._repository.add(federation_round)
        for hospital_id, node in zip(participant_hospital_ids, nodes, strict=True):
            self._repository.add(
                FederationRoundParticipant(
                    federation_round=federation_round,
                    hospital_id=hospital_id,
                    training_node_id=node.id,
                    status=RoundParticipantStatus.INVITED.value,
                    proof_verification_status=ProofVerificationStatus.NOT_SUBMITTED.value,
                )
            )
        self._commit_or_conflict("Training round creation conflicts with an existing record.")
        return federation_round

    def open_round(self, round_id: UUID) -> FederationRound:
        """Open a validated draft round for a future authenticated node transport."""

        federation_round = self._get_round(round_id)
        self._round_manager.transition(federation_round, FederationRoundStatus.OPEN)
        self._repository.commit()
        return federation_round

    def aggregate_round(
        self,
        *,
        round_id: UUID,
        updates: Sequence[ModelUpdate],
    ) -> FederationGlobalCheckpoint:
        """Aggregate already transported private updates and record only provenance.

        This method is intentionally not exposed as a browser endpoint.  A future
        hospital-node transport must authenticate the node and keep raw updates
        outside PostgreSQL before calling this coordinator boundary.
        """

        federation_round = self._get_round(round_id)
        if not self._validator.production_aggregation_ready:
            raise ConflictError("Aggregation is blocked until a reviewed Groth16 verifier is configured.")
        if FederationRoundStatus(federation_round.status) is not FederationRoundStatus.OPEN:
            raise ConflictError("Only an open training round can be aggregated.")
        base_model = self._repository.model_version(federation_round.base_model_version_id)
        if base_model is None:
            raise ResourceNotFoundError("The round base model version was not found.")
        participants = self._repository.participants_for_round(federation_round.id)
        participant_by_hospital = {participant.hospital_id: participant for participant in participants}
        if set(participant_by_hospital) != {update.hospital_id for update in updates}:
            raise FedAvgValidationError(
                "participant_set_mismatch",
                "Submitted updates do not exactly match the round participant set.",
            )

        self._round_manager.transition(federation_round, FederationRoundStatus.AGGREGATING)
        self._repository.commit()
        try:
            validated: list[ValidatedModelUpdate] = []
            for update in updates:
                participant = participant_by_hospital[update.hospital_id]
                try:
                    item = self._validator.validate(
                        federation_round=federation_round,
                        expected_model_commitment=base_model.model_commitment,
                        update=update,
                    )
                except ProofVerificationError as exc:
                    self._record_proof_failure(participant, update, exc)
                    raise
                validated.append(item)
                if participant.training_node_id != item.update.training_node_id:
                    raise FedAvgValidationError(
                        "training_node_mismatch",
                        "Model update was not submitted by the enrolled training node.",
                    )
                participant.status = RoundParticipantStatus.ACCEPTED.value
                participant.sample_count = item.update.sample_count
                participant.update_commitment = item.update.hospital_update_commitment
                participant.proof_artifact_reference = item.update.proof_artifact_reference
                participant.proof_verification_status = item.proof_status.value
                participant.verification_reason = item.verification_reason
                participant.submitted_at = _now()

            result = self._aggregator.aggregate([item.update for item in validated])
            checkpoint = self._persist_aggregate(federation_round, base_model, result)
            self._round_manager.transition(federation_round, FederationRoundStatus.COMPLETED)
            self._repository.commit()
            return checkpoint
        except (FedAvgValidationError, RuntimeError) as exc:
            federation_round.failure_reason = str(exc)
            self._round_manager.transition(federation_round, FederationRoundStatus.FAILED)
            self._repository.commit()
            raise

    def _persist_aggregate(
        self,
        federation_round: FederationRound,
        base_model: FederationModelVersion,
        result: AggregationResult,
    ) -> FederationGlobalCheckpoint:
        output_version = FederationModelVersion(
            label=f"round-{federation_round.id}",
            model_commitment=state_dict_sha256(result.state_dict),
            parent_model_version_id=base_model.id,
            created_by_user_id=federation_round.created_by_user_id,
        )
        saved = self._checkpoint_manager.save(
            model_version_id=output_version.id,
            state_dict=result.state_dict,
            metadata={
                "round_id": str(federation_round.id),
                "base_model_commitment": base_model.model_commitment,
                "participant_hospital_ids": [str(value) for value in result.participant_hospital_ids],
                "aggregation_algorithm": self._aggregator.algorithm,
            },
        )
        output_version.artifact_reference = saved.storage_reference
        output_version.artifact_sha256 = saved.sha256
        checkpoint = FederationGlobalCheckpoint(
            federation_round_id=federation_round.id,
            model_version=output_version,
            storage_reference=saved.storage_reference,
            checkpoint_sha256=saved.sha256,
            size_bytes=saved.size_bytes,
            aggregation_algorithm=self._aggregator.algorithm,
            participant_count=len(result.participant_hospital_ids),
            total_sample_count=result.total_sample_count,
        )
        federation_round.global_model_version = output_version
        self._repository.add(output_version)
        self._repository.add(checkpoint)
        return checkpoint

    def _get_round(self, round_id: UUID) -> FederationRound:
        federation_round = self._repository.round(round_id)
        if federation_round is None:
            raise ResourceNotFoundError("The requested training round was not found.")
        return federation_round

    @staticmethod
    def _record_proof_failure(
        participant: FederationRoundParticipant,
        update: ModelUpdate,
        error: ProofVerificationError,
    ) -> None:
        """Persist an observed proof state while still failing aggregation closed."""

        participant.status = (
            RoundParticipantStatus.REJECTED.value
            if error.proof_status is ProofVerificationStatus.REJECTED
            else RoundParticipantStatus.SUBMITTED.value
        )
        participant.sample_count = update.sample_count
        participant.update_commitment = update.hospital_update_commitment
        participant.proof_artifact_reference = update.proof_artifact_reference
        participant.proof_verification_status = error.proof_status.value
        participant.verification_reason = str(error)
        participant.submitted_at = _now()

    def _commit_or_conflict(self, message: str) -> None:
        try:
            self._repository.commit()
        except IntegrityError as exc:
            self._repository.rollback()
            raise ConflictError(message) from exc
