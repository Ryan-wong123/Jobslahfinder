"""add recommendation rank and metadata

Revision ID: 0002_reco_rank_meta
Revises: 0001_initial_schema
Create Date: 2026-05-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_reco_rank_meta"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("recommendations", sa.Column("rank", sa.Integer(), nullable=True))
    op.add_column(
        "recommendations",
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index("ix_recommendations_rank", "recommendations", ["rank"])


def downgrade() -> None:
    op.drop_index("ix_recommendations_rank", table_name="recommendations")
    op.drop_column("recommendations", "metadata_json")
    op.drop_column("recommendations", "rank")
