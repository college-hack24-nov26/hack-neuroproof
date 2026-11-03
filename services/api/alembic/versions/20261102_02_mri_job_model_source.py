"""Persist selected MRI checkpoint provenance for completed hospital jobs.

Revision ID: 20261102_02
Revises: 20261101_01
Create Date: 2026-11-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261102_02"
down_revision = "20261101_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add a non-destructive provenance column; historical jobs are local."""

    op.add_column(
        "mri_jobs",
        sa.Column(
            "model_source",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'local'"),
        ),
    )


def downgrade() -> None:
    """Remove only the derived provenance column when explicitly rolling back."""

    op.drop_column("mri_jobs", "model_source")
