"""Safe coordinator and historical-evidence schemas for federation APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class TrainingNodeEnrollmentRequest(BaseModel):
    """Explicit self-enrollment request for the caller's active hospital."""

    node_identifier: str = Field(min_length=3, max_length=160, pattern=r"^[A-Za-z0-9._:-]+$")


class TrainingNodeEnrollmentResponse(BaseModel):
    """Enrollment metadata; no network address or dataset claim is returned."""

    id: UUID
    hospital_id: UUID
    node_identifier: str
    status: Literal["enrolled", "disabled"]
    dataset_availability: Literal["not_declared"] = "not_declared"
    created_at: datetime
    updated_at: datetime


class TrainingAgentEnrollmentRequest(BaseModel):
    """Explicit enrollment of a hospital-local agent after node enrollment."""

    agent_identifier: str = Field(min_length=3, max_length=160, pattern=r"^[A-Za-z0-9._:-]+$")


class TrainingAgentResponse(BaseModel):
    """Safe training-agent state with no local path or MRI content."""

    id: UUID
    hospital_id: UUID
    training_node_id: UUID
    agent_identifier: str
    status: Literal["enrolled", "disabled"]
    authorized_case_reference: str | None
    dataset_status: Literal[
        "authorized_unvalidated",
        "geometry_validated",
        "not_approved",
        "unavailable",
    ]
    training_execution_enabled: bool
    created_at: datetime
    updated_at: datetime


class ModelVersionCreateRequest(BaseModel):
    """Operator-only immutable base-model metadata registration."""

    label: str = Field(min_length=3, max_length=160, pattern=r"^[A-Za-z0-9._:-]+$")
    model_commitment: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$")
    artifact_reference: str | None = Field(default=None, max_length=512)
    parameter_schema: list["ParameterSchemaEntry"] | None = Field(default=None, max_length=1000)

    @field_validator("artifact_reference")
    @classmethod
    def reject_filesystem_paths(cls, value: str | None) -> str | None:
        """References are opaque metadata, never arbitrary server file paths."""

        if value is not None and (value.startswith("/") or ".." in value):
            raise ValueError("artifact_reference must not be a filesystem path.")
        return value


class ParameterSchemaEntry(BaseModel):
    """Public name/shape/dtype metadata for a model state entry."""

    name: str = Field(min_length=1, max_length=512)
    shape: list[int] = Field(max_length=8)
    dtype: str = Field(min_length=1, max_length=32)

    @field_validator("shape")
    @classmethod
    def require_non_negative_shape(cls, value: list[int]) -> list[int]:
        if any(dimension < 0 for dimension in value):
            raise ValueError("Parameter shapes must be non-negative.")
        return value


class ModelVersionResponse(BaseModel):
    """Public-safe provenance for one registered coordinator model version."""

    id: UUID
    label: str
    model_commitment: str
    parent_model_version_id: UUID | None
    artifact_reference: str | None
    artifact_sha256: str | None
    parameter_schema_commitment: str | None
    parameter_schema_available: bool
    created_at: datetime


class TrainingRoundCreateRequest(BaseModel):
    """Operator-only creation of a draft custom-coordinator training round."""

    base_model_version_id: UUID
    participant_hospital_ids: list[UUID] = Field(min_length=1, max_length=100)
    requires_zk_verification: bool = True
    research_mode: bool = False

    @model_validator(mode="after")
    def require_research_label_for_non_zk(self) -> "TrainingRoundCreateRequest":
        if not self.requires_zk_verification and not self.research_mode:
            raise ValueError("Non-ZK aggregation is allowed only for a labeled research round.")
        if len(set(self.participant_hospital_ids)) != len(self.participant_hospital_ids):
            raise ValueError("participant_hospital_ids must not contain duplicates.")
        return self


class UpdatePreparationRequest(BaseModel):
    """Bind a single hospital-local submission slot to the round base model."""

    model_version_id: UUID


class Groth16ChunkProofRequest(BaseModel):
    """One public proof object and the seven V2 public signals."""

    proof: dict[str, object]
    public_signals: list[str] = Field(min_length=7, max_length=7)

    @field_validator("public_signals")
    @classmethod
    def require_bounded_signal_strings(cls, value: list[str]) -> list[str]:
        if any(len(item) > 80 or not item.isascii() for item in value):
            raise ValueError("Groth16 public signals must be bounded ASCII decimal strings.")
        return value


