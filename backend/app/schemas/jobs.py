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
    months: int = Field(default=12, ge=1, le=24)

    model_config = ConfigDict(extra="forbid")

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, roles: list[str]) -> list[str]:
        cleaned_roles: list[str] = []
        seen_roles: set[str] = set()
        for role in roles:
            cleaned_role = role.strip()
            if not 2 <= len(cleaned_role) <= 100:
                raise ValueError("Each role must be between 2 and 100 characters.")
            if not all(character.isalnum() or character in " _.,&()+#/'-" for character in cleaned_role):
                raise ValueError("Role contains unsupported characters.")

            normalized_role = cleaned_role.casefold()
            if normalized_role in seen_roles:
                raise ValueError("Roles must be unique.")
            seen_roles.add(normalized_role)
            cleaned_roles.append(cleaned_role)
        return cleaned_roles


class SalaryComparisonResponse(BaseModel):
    comparisons: list[SalaryTrendResponse]
    months: int

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
