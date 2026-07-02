from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime

from fastapi import Request
from sqlalchemy.orm import Session as RiskSession

from app.core.client_ip import get_client_ip
from risk_engine.component.device_cookie import generate_device_token
from risk_engine.component.risk_utils import (
    device_token_fingerprint,
    ip_to_prefix,
    score_login,
    update_baseline_on_success,
)
from risk_engine.config import COOKIE_NAME
from risk_engine.db.db_setup import AuditBase, AuditSessionLocal, Base, SessionLocal, audit_engine, engine
from risk_engine.db.risk_model import LoginEvent

# Import models so SQLAlchemy registers them before create_all.
from risk_engine.db import audit_model as _audit_model  # noqa: F401
from risk_engine.db import cookie_model as _cookie_model  # noqa: F401
from risk_engine.db import risk_model as _risk_model  # noqa: F401


APP_DEVICE_COOKIE_NAME = "app_device_id"


@dataclass(frozen=True)
class RiskDecision:
    decision: str
    score: int
    reasons: list[str]
    ip_prefix: str | None


@dataclass(frozen=True)
class DeviceCookieIssue:
    cookie_name: str
    raw_token: str | None
    expires_at_utc: str | None
    rotate: bool


def init_risk_engine_storage() -> None:
    Base.metadata.create_all(bind=engine)
    AuditBase.metadata.create_all(bind=audit_engine)


def get_or_create_app_device_id(request: Request) -> tuple[str, bool]:
    existing = request.cookies.get(APP_DEVICE_COOKIE_NAME)
    if existing and 16 <= len(existing) <= 256:
        return existing, False
    return secrets.token_urlsafe(32), True


def client_ip_for_risk(request: Request) -> str | None:
    return get_client_ip(request)


def ip_prefix_for_risk(request: Request) -> str | None:
    return ip_to_prefix(client_ip_for_risk(request))


def evaluate_login_risk(
    request: Request,
    *,
    username: str,
    device_token: str | None,
    learn_on_non_block: bool = False,
) -> RiskDecision:
    db: RiskSession = SessionLocal()
    try:
        ip = client_ip_for_risk(request)
        user_agent = request.headers.get("user-agent")
        score, reasons, decision, ip_prefix = score_login(
            db=db,
            username=username,
            ip=ip,
            user_agent=user_agent,
            device_token=device_token,
        )
        event = LoginEvent(
            username=username,
            event_time_utc=datetime.utcnow(),
            ip=ip,
            ip_prefix=ip_prefix,
            user_agent=user_agent,
            device_token=device_token_fingerprint(device_token),
            decision=decision,
            score=score,
            reasons=json.dumps(reasons),
        )
        db.add(event)
        db.commit()
        if learn_on_non_block and decision != "block":
            update_baseline_on_success(db, username, device_token, ip_prefix)
        return RiskDecision(decision=decision, score=score, reasons=reasons, ip_prefix=ip_prefix)
    finally:
        db.close()


def issue_device_cookie(
    *,
    user_id: int,
    device_id: str,
    force_rotate: bool,
) -> DeviceCookieIssue:
    db: RiskSession = SessionLocal()
    try:
        result = generate_device_token(
            db,
            user=str(user_id),
            device=device_id,
            force_rotate=force_rotate,
        )
        return DeviceCookieIssue(
            cookie_name=result.get("cookie_name", COOKIE_NAME),
            raw_token=result.get("raw_token"),
            expires_at_utc=result.get("expires_at_utc"),
            rotate=bool(result.get("rotate")),
        )
    finally:
        db.close()


def learn_successful_login(
    *,
    username: str,
    device_token: str | None,
    ip_prefix: str | None,
) -> None:
    db: RiskSession = SessionLocal()
    try:
        update_baseline_on_success(db, username, device_token, ip_prefix)
    finally:
        db.close()
