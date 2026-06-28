from datetime import datetime
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def clean_optional_text(value: str | None, *, max_length: int, field_name: str) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > max_length or CONTROL_CHAR_PATTERN.search(cleaned):
        raise ValueError(f"Invalid {field_name}.")
    return cleaned


def clean_required_text(value: str, *, max_length: int, field_name: str) -> str:
    cleaned = clean_optional_text(value, max_length=max_length, field_name=field_name)
    if cleaned is None:
        raise ValueError(f"Invalid {field_name}.")
    return cleaned


class ResumeResponse(BaseModel):
    id: int
    original_filename: str
    file_hash: str
    mime_type: str
    file_size_bytes: int
    upload_status: str
    uploaded_at: datetime

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ResumeListResponse(BaseModel):
    items: list[ResumeResponse]
    total: int

    model_config = ConfigDict(extra="forbid")


class ResumeExtractionResponse(BaseModel):
    id: int
    resume_id: int
    processing_status: str
    skills_json: dict | None
    experience_json: dict | None
    education_json: dict | None
    skills: list[str]
    experience: list[dict]
    education: list[dict]
    years_experience: float | None
    processed_at: datetime | None

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ResumeExperienceItem(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    company: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    years: float | None = Field(default=None, ge=0, le=80)

    model_config = ConfigDict(extra="forbid")

    @field_validator("title", "company")
    @classmethod
    def short_text_is_safe(cls, value: str | None, info) -> str | None:
        return clean_optional_text(value, max_length=120, field_name=info.field_name)

    @field_validator("description")
    @classmethod
    def description_is_safe(cls, value: str | None) -> str | None:
        return clean_optional_text(value, max_length=1000, field_name="description")


class ResumeEducationItem(BaseModel):
    institution: str | None = Field(default=None, max_length=160)
    credential: str | None = Field(default=None, max_length=160)
    field: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=300)
    year: int | None = Field(default=None, ge=1950, le=2100)

    model_config = ConfigDict(extra="forbid")

    @field_validator("institution", "credential", "field")
    @classmethod
    def education_text_is_safe(cls, value: str | None, info) -> str | None:
        return clean_optional_text(value, max_length=160, field_name=info.field_name)

    @field_validator("description")
    @classmethod
    def education_description_is_safe(cls, value: str | None) -> str | None:
        return clean_optional_text(value, max_length=300, field_name="description")


class ResumeExtractionUpdateRequest(BaseModel):
    skills: list[str] = Field(default_factory=list, max_length=100)
    experience: list[ResumeExperienceItem] = Field(default_factory=list, max_length=50)
    education: list[ResumeEducationItem] = Field(default_factory=list, max_length=50)
    years_experience: float | None = Field(default=None, ge=0, le=80)

    model_config = ConfigDict(extra="forbid")

    @field_validator("skills")
    @classmethod
    def skills_are_safe(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_skill in value:
            skill = clean_required_text(raw_skill, max_length=80, field_name="skill")
            folded = skill.casefold()
            if folded not in seen:
                normalized.append(skill)
                seen.add(folded)
        return normalized
