from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import ProcessingStatus, UploadStatus

if TYPE_CHECKING:
    from app.models.account import User


class Resume(Base):
    __tablename__ = "resumes"
    __table_args__ = (
        CheckConstraint(
            "upload_status in ('PENDING', 'STORED', 'REJECTED', 'DELETED')",
            name="resumes_upload_status_allowed",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    upload_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=UploadStatus.PENDING.value, index=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="resumes")
    extractions: Mapped[list["ResumeExtraction"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )


class ResumeExtraction(Base):
    __tablename__ = "resume_extractions"
    __table_args__ = (
        CheckConstraint(
            "processing_status in ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')",
            name="resume_extractions_processing_status_allowed",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    resume_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    extracted_text: Mapped[str | None] = mapped_column(Text)
    skills_json: Mapped[dict | None] = mapped_column(JSONB().with_variant(JSON(), "sqlite"))
    experience_json: Mapped[dict | None] = mapped_column(JSONB().with_variant(JSON(), "sqlite"))
    education_json: Mapped[dict | None] = mapped_column(JSONB().with_variant(JSON(), "sqlite"))
    years_experience: Mapped[float | None] = mapped_column(Numeric(4, 1))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=ProcessingStatus.PENDING.value, index=True
    )

    resume: Mapped[Resume] = relationship(back_populates="extractions")
