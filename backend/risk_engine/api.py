from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
import secrets
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


app = FastAPI(title="RBA Risk Engine")

app.add_middleware(
    SessionMiddleware,
    secret_key=config.SESSION_SECRET,
    session_cookie="risk_engine_admin_session",
    https_only=os.getenv("RISK_ENGINE_HTTPS_ONLY", "false").lower() == "true",
    max_age=int(os.getenv("RISK_ENGINE_ADMIN_SESSION_TIMEOUT_SEC", "900")),
    same_site="strict",  # CSRF protection via cookie policy
)

# Mount static files for dashboard CSS/JS
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

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
    try:
        if config.is_sealed():
            raise HTTPException(status_code=410, detail="Already initialized")
    except RuntimeError:
        # State exists but is corrupt: fail closed
        raise HTTPException(status_code=500, detail="Engine misconfigured")

    api_key = secrets.token_urlsafe(32)

    try:
        config.write_engine_state_atomically(api_key)
    except FileExistsError:
        # If you implement locking via O_EXCL and it already exists
        raise HTTPException(status_code=410, detail="Already initialized")
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to initialize")

    return {"api_key": api_key}
