from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AdminDependencyHealth(BaseModel):
    status: str

    model_config = ConfigDict(extra="forbid")


class AdminHealthResponse(BaseModel):
    status: str
    service: str
    access: str
    timestamp: datetime | None = None
    database: AdminDependencyHealth | None = None
    redis: AdminDependencyHealth | None = None
    worker: AdminDependencyHealth | None = None

    model_config = ConfigDict(extra="forbid")


class AdminUserResponse(BaseModel):
    id: int
    email: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class AdminUserListResponse(BaseModel):
    items: list[AdminUserResponse]
    page: int
    page_size: int
    total: int

    model_config = ConfigDict(extra="forbid")


class AdminUserDetailResponse(AdminUserResponse):
    updated_at: datetime
    resume_count: int
    saved_job_count: int
    recommendation_count: int
    cover_letter_count: int
    application_history_count: int

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class AdminUserUpdateRequest(BaseModel):
    is_active: bool

    model_config = ConfigDict(extra="forbid")


class AdminJobUpdateRequest(BaseModel):
    is_active: bool | None = None
    is_suspicious: bool | None = None

    model_config = ConfigDict(extra="forbid")


class AdminAuditLogResponse(BaseModel):
    id: int
    user_id: int | None
    event_type: str
    target_type: str | None
    target_id: int | None
    outcome: str
    details_json: dict[str, Any] | None
    created_at: datetime

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class AdminAuditLogListResponse(BaseModel):
    items: list[AdminAuditLogResponse]
    page: int
    page_size: int
    total: int

    model_config = ConfigDict(extra="forbid")
