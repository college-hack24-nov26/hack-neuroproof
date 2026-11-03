"""Add isolated metadata tables for the custom federated-learning coordinator.

Revision ID: 20261102_03
Revises: 20261102_02
Create Date: 2026-11-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261102_03"
down_revision = "20261102_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create additive coordinator records without touching historical evidence."""

    op.create_table(
        "federation_training_nodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("hospital_id", sa.Uuid(), nullable=False),
        sa.Column("node_identifier", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('enrolled', 'disabled')", name="ck_federation_training_node_status"),
        sa.ForeignKeyConstraint(["hospital_id"], ["hospitals.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hospital_id"),
        sa.UniqueConstraint("node_identifier"),
    )
    op.create_index("ix_federation_training_nodes_hospital_id", "federation_training_nodes", ["hospital_id"])

    op.create_table(
        "federation_model_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("model_commitment", sa.String(length=64), nullable=False),
        sa.Column("parent_model_version_id", sa.Uuid(), nullable=True),
        sa.Column("artifact_reference", sa.String(length=512), nullable=True),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("char_length(model_commitment) = 64", name="ck_federation_model_commitment_length"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["parent_model_version_id"],
            ["federation_model_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("label"),
        sa.UniqueConstraint("model_commitment"),
    )
    op.create_index(
        "ix_federation_model_versions_parent_model_version_id",
        "federation_model_versions",
        ["parent_model_version_id"],
    )

    op.create_table(
        "federation_rounds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("base_model_version_id", sa.Uuid(), nullable=False),
        sa.Column("global_model_version_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requires_zk_verification", sa.Boolean(), nullable=False),
        sa.Column("research_mode", sa.Boolean(), nullable=False),
        sa.Column("failure_reason", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'open', 'aggregating', 'completed', 'failed')",
            name="ck_federation_round_status",
        ),
        sa.CheckConstraint(
            "requires_zk_verification OR research_mode",
            name="ck_federation_round_non_zk_research_only",
        ),
        sa.ForeignKeyConstraint(["base_model_version_id"], ["federation_model_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["global_model_version_id"], ["federation_model_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("global_model_version_id"),
    )
    op.create_index("ix_federation_rounds_base_model_version_id", "federation_rounds", ["base_model_version_id"])
    op.create_index("ix_federation_rounds_status", "federation_rounds", ["status"])

    op.create_table(
        "federation_round_participants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("federation_round_id", sa.Uuid(), nullable=False),
        sa.Column("hospital_id", sa.Uuid(), nullable=False),
        sa.Column("training_node_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=True),
        sa.Column("update_commitment", sa.String(length=64), nullable=True),
        sa.Column("proof_artifact_reference", sa.String(length=512), nullable=True),
        sa.Column("proof_verification_status", sa.String(length=32), nullable=False),
        sa.Column("verification_reason", sa.String(length=256), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('invited', 'submitted', 'accepted', 'rejected')",
            name="ck_federation_participant_status",
        ),
        sa.CheckConstraint(
            "proof_verification_status IN ('not_submitted', 'pending_verification', 'verified', 'rejected')",
            name="ck_federation_proof_status",
        ),
        sa.ForeignKeyConstraint(["federation_round_id"], ["federation_rounds.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["hospital_id"], ["hospitals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["training_node_id"], ["federation_training_nodes.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("federation_round_id", "hospital_id", name="uq_federation_round_hospital"),
    )
    op.create_index(
        "ix_federation_round_participants_federation_round_id",
        "federation_round_participants",
        ["federation_round_id"],
    )
    op.create_index(
        "ix_federation_round_participants_hospital_id",
        "federation_round_participants",
        ["hospital_id"],
    )

    op.create_table(
        "federation_global_checkpoints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("federation_round_id", sa.Uuid(), nullable=False),
        sa.Column("model_version_id", sa.Uuid(), nullable=False),
        sa.Column("storage_reference", sa.String(length=512), nullable=False),
        sa.Column("checkpoint_sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("aggregation_algorithm", sa.String(length=64), nullable=False),
        sa.Column("participant_count", sa.Integer(), nullable=False),
        sa.Column("total_sample_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("size_bytes > 0", name="ck_federation_checkpoint_size"),
        sa.CheckConstraint("participant_count > 0", name="ck_federation_checkpoint_participants"),
        sa.CheckConstraint("total_sample_count > 0", name="ck_federation_checkpoint_samples"),
        sa.ForeignKeyConstraint(["federation_round_id"], ["federation_rounds.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["model_version_id"], ["federation_model_versions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("federation_round_id"),
        sa.UniqueConstraint("model_version_id"),
        sa.UniqueConstraint("storage_reference"),
        sa.UniqueConstraint("checkpoint_sha256"),
    )


def downgrade() -> None:
    """Remove only coordinator metadata when an explicit rollback is approved."""

    op.drop_table("federation_global_checkpoints")
    op.drop_index("ix_federation_round_participants_hospital_id", table_name="federation_round_participants")
    op.drop_index("ix_federation_round_participants_federation_round_id", table_name="federation_round_participants")
    op.drop_table("federation_round_participants")
    op.drop_index("ix_federation_rounds_status", table_name="federation_rounds")
    op.drop_index("ix_federation_rounds_base_model_version_id", table_name="federation_rounds")
    op.drop_table("federation_rounds")
    op.drop_index(
        "ix_federation_model_versions_parent_model_version_id",
        table_name="federation_model_versions",
    )
    op.drop_table("federation_model_versions")
    op.drop_index("ix_federation_training_nodes_hospital_id", table_name="federation_training_nodes")
    op.drop_table("federation_training_nodes")
