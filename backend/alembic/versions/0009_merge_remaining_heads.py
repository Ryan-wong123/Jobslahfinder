"""merge remaining migration heads

Revision ID: 0009_merge_remaining_heads
Revises: 0005_user_totp, 0008_merge_heads
Create Date: 2026-07-02
"""

from collections.abc import Sequence

revision: str = "0009_merge_remaining_heads"
down_revision: tuple[str, str] = ("0005_user_totp", "0008_merge_heads")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
