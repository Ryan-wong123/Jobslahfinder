from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.account import User


class JobRoleRoadmap(Base):
    __tablename__ = "job_role_roadmaps"
    __table_args__ = (
        CheckConstraint(
            "status in ('ACTIVE', 'ARCHIVED')",
            name="job_role_roadmaps_status_allowed",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_role: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    target_level: Mapped[str] = mapped_column(String(40), nullable=False)
    timeline_months: Mapped[int] = mapped_column(Integer, nullable=False)
    current_skills_json: Mapped[dict | None] = mapped_column(JSONB().with_variant(JSON(), "sqlite"))
    roadmap_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="job_role_roadmaps")
