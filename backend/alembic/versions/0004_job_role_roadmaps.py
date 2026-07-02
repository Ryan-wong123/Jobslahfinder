"""add job role roadmaps

Revision ID: 0004_job_role_roadmaps
Revises: 0003_job_salary_experience
Create Date: 2026-06-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_job_role_roadmaps"
down_revision: str | None = "0003_job_salary_experience"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_role_roadmaps",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("target_role", sa.String(length=120), nullable=False),
        sa.Column("target_level", sa.String(length=40), nullable=False),
        sa.Column("timeline_months", sa.Integer(), nullable=False),
        sa.Column("current_skills_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("roadmap_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status in ('ACTIVE', 'ARCHIVED')", name="job_role_roadmaps_status_allowed"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_role_roadmaps_user_id", "job_role_roadmaps", ["user_id"])
    op.create_index("ix_job_role_roadmaps_target_role", "job_role_roadmaps", ["target_role"])
    op.create_index("ix_job_role_roadmaps_status", "job_role_roadmaps", ["status"])
    op.create_index("ix_job_role_roadmaps_created_at", "job_role_roadmaps", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_job_role_roadmaps_created_at", table_name="job_role_roadmaps")
    op.drop_index("ix_job_role_roadmaps_status", table_name="job_role_roadmaps")
    op.drop_index("ix_job_role_roadmaps_target_role", table_name="job_role_roadmaps")
    op.drop_index("ix_job_role_roadmaps_user_id", table_name="job_role_roadmaps")
    op.drop_table("job_role_roadmaps")
