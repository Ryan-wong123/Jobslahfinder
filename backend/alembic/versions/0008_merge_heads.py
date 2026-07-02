"""mark final migration head

Revision ID: 0008_merge_heads
Revises: 0007_job_min_experience
Create Date: 2026-06-25

"""

from collections.abc import Sequence

revision: str = "0008_merge_heads"
down_revision: str | None = "0007_job_min_experience"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
