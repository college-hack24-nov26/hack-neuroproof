"""Hospital-scoped preparation and submission of protected model updates."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Protocol
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.core.errors import (
    ConfigurationUnavailableError,
    ConflictError,
    FederationUpdateRejectedError,
    ResourceNotFoundError,
)
from app.models.federation import (
    FederationModelVersion,
    FederationRound,
    FederationRoundParticipant,
    FederationTrainingAgent,
    FederationTrainingNode,
    FederationUpdateArtifact,
)
from app.modules.federation.coordinator import (
    ModelUpdateValidator,
    ProofVerificationError,
    ValidatedModelUpdate,
)
from app.modules.federation.fedavg import FedAvgValidationError, ModelUpdate
from app.modules.federation.verification import Groth16ProofEnvelope
from app.modules.federation.training_agent import dataset_authorization_for_hospital
from app.modules.federation.types import (
    FederationRoundStatus,
    ProofVerificationStatus,
    RoundParticipantStatus,
    TrainingAgentStatus,
    UpdateArtifactStatus,
)
from app.modules.federation.update_archive import (
    UpdateArchiveError,
    normalize_parameter_schema,
    parse_model_update_archive,
)
from app.modules.federation.update_storage import (
    ModelUpdateArtifactStorage,
    UpdateArtifactStorageError,
)
from app.services.authentication import Principal


from app.modules.federation.update_integrity import (
    UpdateIntegrityError,
    verify_pinned_model_update,
)


class UpdateTransportRepository(Protocol):
    """Persistence operations needed by agent enrollment and update transport."""

    def training_node_for_hospital(self, hospital_id: UUID) -> FederationTrainingNode | None: ...

    def training_agent_for_hospital(self, hospital_id: UUID) -> FederationTrainingAgent | None: ...

    def update_artifact_for_round_hospital(
        self,
        *,
        round_id: UUID,
        hospital_id: UUID,
    ) -> FederationUpdateArtifact | None: ...

    def update_artifact(self, submission_id: UUID) -> FederationUpdateArtifact | None: ...

    def round(self, round_id: UUID) -> FederationRound | None: ...

    def model_version(self, model_version_id: UUID) -> FederationModelVersion | None: ...

    def participant_for_round_hospital(
        self,
        *,
        round_id: UUID,
        hospital_id: UUID,
    ) -> FederationRoundParticipant | None: ...

    def add(self, entity: object) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TrainingAgentRegistry:
    """Require a separate hospital-local training-agent enrollment after node enrollment."""

    def __init__(self, repository: UpdateTransportRepository, *, execution_enabled: bool) -> None:
        self._repository = repository
        self._execution_enabled = execution_enabled

    def enroll_current_hospital(
        self,
        *,
        principal: Principal,
        agent_identifier: str,
    ) -> FederationTrainingAgent:
        """Enroll an agent for only the authenticated hospital's enrolled node."""

        node = self._repository.training_node_for_hospital(principal.hospital_id)
        if node is None or node.status != "enrolled":
            raise ConflictError("An enrolled training node is required before enrolling an agent.")
        assignment = dataset_authorization_for_hospital(principal.hospital_slug)
        agent = self._repository.training_agent_for_hospital(principal.hospital_id)
        if agent is None:
            agent = FederationTrainingAgent(
                hospital_id=principal.hospital_id,
                training_node_id=node.id,
                agent_identifier=agent_identifier,
                status=TrainingAgentStatus.ENROLLED.value,
                authorized_case_reference=assignment.case_reference,
                dataset_status=assignment.status,
                training_execution_enabled=self._execution_enabled,
            )
            self._repository.add(agent)
        else:
            agent.training_node_id = node.id
            agent.agent_identifier = agent_identifier
            agent.status = TrainingAgentStatus.ENROLLED.value
            agent.authorized_case_reference = assignment.case_reference
            agent.dataset_status = assignment.status
            agent.training_execution_enabled = self._execution_enabled
            agent.updated_at = _now()
        self._commit_or_conflict("Training agent enrollment conflicts with an existing record.")
        return agent

    def _commit_or_conflict(self, message: str) -> None:
        try:
            self._repository.commit()
        except IntegrityError as exc:
            self._repository.rollback()
            raise ConflictError(message) from exc


