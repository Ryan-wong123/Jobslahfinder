"""add normalized job detail fields

Revision ID: 0010_job_normalized_details
Revises: 0009_merge_remaining_heads
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_job_normalized_details"
down_revision: str | None = "0009_merge_remaining_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("job_postings", sa.Column("minimum_experience_years", sa.Integer(), nullable=True))
    op.add_column("job_postings", sa.Column("employment_type", sa.String(length=30), nullable=True))
    op.add_column("job_postings", sa.Column("workplace_type", sa.String(length=20), nullable=True))
    op.add_column("job_postings", sa.Column("seniority_level", sa.String(length=20), nullable=True))
    op.add_column("job_postings", sa.Column("skills", sa.JSON(), nullable=True))
    op.add_column("job_postings", sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("job_postings", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "job_postings_experience_years_range",
        "job_postings",
        "minimum_experience_years IS NULL OR (minimum_experience_years >= 0 AND minimum_experience_years <= 50)",
    )
    op.create_check_constraint(
        "job_postings_employment_type_allowed",
        "job_postings",
        "employment_type IS NULL OR employment_type IN ('FULL_TIME','PART_TIME','CONTRACT','TEMPORARY','INTERNSHIP','FREELANCE')",
    )
    op.create_check_constraint(
        "job_postings_workplace_type_allowed",
        "job_postings",
        "workplace_type IS NULL OR workplace_type IN ('ONSITE','HYBRID','REMOTE')",
    )
    op.create_check_constraint(
        "job_postings_seniority_level_allowed",
        "job_postings",
        "seniority_level IS NULL OR seniority_level IN ('ENTRY','JUNIOR','MID','SENIOR','LEAD','MANAGER','DIRECTOR','EXECUTIVE')",
    )
    op.execute("UPDATE job_postings SET posted_at = posting_date WHERE posting_date IS NOT NULL")
    op.create_index("ix_job_postings_posted_at", "job_postings", ["posted_at"])


def downgrade() -> None:
    op.drop_index("ix_job_postings_posted_at", table_name="job_postings")
    op.drop_constraint("job_postings_seniority_level_allowed", "job_postings", type_="check")
    op.drop_constraint("job_postings_workplace_type_allowed", "job_postings", type_="check")
    op.drop_constraint("job_postings_employment_type_allowed", "job_postings", type_="check")
    op.drop_constraint("job_postings_experience_years_range", "job_postings", type_="check")
    for column in (
        "expires_at", "posted_at", "skills", "seniority_level", "workplace_type",
        "employment_type", "minimum_experience_years",
    ):
        op.drop_column("job_postings", column)
