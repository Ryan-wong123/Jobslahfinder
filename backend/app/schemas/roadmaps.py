from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.auth import validate_optional_text

RoadmapLevel = Literal["ENTRY", "JUNIOR", "MID", "SENIOR"]
RoadmapStatus = Literal["ACTIVE", "ARCHIVED"]
MAX_CURRENT_SKILLS = 30
MAX_CURRENT_SKILL_LENGTH = 80


class RoadmapCreateRequest(BaseModel):
    target_role: str = Field(min_length=2, max_length=120)
    target_level: RoadmapLevel = "JUNIOR"
    timeline_months: int = Field(ge=1, le=24)
    current_skills: list[str] = Field(default_factory=list, max_length=MAX_CURRENT_SKILLS)
    notes: str | None = Field(default=None, max_length=1000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("target_role")
    @classmethod
    def validate_target_role(cls, value: str) -> str:
        cleaned = validate_optional_text(value, field_name="target_role")
        if cleaned is None:
            raise ValueError("Invalid target role.")
        return cleaned

    @field_validator("current_skills")
    @classmethod
    def validate_current_skills(cls, value: list[str]) -> list[str]:
        cleaned_items: list[str] = []
        seen: set[str] = set()
        for item in value:
            cleaned = validate_optional_text(item, field_name="current_skills")
            if cleaned is None:
                continue
            if len(cleaned) > MAX_CURRENT_SKILL_LENGTH:
                raise ValueError("Invalid current skills.")
            normalized = cleaned.casefold()
            if normalized in seen:
                continue
            cleaned_items.append(cleaned)
            seen.add(normalized)
        return cleaned_items

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, value: str | None) -> str | None:
        return validate_optional_text(value, field_name="notes")


class RoadmapUpdateRequest(BaseModel):
    status: RoadmapStatus

    model_config = ConfigDict(extra="forbid")


class RoadmapMilestoneResponse(BaseModel):
    month: int = Field(ge=1, le=60)
    title: str = Field(min_length=1, max_length=120)
    focus: str = Field(min_length=1, max_length=200)
    actions: list[str] = Field(default_factory=list, max_length=10)
    evidence: list[str] = Field(default_factory=list, max_length=10)

    model_config = ConfigDict(extra="forbid")


class JobRoleRoadmapResponse(BaseModel):
    id: int
    target_role: str
    target_level: RoadmapLevel
    timeline_months: int
    current_skills: list[str]
    milestones: list[RoadmapMilestoneResponse]
    notes: str | None
    status: RoadmapStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid")


class JobRoleRoadmapListResponse(BaseModel):
    items: list[JobRoleRoadmapResponse]
    page: int
    page_size: int
    total: int

    model_config = ConfigDict(extra="forbid")
