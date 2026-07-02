"""repair job role roadmap columns

Revision ID: 0006_repair_role_roadmaps
Revises: 0005_job_salary_fields
Create Date: 2026-06-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_repair_role_roadmaps"
down_revision: str | None = "0005_job_salary_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = inspector.get_table_names()
    if "job_role_roadmaps" not in table_names:
        op.create_table(
            "job_role_roadmaps",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("target_role", sa.String(length=120), nullable=False),
            sa.Column("target_level", sa.String(length=40), nullable=False),
            sa.Column("timeline_months", sa.Integer(), nullable=False),
            sa.Column("current_skills_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("roadmap_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_job_role_roadmaps_user_id_users", ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id", name="pk_job_role_roadmaps"),
        )
        op.create_index("ix_job_role_roadmaps_user_id", "job_role_roadmaps", ["user_id"])
        op.create_index("ix_job_role_roadmaps_target_role", "job_role_roadmaps", ["target_role"])
        op.create_index("ix_job_role_roadmaps_status", "job_role_roadmaps", ["status"])
        op.create_index("ix_job_role_roadmaps_created_at", "job_role_roadmaps", ["created_at"])
        return

    if not has_column(inspector, "job_role_roadmaps", "target_level"):
        op.add_column("job_role_roadmaps", sa.Column("target_level", sa.String(length=40), nullable=True))
        op.execute(
            """
            UPDATE job_role_roadmaps
            SET target_level = COALESCE(NULLIF(upper(target_seniority), ''), 'JUNIOR')
            """
        )
        op.alter_column("job_role_roadmaps", "target_level", nullable=False)

    if not has_column(inspector, "job_role_roadmaps", "timeline_months"):
        op.add_column("job_role_roadmaps", sa.Column("timeline_months", sa.Integer(), nullable=True))
        op.execute(
            """
            UPDATE job_role_roadmaps
            SET timeline_months = LEAST(24, GREATEST(1, CEIL(COALESCE(target_timeline_weeks, 24) / 4.0)::integer))
            """
        )
        op.alter_column("job_role_roadmaps", "timeline_months", nullable=False)

    if not has_column(inspector, "job_role_roadmaps", "current_skills_json"):
        op.add_column(
            "job_role_roadmaps",
            sa.Column("current_skills_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )
        op.execute("UPDATE job_role_roadmaps SET current_skills_json = jsonb_build_object('items', jsonb_build_array())")

    if not has_column(inspector, "job_role_roadmaps", "roadmap_json"):
        op.add_column(
            "job_role_roadmaps",
            sa.Column("roadmap_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )
        op.execute(
            """
            UPDATE job_role_roadmaps
            SET roadmap_json = jsonb_build_object(
                'version', 'legacy-job-role-roadmap-v1',
                'milestones', jsonb_build_array(
                    jsonb_build_object(
                        'month', 1,
                        'title', 'Review legacy roadmap',
                        'focus', COALESCE(target_role, 'target role'),
                        'actions', jsonb_build_array('Review the previous roadmap notes and create an updated plan.'),
                        'evidence', jsonb_build_array('Updated roadmap entry')
                    )
                )
            )
            """
        )
        op.alter_column("job_role_roadmaps", "roadmap_json", nullable=False)

    if not has_column(inspector, "job_role_roadmaps", "notes"):
        op.add_column("job_role_roadmaps", sa.Column("notes", sa.Text(), nullable=True))
        op.execute("UPDATE job_role_roadmaps SET notes = user_notes")

    existing_indexes = {index["name"] for index in inspector.get_indexes("job_role_roadmaps")}
    if "ix_job_role_roadmaps_target_role" not in existing_indexes:
        op.create_index("ix_job_role_roadmaps_target_role", "job_role_roadmaps", ["target_role"])
    if "ix_job_role_roadmaps_created_at" not in existing_indexes:
        op.create_index("ix_job_role_roadmaps_created_at", "job_role_roadmaps", ["created_at"])


def downgrade() -> None:
    pass
