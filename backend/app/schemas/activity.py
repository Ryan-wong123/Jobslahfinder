from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.auth import validate_optional_text
from app.schemas.jobs import JobSummaryResponse


MAX_COVER_LETTER_TEXT_LENGTH = 20_000


class RecommendationResponse(BaseModel):
    id: int
    job: JobSummaryResponse
    resume_id: int | None
    match_score: float
    rank: int | None
    rationale: str | None
    metadata: dict | None
    generated_at: datetime

    model_config = ConfigDict(extra="forbid")


class RecommendationListResponse(BaseModel):
    items: list[RecommendationResponse]
    page: int
    page_size: int
    total: int

    model_config = ConfigDict(extra="forbid")


class CoverLetterUpdateRequest(BaseModel):
    edited_text: str = Field(min_length=1, max_length=MAX_COVER_LETTER_TEXT_LENGTH)

    model_config = ConfigDict(extra="forbid")

    @field_validator("edited_text")
    @classmethod
    def edited_text_is_safe(cls, value: str) -> str:
        cleaned = validate_optional_text(value, field_name="edited_text")
        if cleaned is None:
            raise ValueError("Invalid edited text.")
        return cleaned


class CoverLetterResponse(BaseModel):
    id: int
    job: JobSummaryResponse
    resume_id: int | None
    generated_text: str
    edited_text: str | None
    version_no: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid")


class CoverLetterListResponse(BaseModel):
    items: list[CoverLetterResponse]
    page: int
    page_size: int
    total: int

    model_config = ConfigDict(extra="forbid")


class ApplicationHistoryResponse(BaseModel):
    id: int
    job: JobSummaryResponse | None
    cover_letter_id: int | None
    action_type: str
    action_time: datetime

    model_config = ConfigDict(extra="forbid")


class ApplicationHistoryListResponse(BaseModel):
    items: list[ApplicationHistoryResponse]
    page: int
    page_size: int
    total: int

    model_config = ConfigDict(extra="forbid")
