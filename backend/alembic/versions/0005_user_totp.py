"""add user totp fields

Revision ID: 0005_user_totp
Revises: 0004_job_role_roadmaps
Create Date: 2026-06-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_user_totp"
down_revision: str | None = "0004_job_role_roadmaps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("users")}

    if "totp_secret_encrypted" not in existing_columns:
        op.add_column("users", sa.Column("totp_secret_encrypted", sa.Text(), nullable=True))
    if "totp_enabled" not in existing_columns:
        op.add_column("users", sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
        op.alter_column("users", "totp_enabled", server_default=None)
    if "totp_confirmed_at" not in existing_columns:
        op.add_column("users", sa.Column("totp_confirmed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "totp_confirmed_at")
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_secret_encrypted")
