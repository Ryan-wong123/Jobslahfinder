from datetime import datetime
from typing import Any
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AdminDependencyHealth(BaseModel):
    status: Literal["ok", "unavailable"]

    model_config = ConfigDict(extra="forbid")


class AdminHealthResponse(BaseModel):
    status: Literal["ok", "unavailable"]
    service: str = Field(min_length=1, max_length=40)
    access: Literal["admin"]
    timestamp: datetime | None = None
    database: AdminDependencyHealth | None = None
    redis: AdminDependencyHealth | None = None
    worker: AdminDependencyHealth | None = None

    model_config = ConfigDict(extra="forbid")


class AdminUserResponse(BaseModel):
    id: int = Field(gt=0)
    email: str = Field(min_length=3, max_length=255)
    role: Literal["USER", "ADMIN"]
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class AdminUserListResponse(BaseModel):
    items: list[AdminUserResponse]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=50)
    total: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid")


class AdminUserDetailResponse(AdminUserResponse):
    updated_at: datetime
    resume_count: int = Field(ge=0)
    saved_job_count: int = Field(ge=0)
    recommendation_count: int = Field(ge=0)
    cover_letter_count: int = Field(ge=0)
    application_history_count: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class AdminUserUpdateRequest(BaseModel):
    is_active: bool

    model_config = ConfigDict(extra="forbid")


class AdminJobUpdateRequest(BaseModel):
    is_active: bool | None = None
    is_suspicious: bool | None = None

    model_config = ConfigDict(extra="forbid")


class AdminAuditLogResponse(BaseModel):
    id: int = Field(gt=0)
    user_id: int | None = Field(default=None, gt=0)
    event_type: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.:-]+$")
    target_type: str | None = Field(default=None, max_length=100)
    target_id: int | None = Field(default=None, gt=0)
    outcome: Literal["SUCCESS", "FAILURE", "DENIED"]
    details_json: dict[str, Any] | None
    created_at: datetime

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class AdminAuditLogListResponse(BaseModel):
    items: list[AdminAuditLogResponse]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=50)
    total: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid")
