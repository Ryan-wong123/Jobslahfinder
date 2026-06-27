from pydantic import BaseModel, ConfigDict


class AdminHealthResponse(BaseModel):
    status: str
    service: str
    access: str

    model_config = ConfigDict(extra="forbid")
