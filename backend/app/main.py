from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.activity import router as activity_router
from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.job_roles import router as job_roles_router
from app.api.jobs import router as jobs_router
from app.api.roadmaps import router as roadmaps_router
from app.api.resumes import router as resumes_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.services.risk_engine import init_risk_engine_storage
from risk_engine.api import app as risk_engine_app

settings = get_settings()
configure_logging(settings.app_env)
logger = get_logger(__name__)

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None,
    openapi_url="/openapi.json" if settings.enable_docs else None,
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(job_roles_router)
app.include_router(jobs_router)
app.include_router(resumes_router)
app.include_router(roadmaps_router)
app.include_router(activity_router)
app.include_router(admin_router)
app.mount("/risk-engine", risk_engine_app)


SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def _origin_from_url(value: str) -> str | None:
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"{parsed.scheme}://{parsed.hostname.lower()}{port}"


def _allowed_csrf_origins(request: Request) -> set[str]:
    request_origin = _origin_from_url(str(request.base_url))
    configured_origin = _origin_from_url(settings.frontend_base_url)
    return {origin for origin in {request_origin, configured_origin} if origin}


@app.middleware("http")
async def csrf_origin_middleware(request: Request, call_next):
    if request.method.upper() in SAFE_METHODS:
        return await call_next(request)

    if settings.session_cookie_name not in request.cookies:
        return await call_next(request)

    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    supplied_origin = _origin_from_url(origin) if origin else _origin_from_url(referer or "")
    allowed_origins = _allowed_csrf_origins(request)

    if supplied_origin is None:
        if settings.app_env.lower() == "production":
            logger.warning("Rejected state-changing request without CSRF origin", extra={"path": request.url.path})
            return JSONResponse(status_code=403, content={"detail": "Request origin not allowed."})
        return await call_next(request)

    if supplied_origin not in allowed_origins:
        logger.warning("Rejected cross-site state-changing request", extra={"path": request.url.path})
        return JSONResponse(status_code=403, content={"detail": "Request origin not allowed."})

    return await call_next(request)


@app.on_event("startup")
def startup() -> None:
    init_risk_engine_storage()
    print("Website just started")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    logger.info("Request validation failed", extra={"path": request.url.path})
    return JSONResponse(
        status_code=422,
        content={"detail": "Invalid request."},
    )


@app.exception_handler(SQLAlchemyError)
async def database_exception_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    logger.exception("Database error", extra={"path": request.url.path})
    return JSONResponse(
        status_code=500,
        content={"detail": "Database operation failed."},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    logger.exception("Unhandled application error", extra={"path": request.url.path})
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong. Please try again later."},
    )
