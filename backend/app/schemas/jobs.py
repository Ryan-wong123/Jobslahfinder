from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    employment_type: str | None = None
    workplace_type: str | None = None
    seniority_level: str | None = None
    skills: list[str] | None = None
    closing_date: date | None = None
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


class SalaryComparisonQuery(BaseModel):
    roles: list[str] = Field(min_length=2, max_length=4)
    page: int = Field(default=1, ge=1, le=1000)
    page_size: int = Field(default=4, ge=1, le=4)

    model_config = ConfigDict(extra="forbid")

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, roles: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for role in roles:
            normalized = " ".join(role.split())
            if not 2 <= len(normalized) <= 100:
                raise ValueError("Each role must contain between 2 and 100 characters.")
            if not all(character.isalnum() or character in " ., &()+#/'-_" for character in normalized):
                raise ValueError("A role contains unsupported characters.")
            key = normalized.casefold()
            if key in seen:
                raise ValueError("Roles must be unique.")
            seen.add(key)
            cleaned.append(normalized)
        return cleaned


class SalaryComparisonItemResponse(BaseModel):
    role: str
    currency: str = "SGD"
    period: str = "month"
    minimum_salary: float | None
    maximum_salary: float | None
    median_salary: float | None
    average_salary: float | None
    valid_posting_count: int = Field(ge=0)
    median_minimum_experience_years: float | None
    experience_data_coverage_percentage: float = Field(ge=0, le=100)
    statistics_available: bool

    model_config = ConfigDict(extra="forbid")


class SalaryComparisonResponse(BaseModel):
    items: list[SalaryComparisonItemResponse]
    page: int
    page_size: int
    total: int

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
