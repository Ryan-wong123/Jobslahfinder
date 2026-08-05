"""add nullable job comparison metadata

Revision ID: 0010_job_comparison_metadata
Revises: 0009_merge_remaining_heads
Create Date: 2026-08-05
"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "0010_job_comparison_metadata"
down_revision: str | None = "0009_merge_remaining_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FIELDS = (
    ("employment_type", sa.String(length=100)),
    ("workplace_type", sa.String(length=50)),
    ("seniority_level", sa.String(length=100)),
    ("skills", sa.JSON()),
    ("closing_date", sa.Date()),
)


def upgrade() -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("job_postings")}
    for name, column_type in FIELDS:
        if name not in existing:
            op.add_column("job_postings", sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("job_postings")}
    for name, _ in reversed(FIELDS):
        if name in existing:
            op.drop_column("job_postings", name)