class Groth16ProofSubmissionRequest(BaseModel):
    """A circuit-pinned proof envelope; clients never supply a verification key."""

    circuit_version: str = Field(min_length=3, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")
    verification_key_id: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$")
    proofs: list[Groth16ChunkProofRequest] = Field(min_length=1, max_length=128)


class UpdateArtifactResponse(BaseModel):
    """Safe submission outcome; raw tensors and local paths are never returned."""

    id: UUID
    federation_round_id: UUID
    hospital_id: UUID
    training_node_id: UUID
    training_agent_id: UUID
    model_version_id: UUID
    status: Literal["prepared", "submitted", "accepted", "rejected"]
    artifact_sha256: str | None
    artifact_size_bytes: int | None
    update_commitment: str | None
    parameter_schema_commitment: str | None
    sample_count: int | None
    proof_artifact_reference: str | None
    proof_artifact_sha256: str | None
    proof_verification_status: Literal[
        "not_submitted",
        "pending_verification",
        "verified",
        "rejected",
    ]
    training_metadata_recorded: bool
    aggregation_eligible: bool
    proof_lifecycle: Literal[
        "prepared",
        "submitted",
        "awaiting_proof",
        "verification_pending",
        "cryptographically_verified",
        "rejected",
    ]
    zk_circuit_version: str | None
    zk_verification_key_id: str | None
    zk_coverage_complete: bool
    rejection_code: str | None
    rejection_reason: str | None
    prepared_at: datetime
    submitted_at: datetime | None


class TrainingRoundParticipantResponse(BaseModel):
    """Non-sensitive state for one participant; no update tensors are exposed."""

    hospital_id: UUID
    status: Literal["invited", "submitted", "accepted", "rejected"]
    sample_count: int | None
    update_commitment: str | None
    proof_artifact_reference: str | None
    proof_verification_status: Literal[
        "not_submitted",
        "pending_verification",
        "verified",
        "rejected",
    ]
    verification_reason: str | None
    submitted_at: datetime | None


class TrainingRoundResponse(BaseModel):
    """Round status and public commitments suitable for the administrator UI."""

    id: UUID
    base_model_version_id: UUID
    global_model_version_id: UUID | None
    status: Literal["draft", "open", "aggregating", "completed", "failed"]
    requires_zk_verification: bool
    research_mode: bool
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    participants: list[TrainingRoundParticipantResponse] = Field(default_factory=list)


class CoordinatorHospitalResponse(BaseModel):
    """Dynamic hospital discovery with explicit enrollment state."""

    hospital_name: str
    hospital_slug: str
    registered: bool = True
    training_node_status: Literal["not_enrolled", "enrolled", "disabled"]
    training_agent_status: Literal["not_enrolled", "enrolled", "disabled"]
    dataset_availability: Literal[
        "authorized_unvalidated",
        "geometry_validated",
        "not_approved",
        "unavailable",
    ]
    training_readiness: Literal[
        "not_ready_missing_node",
        "not_ready_missing_agent",
        "not_ready_dataset_unvalidated",
        "not_ready_no_dataset",
        "execution_disabled",
        "execution_authorization_required",
    ]


class CoordinatorReadinessResponse(BaseModel):
    """Truthful feature readiness, including the fail-closed verifier state."""

    database_backed: bool
    checkpoint_storage_configured: bool
    update_storage_configured: bool
    groth16_verifier: Literal["unavailable", "development_only", "production_ready"]
    production_aggregation: Literal["blocked_pending_groth16_verifier"]


class GlobalCheckpointResponse(BaseModel):
    """Provenance of a new custom-coordinator global checkpoint."""

    federation_round_id: UUID
    model_version_id: UUID
    storage_reference: str
    checkpoint_sha256: str
    size_bytes: int
    aggregation_algorithm: str
    participant_count: int
    total_sample_count: int
    created_at: datetime


class OwnLocalTrainingEvidenceResponse(BaseModel):
    """Legacy Flower evidence fields; not active coordinator state."""

    epochs: int | None = None
    training_loss: float | None = None
    training_seconds: float | None = None
    patch_size: list[int] | None = None
    federated_round_completed: bool = False
    purpose: str | None = None


class FederationHospitalResponse(BaseModel):
    """Legacy Flower evidence projection, retained separately from coordinator APIs."""

    hospital_name: str
    hospital_slug: str
    registered: bool = True
    flower_node_configured: bool = False
    flower_node_port: int | None = None
    flower_node_online: bool = False
    local_training_evidence_available: bool = False
    participated_in_fedavg_abc: bool = False
    own_local_training: OwnLocalTrainingEvidenceResponse | None = None
