from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from redis import Redis
from app.core.database import get_db
from app.core.config import get_settings

from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="backend")


@router.get("/ready", response_model=HealthResponse)
def readiness(db: Session = Depends(get_db)) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
        settings = get_settings()
        for url in {settings.redis_url, settings.auth_redis_url or settings.redis_url}:
            with Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2) as client:
                client.ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable.") from exc
    return HealthResponse(status="ok", service="backend")
