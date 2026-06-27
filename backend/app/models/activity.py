from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.account import User
    from app.models.job import JobPosting
    from app.models.resume import Resume


class SavedJob(Base):
    __tablename__ = "saved_jobs"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    job_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("job_postings.id", ondelete="CASCADE"), primary_key=True
    )
    saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="saved_jobs")
    job: Mapped["JobPosting"] = relationship(back_populates="saved_by_users")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("job_postings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resume_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("resumes.id", ondelete="SET NULL"), index=True
    )
    match_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="recommendations")
    job: Mapped["JobPosting"] = relationship(back_populates="recommendations")
    resume: Mapped["Resume | None"] = relationship()


class CoverLetter(Base):
    __tablename__ = "cover_letters"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("job_postings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resume_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("resumes.id", ondelete="SET NULL"), index=True
    )
    generated_text: Mapped[str] = mapped_column(Text, nullable=False)
    edited_text: Mapped[str | None] = mapped_column(Text)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="cover_letters")
    job: Mapped["JobPosting"] = relationship(back_populates="cover_letters")
    resume: Mapped["Resume | None"] = relationship()


class ApplicationHistory(Base):
    __tablename__ = "application_history"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("job_postings.id", ondelete="SET NULL"), index=True
    )
    cover_letter_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("cover_letters.id", ondelete="SET NULL"), index=True
    )
    action_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    action_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    user: Mapped["User"] = relationship(back_populates="application_history")
    job: Mapped["JobPosting | None"] = relationship(back_populates="application_history")
    cover_letter: Mapped["CoverLetter | None"] = relationship()
