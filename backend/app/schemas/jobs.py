from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class JobSourceResponse(BaseModel):
    id: int
    source_name: str
    base_url: str
    is_enabled: bool
    created_at: datetime

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
