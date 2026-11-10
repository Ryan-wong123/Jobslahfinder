"""Transactional mail delivery and verified email changes."""
from alembic import op
import sqlalchemy as sa

revision = "0010_security_recovery"
down_revision = "0009_merge_remaining_heads"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("email_change_tokens",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("old_email", sa.String(255), nullable=False),
        sa.Column("new_email", sa.String(255), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)))
    op.create_index("ix_email_change_tokens_user_id", "email_change_tokens", ["user_id"])
    op.create_table("email_deliveries",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("encrypted_payload", sa.Text()),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_email_deliveries_user_id", "email_deliveries", ["user_id"])
    op.create_index("ix_email_deliveries_status", "email_deliveries", ["status"])


def downgrade():
    op.drop_table("email_deliveries")
    op.drop_table("email_change_tokens")
