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


class JobRoleDetailResponse(JobRoleSummaryResponse):
    overview: str
    tasks: list[str]
    how_to_become_intro: str
    how_to_become_steps: list[str]
    top_skills: list[str]
    salary_points: list[SalaryTrendPointResponse]
    latest_jobs: list[JobSummaryResponse]

    model_config = ConfigDict(extra="forbid")
