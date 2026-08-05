"""add nullable job posting metadata

Revision ID: 0010_job_nullable_metadata
Revises: 0009_merge_remaining_heads
"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "0010_job_nullable_metadata"
down_revision: str | None = "0009_merge_remaining_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("job_postings")}
    columns = (
        sa.Column("employment_type", sa.String(100), nullable=True),
        sa.Column("workplace_type", sa.String(50), nullable=True),
        sa.Column("seniority_level", sa.String(100), nullable=True),
        sa.Column("skills", sa.JSON(), nullable=True),
        sa.Column("closing_date", sa.Date(), nullable=True),
    )
    for column in columns:
        if column.name not in existing:
            op.add_column("job_postings", column)


def downgrade() -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("job_postings")}
    for name in ("closing_date", "skills", "seniority_level", "workplace_type", "employment_type"):
        if name in existing:
            op.drop_column("job_postings", name)
