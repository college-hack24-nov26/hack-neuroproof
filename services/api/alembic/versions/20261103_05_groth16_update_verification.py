"""Add Groth16 proof receipts to protected federation-update metadata.

Revision ID: 20261103_05
Revises: 20261102_04
Create Date: 2026-11-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261103_05"
down_revision = "20261102_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add only nullable/false-default proof receipt fields; preserve all records."""

    op.add_column(
        "federation_update_artifacts",
        sa.Column("proof_artifact_sha256", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "federation_update_artifacts",
        sa.Column("zk_circuit_version", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "federation_update_artifacts",
        sa.Column("zk_verification_key_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "federation_update_artifacts",
        sa.Column(
            "zk_coverage_complete",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "federation_update_artifacts",
        sa.Column(
            "aggregation_eligible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "federation_update_artifacts",
        sa.Column("proof_submitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "federation_update_artifacts",
        sa.Column("cryptographically_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_constraint(
        "ck_federation_update_artifact_status",
        "federation_update_artifacts",
        type_="check",
    )
    op.create_check_constraint(
        "ck_federation_update_artifact_status",
        "federation_update_artifacts",
        "status IN ('prepared', 'submitted', 'accepted', 'rejected')",
    )
    op.create_index(
        "ix_federation_update_artifacts_zk_verification_key_id",
        "federation_update_artifacts",
        ["zk_verification_key_id"],
    )


def downgrade() -> None:
    """Reverse Phase 3 metadata only during an explicitly approved rollback."""

    op.drop_index(
        "ix_federation_update_artifacts_zk_verification_key_id",
        table_name="federation_update_artifacts",
    )
    op.drop_constraint(
        "ck_federation_update_artifact_status",
        "federation_update_artifacts",
        type_="check",
    )
    op.create_check_constraint(
        "ck_federation_update_artifact_status",
        "federation_update_artifacts",
        "status IN ('prepared', 'accepted', 'rejected')",
    )
    op.drop_column("federation_update_artifacts", "cryptographically_verified_at")
    op.drop_column("federation_update_artifacts", "proof_submitted_at")
    op.drop_column("federation_update_artifacts", "aggregation_eligible")
    op.drop_column("federation_update_artifacts", "zk_coverage_complete")
    op.drop_column("federation_update_artifacts", "zk_verification_key_id")
    op.drop_column("federation_update_artifacts", "zk_circuit_version")
    op.drop_column("federation_update_artifacts", "proof_artifact_sha256")
