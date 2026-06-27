from fastapi import APIRouter, Depends

from app.models.account import User
from app.schemas.admin import AdminHealthResponse
from app.security.auth import require_admin


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/health", response_model=AdminHealthResponse)
def admin_health(_current_admin: User = Depends(require_admin)) -> AdminHealthResponse:
    return AdminHealthResponse(status="ok", service="backend", access="admin")
