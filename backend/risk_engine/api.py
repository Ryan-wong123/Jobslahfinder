from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
import os

# db import
from risk_engine.db.db_setup import Base, engine, AuditBase, audit_engine

# ensure models are registered with Base before create_all
from risk_engine.db import cookie_model
from risk_engine.db import risk_model
from risk_engine.db import audit_model

#routes imports
from risk_engine.routes.cookie_route import cookie_router
from risk_engine.routes.risk_route import risk_router
from risk_engine.routes.dashboard_route import dashboard_router

#component import
from risk_engine import config


from app.core.config import get_settings
_production = get_settings().app_env.lower() == "production"
app = FastAPI(title="RBA Risk Engine", docs_url=None if _production else "/docs",
              redoc_url=None if _production else "/redoc",
              openapi_url=None if _production else "/openapi.json")

app.add_middleware(
    SessionMiddleware,
    secret_key=config.SESSION_SECRET,
    session_cookie="risk_engine_admin_session",
    https_only=_production or os.getenv("RISK_ENGINE_HTTPS_ONLY", "false").lower() == "true",
    max_age=int(os.getenv("RISK_ENGINE_ADMIN_SESSION_TIMEOUT_SEC", "900")),
    same_site="strict",  # CSRF protection via cookie policy
)

# Mount static files for dashboard CSS/JS
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

if not _production:
    app.include_router(cookie_router)
    app.include_router(risk_router)
app.include_router(dashboard_router)



@app.on_event("startup")
def init_db():
    Base.metadata.create_all(bind=engine)
    AuditBase.metadata.create_all(bind=audit_engine)

@app.get("/")
def read_root():
    return RedirectResponse(url=config.admin_path("/login"), status_code=302)



@app.post("/setup")
def setup():
    # Initialization is an operator-only CLI operation. Keep a safe response for
    # old clients without exposing an initialization race or returning a secret.
    raise HTTPException(status_code=404, detail="Not found.")
