"""Create hospital identity and MRI ownership tables.

Revision ID: 20261101_01
Revises:
Create Date: 2026-11-01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261101_01"
down_revision = None
branch_labels = None
depends_on = None


hospital_role = sa.Enum("hospital_admin", "doctor", name="hospital_role")
mri_job_state = sa.Enum("queued", "running", "completed", "failed", name="mri_job_state")


def upgrade() -> None:
    """Create the minimum PostgreSQL tables for scoped authentication and MRI metadata."""

    op.create_table(
        "hospitals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_hospitals_slug", "hospitals", ["slug"], unique=False)
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    op.create_table(
        "hospital_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("hospital_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", hospital_role, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["hospital_id"], ["hospitals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hospital_id", "user_id", name="uq_membership_hospital_user"),
    )
    op.create_index("ix_hospital_memberships_hospital_id", "hospital_memberships", ["hospital_id"])
    op.create_index("ix_hospital_memberships_user_id", "hospital_memberships", ["user_id"])
    op.create_table(
        "mri_cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("hospital_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("case_reference", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["hospital_id"], ["hospitals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mri_cases_hospital_id", "mri_cases", ["hospital_id"])
    op.create_table(
        "mri_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("hospital_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("mri_case_id", sa.Uuid(), nullable=True),
        sa.Column("status", mri_job_state, nullable=False),
        sa.Column("artifact_reference", sa.String(length=512), nullable=True),
        sa.Column("model_sha256", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["hospital_id"], ["hospitals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mri_case_id"], ["mri_cases.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mri_jobs_hospital_id", "mri_jobs", ["hospital_id"])
    op.create_index("ix_mri_jobs_mri_case_id", "mri_jobs", ["mri_case_id"])


def downgrade() -> None:
    """Drop Phase 3 tenancy tables and their owned PostgreSQL enum types."""

    op.drop_index("ix_mri_jobs_mri_case_id", table_name="mri_jobs")
    op.drop_index("ix_mri_jobs_hospital_id", table_name="mri_jobs")
    op.drop_table("mri_jobs")
    op.drop_index("ix_mri_cases_hospital_id", table_name="mri_cases")
    op.drop_table("mri_cases")
    op.drop_index("ix_hospital_memberships_user_id", table_name="hospital_memberships")
    op.drop_index("ix_hospital_memberships_hospital_id", table_name="hospital_memberships")
    op.drop_table("hospital_memberships")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.drop_index("ix_hospitals_slug", table_name="hospitals")
    op.drop_table("hospitals")
    mri_job_state.drop(op.get_bind(), checkfirst=True)
    hospital_role.drop(op.get_bind(), checkfirst=True)