class ModelUpdateSubmissionService:
    """Validate, persist, and record one private update for an invited hospital."""

    def __init__(
        self,
        repository: UpdateTransportRepository,
        *,
        storage: ModelUpdateArtifactStorage,
        max_bytes: int,
        proof_max_bytes: int = 128 * 1024,
        validator: ModelUpdateValidator | None = None,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._max_bytes = max_bytes
        self._proof_max_bytes = proof_max_bytes
        self._validator = validator or ModelUpdateValidator()

    def prepare(
        self,
        *,
        principal: Principal,
        round_id: UUID,
        model_version_id: UUID,
    ) -> FederationUpdateArtifact:
        """Create one hospital-scoped submission slot before any artifact bytes arrive."""

        if not self._storage.is_configured:
            raise ConfigurationUnavailableError(
                "Federation update storage is not configured.",
                code="federation_update_storage_unavailable",
            )
        federation_round = self._required_round(round_id)
        if federation_round.status != FederationRoundStatus.OPEN.value:
            raise ConflictError("Updates can be prepared only for an open training round.")
        if federation_round.base_model_version_id != model_version_id:
            raise ConflictError("Requested model version is not the round base model.")
        model_version = self._required_model_version(model_version_id)
        if model_version.parameter_schema is None or model_version.parameter_schema_commitment is None:
            raise ConflictError("Round base model has no approved parameter schema.")
        node, agent, _ = self._authorized_participant(principal, federation_round)
        existing = self._repository.update_artifact_for_round_hospital(
            round_id=round_id,
            hospital_id=principal.hospital_id,
        )
        if existing is not None:
            raise ConflictError("This hospital already prepared or submitted an update for the round.")
        artifact = FederationUpdateArtifact(
            federation_round_id=round_id,
            hospital_id=principal.hospital_id,
            training_node_id=node.id,
            training_agent_id=agent.id,
            model_version_id=model_version.id,
            status=UpdateArtifactStatus.PREPARED.value,
            proof_verification_status=ProofVerificationStatus.NOT_SUBMITTED.value,
        )
        self._repository.add(artifact)
        self._commit_or_conflict("Update preparation conflicts with an existing hospital submission.")
        return artifact

    def submit_artifact(
        self,
        *,
        principal: Principal,
        submission_id: UUID,
        content: bytes,
    ) -> FederationUpdateArtifact:
        """Store a prepared update, then move it to the explicit awaiting-proof state."""

        artifact = self._required_owned_artifact(principal, submission_id)
        if artifact.status != UpdateArtifactStatus.PREPARED.value:
            raise ConflictError("This update submission is no longer available for upload.")
        federation_round = self._required_round(artifact.federation_round_id)
        if federation_round.status != FederationRoundStatus.OPEN.value:
            raise ConflictError("Updates can be submitted only for an open training round.")
        node, agent, participant = self._authorized_participant(principal, federation_round)
        if node.id != artifact.training_node_id or agent.id != artifact.training_agent_id:
            raise ConflictError("Update submission no longer matches the enrolled training agent.")
        model_version = self._required_model_version(artifact.model_version_id)
        try:
            schema = normalize_parameter_schema(model_version.parameter_schema)
            parsed = parse_model_update_archive(
                content,
                expected_schema=schema,
                expected_schema_commitment=model_version.parameter_schema_commitment or "",
                max_bytes=self._max_bytes,
            )
            if parsed.model_version_commitment != model_version.model_commitment:
                raise UpdateArchiveError(
                    "model_version_commitment_mismatch",
                    "Update artifact is not bound to the selected model version.",
                )
            if parsed.proof_artifact_reference is not None:
                raise UpdateArchiveError(
                    "proof_reference_forbidden",
                    "Groth16 proofs must use the authenticated proof-submission endpoint.",
                )
            stored = self._storage.save(
                federation_round_id=federation_round.id,
                submission_id=artifact.id,
                content=content,
            )
            artifact.artifact_reference = stored.storage_reference
            artifact.artifact_sha256 = stored.sha256
            artifact.artifact_size_bytes = stored.size_bytes
            artifact.update_commitment = parsed.update_commitment
            artifact.parameter_schema_commitment = parsed.parameter_schema_commitment
            artifact.sample_count = parsed.sample_count
            artifact.training_metadata = parsed.training_metadata
            artifact.submitted_at = _now()
            artifact.status = UpdateArtifactStatus.SUBMITTED.value
            artifact.proof_verification_status = ProofVerificationStatus.NOT_SUBMITTED.value
            participant.status = RoundParticipantStatus.SUBMITTED.value
            participant.sample_count = parsed.sample_count
            participant.update_commitment = parsed.update_commitment
            participant.proof_verification_status = ProofVerificationStatus.NOT_SUBMITTED.value
            participant.verification_reason = "Update artifact submitted; awaiting Groth16 proof."
            participant.submitted_at = artifact.submitted_at
        except UpdateArchiveError as exc:
            self._reject(artifact, participant, exc.code, str(exc), ProofVerificationStatus.REJECTED)
        except UpdateArtifactStorageError as exc:
            self._reject(artifact, participant, "artifact_storage_failed", str(exc), ProofVerificationStatus.REJECTED)
        self._repository.commit()
        if artifact.status == UpdateArtifactStatus.REJECTED.value:
            raise FederationUpdateRejectedError(artifact.rejection_reason or "Federated model update was rejected.")
        return artifact

    def submit_proof(
        self,
        *,
        principal: Principal,
        submission_id: UUID,
        proof_envelope: Groth16ProofEnvelope,
    ) -> FederationUpdateArtifact:
        """Store one proof envelope, verify it, and retain its non-sensitive receipt."""

        artifact = self._required_owned_artifact(principal, submission_id)
        if artifact.status != UpdateArtifactStatus.SUBMITTED.value:
            raise ConflictError("A Groth16 proof may be submitted only once for a submitted update.")
        if artifact.proof_artifact_reference is not None:
            raise ConflictError("A Groth16 proof was already submitted for this update.")
        federation_round = self._required_round(artifact.federation_round_id)
        if federation_round.status != FederationRoundStatus.OPEN.value:
            raise ConflictError("Groth16 proofs can be submitted only for an open training round.")
        node, agent, participant = self._authorized_participant(principal, federation_round)
        if node.id != artifact.training_node_id or agent.id != artifact.training_agent_id:
            raise ConflictError("Proof submission no longer matches the enrolled training agent.")
        model_version = self._required_model_version(artifact.model_version_id)
        try:
            proof_content = json.dumps(proof_envelope.to_record(), separators=(",", ":")).encode("utf-8")
            if len(proof_content) > self._proof_max_bytes:
                raise FedAvgValidationError("proof_size_invalid", "Groth16 proof envelope exceeds the configured size limit.")
            stored_proof = self._storage.save_proof(
                federation_round_id=federation_round.id,
                submission_id=artifact.id,
                content=proof_content,
            )
            artifact.proof_artifact_reference = stored_proof.storage_reference
            artifact.proof_artifact_sha256 = stored_proof.sha256
            artifact.zk_circuit_version = proof_envelope.circuit_version
            artifact.zk_verification_key_id = proof_envelope.verification_key_id.lower()
            artifact.proof_submitted_at = _now()
            artifact.proof_verification_status = ProofVerificationStatus.PENDING_VERIFICATION.value
            participant.proof_artifact_reference = stored_proof.storage_reference
            participant.proof_verification_status = ProofVerificationStatus.PENDING_VERIFICATION.value
            participant.verification_reason = "Groth16 proof submitted; verification pending."
            content = self._storage.read_update(
                federation_round_id=federation_round.id,
                submission_id=artifact.id,
                max_bytes=self._max_bytes,
            )
            schema = normalize_parameter_schema(model_version.parameter_schema)
            if artifact.artifact_sha256 is None:
                raise FedAvgValidationError(
                    "artifact_binding_mismatch",
                    "Protected update artifact has no pinned SHA-256.",
                )

            try:
                integrity_receipt = verify_pinned_model_update(
                    content,
                    trusted_artifact_sha256=artifact.artifact_sha256,
                    trusted_base_model_commitment=model_version.model_commitment,
                    trusted_parameter_schema=schema,
                    max_bytes=self._max_bytes,
                )
            except UpdateIntegrityError as exc:
                raise FedAvgValidationError(
                    "artifact_binding_mismatch",
                    "Protected update artifact failed full-model integrity verification.",
                ) from exc

            if integrity_receipt.update_commitment != artifact.update_commitment:
                raise FedAvgValidationError(
                    "artifact_binding_mismatch",
                    "Full-model integrity receipt does not match the recorded update.",
                )

            parsed = parse_model_update_archive(
                content,
                expected_schema=schema,
                expected_schema_commitment=model_version.parameter_schema_commitment or "",
                max_bytes=self._max_bytes,
            )
            if (
                parsed.model_version_commitment != model_version.model_commitment
                or parsed.update_commitment != artifact.update_commitment
                or artifact.artifact_sha256 is None
            ):
                raise FedAvgValidationError(
                    "artifact_binding_mismatch",
                    "Protected update artifact no longer matches its recorded provenance.",
                )
            update = ModelUpdate(
                hospital_id=principal.hospital_id,
                training_node_id=node.id,
                sample_count=parsed.sample_count,
                state_dict=parsed.state_dict,
                model_version_commitment=parsed.model_version_commitment,
                hospital_update_commitment=parsed.update_commitment,
                proof_artifact_reference=stored_proof.storage_reference,
                artifact_sha256=artifact.artifact_sha256,
                proof_envelope=proof_envelope,
            )
            validated = self._validate_update(
                federation_round,
                model_version,
                participant,
                artifact,
                update,
            )
        except ProofVerificationError as exc:
            if exc.proof_status is ProofVerificationStatus.PENDING_VERIFICATION:
                self._pending(artifact, participant, str(exc))
                self._repository.commit()
                return artifact
            self._reject(artifact, participant, exc.code, str(exc), exc.proof_status)
        except UpdateArtifactStorageError as exc:
            self._reject(artifact, participant, "proof_storage_failed", str(exc), ProofVerificationStatus.REJECTED)
        except UpdateArchiveError as exc:
            self._reject(artifact, participant, exc.code, str(exc), ProofVerificationStatus.REJECTED)
        except TypeError:
            self._reject(
                artifact,
                participant,
                "malformed_proof",
                "Groth16 proof envelope is invalid.",
                ProofVerificationStatus.REJECTED,
            )
        except FedAvgValidationError as exc:
            self._reject(artifact, participant, exc.code, str(exc), ProofVerificationStatus.REJECTED)
        else:
            receipt = validated.verification_result
            if receipt is None or receipt.status is not ProofVerificationStatus.VERIFIED:
                self._reject(
                    artifact,
                    participant,
                    "proof_not_verified",
                    "Groth16 proof verification did not succeed.",
                    ProofVerificationStatus.REJECTED,
                )
            else:
                artifact.status = UpdateArtifactStatus.ACCEPTED.value
                artifact.proof_verification_status = receipt.status.value
                artifact.zk_circuit_version = receipt.circuit_version
                artifact.zk_verification_key_id = receipt.verification_key_id
                artifact.zk_coverage_complete = receipt.coverage_complete
                artifact.aggregation_eligible = receipt.aggregation_eligible
                artifact.cryptographically_verified_at = _now()
                participant.status = RoundParticipantStatus.ACCEPTED.value
                participant.proof_verification_status = receipt.status.value
                participant.verification_reason = receipt.reason
                participant.submitted_at = artifact.submitted_at
                self._repository.commit()
                return artifact

        self._repository.commit()
        raise FederationUpdateRejectedError(artifact.rejection_reason or "Groth16 proof was rejected.")

    def _validate_update(
        self,
        federation_round: FederationRound,
        model_version: FederationModelVersion,
        participant: FederationRoundParticipant,
        artifact: FederationUpdateArtifact,
        update: ModelUpdate,
    ) -> ValidatedModelUpdate:
        validated = self._validator.validate(
            federation_round=federation_round,
            expected_model_commitment=model_version.model_commitment,
            update=update,
        )
        artifact.proof_verification_status = validated.proof_status.value
        participant.status = RoundParticipantStatus.SUBMITTED.value
        participant.sample_count = update.sample_count
        participant.update_commitment = update.hospital_update_commitment
        participant.proof_artifact_reference = update.proof_artifact_reference
        participant.proof_verification_status = validated.proof_status.value
        participant.verification_reason = validated.verification_reason
        participant.submitted_at = artifact.submitted_at
        return validated

    @staticmethod
    def _pending(
        artifact: FederationUpdateArtifact,
        participant: FederationRoundParticipant,
        reason: str,
    ) -> None:
        artifact.proof_verification_status = ProofVerificationStatus.PENDING_VERIFICATION.value
        participant.status = RoundParticipantStatus.SUBMITTED.value
        participant.proof_verification_status = ProofVerificationStatus.PENDING_VERIFICATION.value
        participant.verification_reason = reason[:256]

    @staticmethod
    def _reject(
        artifact: FederationUpdateArtifact,
        participant: FederationRoundParticipant,
        code: str,
        reason: str,
        proof_status: ProofVerificationStatus,
    ) -> None:
        artifact.status = UpdateArtifactStatus.REJECTED.value
        artifact.rejection_code = code
        artifact.rejection_reason = reason[:256]
        artifact.proof_verification_status = proof_status.value
        artifact.aggregation_eligible = False
        artifact.zk_coverage_complete = False
        artifact.submitted_at = artifact.submitted_at or _now()
        participant.status = RoundParticipantStatus.REJECTED.value
        participant.sample_count = artifact.sample_count
        participant.update_commitment = artifact.update_commitment
        participant.proof_artifact_reference = artifact.proof_artifact_reference
        participant.proof_verification_status = proof_status.value
        participant.verification_reason = reason[:256]
        participant.submitted_at = artifact.submitted_at

    def _authorized_participant(
        self,
        principal: Principal,
        federation_round: FederationRound,
    ) -> tuple[FederationTrainingNode, FederationTrainingAgent, FederationRoundParticipant]:
        node = self._repository.training_node_for_hospital(principal.hospital_id)
        agent = self._repository.training_agent_for_hospital(principal.hospital_id)
        participant = self._repository.participant_for_round_hospital(
            round_id=federation_round.id,
            hospital_id=principal.hospital_id,
        )
        if (
            node is None
            or node.status != "enrolled"
            or agent is None
            or agent.status != TrainingAgentStatus.ENROLLED.value
            or agent.dataset_status not in {"authorized_unvalidated", "geometry_validated"}
            or participant is None
            or participant.training_node_id != node.id
            or agent.training_node_id != node.id
        ):
            raise ResourceNotFoundError("No eligible training-agent participation was found for this hospital.")
        return node, agent, participant

    def _required_round(self, round_id: UUID) -> FederationRound:
        federation_round = self._repository.round(round_id)
        if federation_round is None:
            raise ResourceNotFoundError("The requested training round was not found.")
        return federation_round

    def _required_model_version(self, model_version_id: UUID) -> FederationModelVersion:
        model_version = self._repository.model_version(model_version_id)
        if model_version is None:
            raise ResourceNotFoundError("The requested model version was not found.")
        return model_version

    def _required_owned_artifact(
        self,
        principal: Principal,
        submission_id: UUID,
    ) -> FederationUpdateArtifact:
        artifact = self._repository.update_artifact(submission_id)
        if artifact is None or artifact.hospital_id != principal.hospital_id:
            raise ResourceNotFoundError("The requested update submission was not found.")
        return artifact

    def _commit_or_conflict(self, message: str) -> None:
        try:
            self._repository.commit()
        except IntegrityError as exc:
            self._repository.rollback()
            raise ConflictError(message) from exc
