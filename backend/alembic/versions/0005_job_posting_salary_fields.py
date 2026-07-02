"""add job posting salary fields

Revision ID: 0005_job_salary_fields
Revises: 0004_ensure_role_roadmaps
Create Date: 2026-06-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_job_salary_fields"
down_revision: str | None = "0004_ensure_role_roadmaps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("job_postings")}
    existing_indexes = {index["name"] for index in inspector.get_indexes("job_postings")}

    if "salary_min" not in existing_columns:
        op.add_column("job_postings", sa.Column("salary_min", sa.Numeric(12, 2), nullable=True))
    if "salary_max" not in existing_columns:
        op.add_column("job_postings", sa.Column("salary_max", sa.Numeric(12, 2), nullable=True))
    if "salary_currency" not in existing_columns:
        op.add_column("job_postings", sa.Column("salary_currency", sa.String(length=10), nullable=True))
    if "salary_period" not in existing_columns:
        op.add_column("job_postings", sa.Column("salary_period", sa.String(length=20), nullable=True))
    if "ix_job_postings_salary_min" not in existing_indexes:
        op.create_index("ix_job_postings_salary_min", "job_postings", ["salary_min"])
    if "ix_job_postings_salary_max" not in existing_indexes:
        op.create_index("ix_job_postings_salary_max", "job_postings", ["salary_max"])


def downgrade() -> None:
    op.drop_index("ix_job_postings_salary_max", table_name="job_postings")
    op.drop_index("ix_job_postings_salary_min", table_name="job_postings")
    op.drop_column("job_postings", "salary_period")
    op.drop_column("job_postings", "salary_currency")
    op.drop_column("job_postings", "salary_max")
    op.drop_column("job_postings", "salary_min")
