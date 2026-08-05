"""add normalized job detail fields

Revision ID: 0010_job_detail_fields
Revises: 0009_merge_remaining_heads
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_job_detail_fields"
down_revision: str | None = "0009_merge_remaining_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("job_postings", sa.Column("minimum_experience_years", sa.Integer(), nullable=True))
    op.add_column("job_postings", sa.Column("employment_type", sa.String(length=30), nullable=True))
    op.add_column("job_postings", sa.Column("workplace_type", sa.String(length=20), nullable=True))
    op.add_column("job_postings", sa.Column("seniority_level", sa.String(length=20), nullable=True))
    op.add_column("job_postings", sa.Column("skills", sa.JSON(), nullable=True))
    op.add_column("job_postings", sa.Column("expires_at", sa.Date(), nullable=True))
    op.create_check_constraint(
        "job_postings_experience_years_range",
        "job_postings",
        "minimum_experience_years is null or (minimum_experience_years >= 0 and minimum_experience_years <= 60)",
    )
    op.create_check_constraint(
        "job_postings_employment_type_allowed",
        "job_postings",
        "employment_type is null or employment_type in ('FULL_TIME', 'PART_TIME', 'CONTRACT', 'TEMPORARY', 'INTERNSHIP')",
    )
    op.create_check_constraint(
        "job_postings_workplace_type_allowed",
        "job_postings",
        "workplace_type is null or workplace_type in ('ONSITE', 'HYBRID', 'REMOTE')",
    )
    op.create_check_constraint(
        "job_postings_seniority_level_allowed",
        "job_postings",
        "seniority_level is null or seniority_level in ('ENTRY', 'JUNIOR', 'MID', 'SENIOR', 'LEAD', 'MANAGER', 'DIRECTOR', 'EXECUTIVE')",
    )
    op.create_index("ix_job_postings_expires_at", "job_postings", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_job_postings_expires_at", table_name="job_postings")
    op.drop_constraint("job_postings_seniority_level_allowed", "job_postings", type_="check")
    op.drop_constraint("job_postings_workplace_type_allowed", "job_postings", type_="check")
    op.drop_constraint("job_postings_employment_type_allowed", "job_postings", type_="check")
    op.drop_constraint("job_postings_experience_years_range", "job_postings", type_="check")
    op.drop_column("job_postings", "expires_at")
    op.drop_column("job_postings", "skills")
    op.drop_column("job_postings", "seniority_level")
    op.drop_column("job_postings", "workplace_type")
    op.drop_column("job_postings", "employment_type")
    op.drop_column("job_postings", "minimum_experience_years")
