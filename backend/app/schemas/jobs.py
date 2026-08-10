from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class JobSourceResponse(BaseModel):
    id: int
    source_name: str
    base_url: str
    is_enabled: bool
    created_at: datetime
    job_count: int = 0

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class JobSourceUpdateRequest(BaseModel):
    is_enabled: bool

    model_config = ConfigDict(extra="forbid")


class ScrapingRunResponse(BaseModel):
    id: int
    source_id: int
    started_at: datetime
    completed_at: datetime | None
    status: str
    jobs_retrieved: int
    error_message: str | None

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ScrapingRunTriggerRequest(BaseModel):
    source_id: int = Field(gt=0)

    model_config = ConfigDict(extra="forbid")


class JobSourcePublicResponse(BaseModel):
    id: int
    source_name: str

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class JobSummaryResponse(BaseModel):
    id: int
    title: str
    company: str
    location: str | None
    category: str | None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    minimum_experience: str | None = None
    source: JobSourcePublicResponse
    posting_date: date | None
    scraped_at: datetime
    is_active: bool
    is_suspicious: bool
    application_url_is_valid: bool

    model_config = ConfigDict(extra="forbid")


class JobDetailResponse(JobSummaryResponse):
    description: str | None
    job_url: str
    external_link_warning: str


class JobListResponse(BaseModel):
    items: list[JobSummaryResponse]
    page: int
    page_size: int
    total: int

    model_config = ConfigDict(extra="forbid")


class SalaryTrendPointResponse(BaseModel):
    period: str
    average_salary: float
    sample_count: int

    model_config = ConfigDict(extra="forbid")


class SalaryTrendResponse(BaseModel):
    role: str
    currency: str
    period: str
    points: list[SalaryTrendPointResponse]
    sample_size: int

    model_config = ConfigDict(extra="forbid")


class ExperienceBand(StrEnum):
    ZERO_TO_TWO = "0-2"
    THREE_TO_FIVE = "3-5"
    SIX_TO_NINE = "6-9"
    TEN_PLUS = "10+"


class SalaryExperienceBandResponse(BaseModel):
    band: ExperienceBand
    label: str
    sample_count: int = Field(ge=0)
    median_salary: float | None
    lower_quartile: float | None
    upper_quartile: float | None

    model_config = ConfigDict(extra="forbid")


class SalaryExperienceComparisonResponse(BaseModel):
    role: str
    selected_band: ExperienceBand
    currency: str = "SGD"
    period: str = "month"
    role_sample_count: int = Field(ge=0)
    role_median_salary: float | None
    selected_band_difference_from_role_median: float | None
    bands: list[SalaryExperienceBandResponse]
    disclaimer: str

    model_config = ConfigDict(extra="forbid")


class SavedJobResponse(BaseModel):
    job: JobSummaryResponse
    saved_at: datetime

    model_config = ConfigDict(extra="forbid")


class SavedJobListResponse(BaseModel):
    items: list[SavedJobResponse]
    page: int
    page_size: int
    total: int

    model_config = ConfigDict(extra="forbid")
