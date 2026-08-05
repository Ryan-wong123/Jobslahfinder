from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EmploymentType, SeniorityLevel, WorkplaceType


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
    minimum_experience_years: int | None = Field(default=None, ge=0, le=50)
    employment_type: EmploymentType | None = None
    workplace_type: WorkplaceType | None = None
    seniority_level: SeniorityLevel | None = None
    skills: list[str] | None = None
    posted_at: datetime | None = None
    expires_at: datetime | None = None
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
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)

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
