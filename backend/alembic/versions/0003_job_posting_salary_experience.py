"""add job posting salary and experience fields

Revision ID: 0003_job_salary_experience
Revises: 0002_reco_rank_meta
Create Date: 2026-06-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_job_salary_experience"
down_revision: str | None = "0002_reco_rank_meta"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("job_postings", sa.Column("salary_min", sa.Numeric(12, 2), nullable=True))
    op.add_column("job_postings", sa.Column("salary_max", sa.Numeric(12, 2), nullable=True))
    op.add_column("job_postings", sa.Column("salary_currency", sa.String(length=10), nullable=True))
    op.add_column("job_postings", sa.Column("salary_period", sa.String(length=20), nullable=True))
    op.add_column("job_postings", sa.Column("minimum_experience", sa.String(length=100), nullable=True))
    op.create_index("ix_job_postings_salary_min", "job_postings", ["salary_min"])
    op.create_index("ix_job_postings_salary_max", "job_postings", ["salary_max"])


def downgrade() -> None:
    op.drop_index("ix_job_postings_salary_max", table_name="job_postings")
    op.drop_index("ix_job_postings_salary_min", table_name="job_postings")
    op.drop_column("job_postings", "minimum_experience")
    op.drop_column("job_postings", "salary_period")
    op.drop_column("job_postings", "salary_currency")
    op.drop_column("job_postings", "salary_max")
    op.drop_column("job_postings", "salary_min")
