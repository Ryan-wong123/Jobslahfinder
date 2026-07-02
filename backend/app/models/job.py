from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import ScrapingRunStatus

if TYPE_CHECKING:
    from app.models.activity import ApplicationHistory, CoverLetter, Recommendation, SavedJob


class JobSource(Base):
    __tablename__ = "job_sources"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    source_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    scraping_runs: Mapped[list["ScrapingRun"]] = relationship(back_populates="source")
    job_postings: Mapped[list["JobPosting"]] = relationship(back_populates="source")


class ScrapingRun(Base):
    __tablename__ = "scraping_runs"
    __table_args__ = (
        CheckConstraint(
            "status in ('PENDING', 'RUNNING', 'SUCCESS', 'FAILED')",
            name="scraping_runs_status_allowed",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    source_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("job_sources.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=ScrapingRunStatus.PENDING.value, index=True
    )
    jobs_retrieved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)

    source: Mapped[JobSource] = relationship(back_populates="scraping_runs")


class JobPosting(Base):
    __tablename__ = "job_postings"
    __table_args__ = (
        UniqueConstraint("source_id", "external_job_id", name="uq_job_postings_source_external_id"),
        Index("ix_job_postings_title", "title"),
        Index("ix_job_postings_company", "company"),
        Index("ix_job_postings_location", "location"),
        Index("ix_job_postings_category", "category"),
        Index("ix_job_postings_posting_date", "posting_date"),
        Index("ix_job_postings_content_hash", "content_hash"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    source_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("job_sources.id"), nullable=False)
    external_job_id: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    job_url: Mapped[str] = mapped_column(Text, nullable=False)
    posting_date: Mapped[date | None] = mapped_column(Date)
    salary_min: Mapped[float | None] = mapped_column(Numeric(12, 2), index=True)
    salary_max: Mapped[float | None] = mapped_column(Numeric(12, 2), index=True)
    salary_currency: Mapped[str | None] = mapped_column(String(10))
    salary_period: Mapped[str | None] = mapped_column(String(20))
    minimum_experience: Mapped[str | None] = mapped_column(String(100))
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    is_suspicious: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)

    source: Mapped[JobSource] = relationship(back_populates="job_postings")
    saved_by_users: Mapped[list["SavedJob"]] = relationship(back_populates="job")
    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="job")
    cover_letters: Mapped[list["CoverLetter"]] = relationship(back_populates="job")
    application_history: Mapped[list["ApplicationHistory"]] = relationship(back_populates="job")
