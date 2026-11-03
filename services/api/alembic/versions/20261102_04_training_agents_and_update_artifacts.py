"""Add custom training-agent and protected update-artifact metadata.

Revision ID: 20261102_04
Revises: 20261102_03
Create Date: 2026-11-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261102_04"
down_revision = "20261102_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add isolated coordinator metadata without altering historical records."""

    op.add_column(
        "federation_model_versions",
        sa.Column("parameter_schema", sa.JSON(), nullable=True),
    )
    op.add_column(
        "federation_model_versions",
        sa.Column("parameter_schema_commitment", sa.String(length=64), nullable=True),
    )
    op.create_table(
        "federation_training_agents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("hospital_id", sa.Uuid(), nullable=False),
        sa.Column("training_node_id", sa.Uuid(), nullable=False),
        sa.Column("agent_identifier", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("authorized_case_reference", sa.String(length=160), nullable=True),
        sa.Column("dataset_status", sa.String(length=48), nullable=False),
        sa.Column("training_execution_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('enrolled', 'disabled')",
            name="ck_federation_training_agent_status",
        ),
        sa.CheckConstraint(
            "dataset_status IN ('authorized_unvalidated', 'geometry_validated', 'not_approved', 'unavailable')",
            name="ck_federation_training_agent_dataset_status",
        ),
        sa.ForeignKeyConstraint(["hospital_id"], ["hospitals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["training_node_id"],
            ["federation_training_nodes.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hospital_id"),
        sa.UniqueConstraint("training_node_id"),
        sa.UniqueConstraint("agent_identifier"),
    )
    op.create_index(
        "ix_federation_training_agents_hospital_id",
        "federation_training_agents",
        ["hospital_id"],
    )
    op.create_table(
        "federation_update_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("federation_round_id", sa.Uuid(), nullable=False),
        sa.Column("hospital_id", sa.Uuid(), nullable=False),
        sa.Column("training_node_id", sa.Uuid(), nullable=False),
        sa.Column("training_agent_id", sa.Uuid(), nullable=False),
        sa.Column("model_version_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("artifact_reference", sa.String(length=512), nullable=True),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=True),
        sa.Column("artifact_size_bytes", sa.Integer(), nullable=True),
        sa.Column("update_commitment", sa.String(length=64), nullable=True),
        sa.Column("parameter_schema_commitment", sa.String(length=64), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=True),
        sa.Column("proof_artifact_reference", sa.String(length=512), nullable=True),
        sa.Column("proof_verification_status", sa.String(length=32), nullable=False),
        sa.Column("training_metadata", sa.JSON(), nullable=True),
        sa.Column("rejection_code", sa.String(length=80), nullable=True),
        sa.Column("rejection_reason", sa.String(length=256), nullable=True),
        sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('prepared', 'accepted', 'rejected')",
            name="ck_federation_update_artifact_status",
        ),
        sa.CheckConstraint(
            "proof_verification_status IN ('not_submitted', 'pending_verification', 'verified', 'rejected')",
            name="ck_federation_update_artifact_proof_status",
        ),
        sa.CheckConstraint(
            "sample_count IS NULL OR sample_count > 0",
            name="ck_federation_update_artifact_sample_count",
        ),
        sa.ForeignKeyConstraint(["federation_round_id"], ["federation_rounds.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["hospital_id"], ["hospitals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["training_node_id"],
            ["federation_training_nodes.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["training_agent_id"],
            ["federation_training_agents.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["federation_model_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "federation_round_id",
            "hospital_id",
            name="uq_federation_update_round_hospital",
        ),
        sa.UniqueConstraint("artifact_reference"),
        sa.UniqueConstraint("artifact_sha256"),
    )
    op.create_index(
        "ix_federation_update_artifacts_federation_round_id",
        "federation_update_artifacts",
        ["federation_round_id"],
    )
    op.create_index(
        "ix_federation_update_artifacts_hospital_id",
        "federation_update_artifacts",
        ["hospital_id"],
    )


def downgrade() -> None:
    """Remove only Phase 2 metadata tables during an explicit approved rollback."""

    op.drop_index(
        "ix_federation_update_artifacts_hospital_id",
        table_name="federation_update_artifacts",
    )
    op.drop_index(
        "ix_federation_update_artifacts_federation_round_id",
        table_name="federation_update_artifacts",
    )
    op.drop_table("federation_update_artifacts")
    op.drop_index(
        "ix_federation_training_agents_hospital_id",
        table_name="federation_training_agents",
    )
    op.drop_table("federation_training_agents")
    op.drop_column("federation_model_versions", "parameter_schema_commitment")
    op.drop_column("federation_model_versions", "parameter_schema")
