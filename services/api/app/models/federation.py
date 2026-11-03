"""PostgreSQL metadata for the custom federated-learning coordinator."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.auth import utc_now


class FederationTrainingNode(Base):
    """An explicit coordinator enrollment; registration alone never creates one."""

    __tablename__ = "federation_training_nodes"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    hospital_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("hospitals.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    node_identifier: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="enrolled")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class FederationModelVersion(Base):
    """Immutable model-version commitment and protected artifact provenance."""

    __tablename__ = "federation_model_versions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    label: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    model_commitment: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    parent_model_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("federation_model_versions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    artifact_reference: Mapped[str | None] = mapped_column(String(512), nullable=True)
    artifact_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parameter_schema: Mapped[list[dict[str, object]] | None] = mapped_column(JSON, nullable=True)
    parameter_schema_commitment: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class FederationRound(Base):
    """A coordinator-controlled training round without private model data."""

    __tablename__ = "federation_rounds"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    base_model_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("federation_model_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    global_model_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("federation_model_versions.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    requires_zk_verification: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    research_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failure_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    base_model_version: Mapped[FederationModelVersion] = relationship(
        foreign_keys=[base_model_version_id],
    )
    global_model_version: Mapped[FederationModelVersion | None] = relationship(
        foreign_keys=[global_model_version_id],
    )


class FederationRoundParticipant(Base):
    """One hospital's non-sensitive update/proof metadata for a round."""

    __tablename__ = "federation_round_participants"
    __table_args__ = (
        UniqueConstraint("federation_round_id", "hospital_id", name="uq_federation_round_hospital"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    federation_round_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("federation_rounds.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    hospital_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("hospitals.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    training_node_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("federation_training_nodes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="invited")
    sample_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    update_commitment: Mapped[str | None] = mapped_column(String(64), nullable=True)
    proof_artifact_reference: Mapped[str | None] = mapped_column(String(512), nullable=True)
    proof_artifact_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    proof_verification_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="not_submitted",
    )
    verification_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    federation_round: Mapped[FederationRound] = relationship()


class FederationGlobalCheckpoint(Base):
    """Metadata and integrity hash for a newly saved coordinator checkpoint."""

    __tablename__ = "federation_global_checkpoints"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    federation_round_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("federation_rounds.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    model_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("federation_model_versions.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    storage_reference: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    checkpoint_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    aggregation_algorithm: Mapped[str] = mapped_column(String(64), nullable=False)
    participant_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    model_version: Mapped[FederationModelVersion] = relationship()


class FederationTrainingAgent(Base):
    """A hospital-local training agent enrollment without local dataset paths."""

    __tablename__ = "federation_training_agents"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    hospital_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("hospitals.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    training_node_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("federation_training_nodes.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    agent_identifier: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="enrolled")
    authorized_case_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    dataset_status: Mapped[str] = mapped_column(String(48), nullable=False)
    training_execution_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class FederationUpdateArtifact(Base):
    """Private-update provenance without serialized tensors in PostgreSQL."""

    __tablename__ = "federation_update_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "federation_round_id",
            "hospital_id",
            name="uq_federation_update_round_hospital",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    federation_round_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("federation_rounds.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    hospital_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("hospitals.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    training_node_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("federation_training_nodes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    training_agent_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("federation_training_agents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    model_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("federation_model_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="prepared")
    artifact_reference: Mapped[str | None] = mapped_column(String(512), nullable=True, unique=True)
    artifact_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    artifact_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    update_commitment: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parameter_schema_commitment: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sample_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    proof_artifact_reference: Mapped[str | None] = mapped_column(String(512), nullable=True)
    proof_artifact_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    proof_verification_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="not_submitted",
    )
    zk_circuit_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    zk_verification_key_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    zk_coverage_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    aggregation_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    training_metadata: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    rejection_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    prepared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    proof_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cryptographically_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
