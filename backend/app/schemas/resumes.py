from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ResumeResponse(BaseModel):
    id: int
    original_filename: str
    file_hash: str
    mime_type: str
    file_size_bytes: int
    upload_status: str
    uploaded_at: datetime

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ResumeListResponse(BaseModel):
    items: list[ResumeResponse]
    total: int

    model_config = ConfigDict(extra="forbid")


class ResumeExtractionResponse(BaseModel):
    id: int
    resume_id: int
    processing_status: str
    skills_json: dict | None
    experience_json: dict | None
    education_json: dict | None
    years_experience: float | None
    processed_at: datetime | None

    model_config = ConfigDict(extra="forbid", from_attributes=True)
