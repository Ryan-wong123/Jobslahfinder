"""add job posting minimum experience

Revision ID: 0007_job_min_experience
Revises: 0006_repair_role_roadmaps
Create Date: 2026-06-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_job_min_experience"
down_revision: str | None = "0006_repair_role_roadmaps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("job_postings", sa.Column("minimum_experience", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("job_postings", "minimum_experience")
