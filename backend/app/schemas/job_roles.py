from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.jobs import JobSummaryResponse, SalaryTrendPointResponse


class JobRoleSummaryResponse(BaseModel):
    slug: str
    name: str
    tagline: str
    category: str
    job_count: int
    typical_monthly_salary: float | None

    model_config = ConfigDict(extra="forbid")


class JobRoleListResponse(BaseModel):
    items: list[JobRoleSummaryResponse]

    model_config = ConfigDict(extra="forbid")


class ExperienceSalaryBandResponse(BaseModel):
    key: Literal["ENTRY", "MID_LEVEL", "SENIOR", "LEAD_EXPERT"]
    label: str
    years: str
    median_monthly_salary: float | None
    percentile_25: float | None
    percentile_75: float | None
    sample_count: int
    difference_from_preceding_band: float | None
    insufficient_data: bool

    model_config = ConfigDict(extra="forbid")


class ExperienceSalaryComparisonResponse(BaseModel):
    role_slug: str
    role_name: str
    location: str | None
    currency: Literal["SGD"] = "SGD"
    period: Literal["month"] = "month"
    observation_start: date | None
    observation_end: date | None
    bands: list[ExperienceSalaryBandResponse]

    model_config = ConfigDict(extra="forbid")


class JobRoleDetailResponse(JobRoleSummaryResponse):
    overview: str
    tasks: list[str]
    how_to_become_intro: str
    how_to_become_steps: list[str]
    top_skills: list[str]
    salary_points: list[SalaryTrendPointResponse]
    latest_jobs: list[JobSummaryResponse]

    model_config = ConfigDict(extra="forbid")
