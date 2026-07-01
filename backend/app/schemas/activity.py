from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.auth import validate_optional_text
from app.schemas.jobs import JobSummaryResponse
from app.security.text import sanitize_required_text, sanitize_text


MAX_COVER_LETTER_TEXT_LENGTH = 20_000
MAX_INTERVIEW_QUESTION_LENGTH = 500
MAX_INTERVIEW_QUESTIONS = 10

InterviewQuestionCategory = Literal["Technical", "Behavioral", "Situational", "Resume-based"]
InterviewQuestionDifficulty = Literal["Easy", "Medium", "Hard"]


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


class InterviewQuestionItemResponse(BaseModel):
    category: InterviewQuestionCategory
    difficulty: InterviewQuestionDifficulty
    question: str = Field(min_length=1, max_length=MAX_INTERVIEW_QUESTION_LENGTH)

    model_config = ConfigDict(extra="forbid")

    @field_validator("category", "difficulty", mode="before")
    @classmethod
    def strip_choice_values(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("Invalid interview question choice.")
        return value.strip()

    @field_validator("question", mode="before")
    @classmethod
    def question_is_safe(cls, value: str) -> str:
        return sanitize_required_text(
            value,
            field_name="question",
            max_length=MAX_INTERVIEW_QUESTION_LENGTH,
            html_policy="strip",
            control_policy="strip",
            collapse_whitespace=True,
            allow_multiline=False,
        )


class InterviewQuestionsResponse(BaseModel):
    job_id: int = Field(gt=0)
    resume_id: int = Field(gt=0)
    generated_by: str = Field(min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_-]*$")
    items: list[InterviewQuestionItemResponse] = Field(
        min_length=1,
        max_length=MAX_INTERVIEW_QUESTIONS,
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("generated_by", mode="before")
    @classmethod
    def generated_by_is_safe(cls, value: str) -> str:
        cleaned = sanitize_text(
            value,
            field_name="generated_by",
            max_length=40,
            empty_to_none=True,
            html_policy="reject",
            control_policy="reject",
            collapse_whitespace=True,
            allow_multiline=False,
        )
        if cleaned is None:
            raise ValueError("Invalid generated_by.")
        return cleaned

    @model_validator(mode="after")
    def questions_are_unique(self) -> "InterviewQuestionsResponse":
        seen: set[str] = set()
        for item in self.items:
            key = item.question.casefold()
            if key in seen:
                raise ValueError("Duplicate interview questions are not allowed.")
            seen.add(key)
        return self


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
