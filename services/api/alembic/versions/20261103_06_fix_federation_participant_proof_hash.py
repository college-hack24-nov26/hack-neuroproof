"""Add missing proof artifact hash to federation round participants.

Revision ID: 20261103_06
Revises: 20261103_05
"""

from alembic import op
import sqlalchemy as sa


revision = "20261103_06"
down_revision = "20261103_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "federation_round_participants",
        sa.Column(
            "proof_artifact_sha256",
            sa.String(length=64),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "federation_round_participants",
        "proof_artifact_sha256",
    )
