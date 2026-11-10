from datetime import timedelta
import logging
import sys

import pyotp
import pytest
from fastapi import HTTPException
from redis.exceptions import ConnectionError
from sqlalchemy import select

from app.tests.test_auth import client, db_session, register, login, STRONG_PASSWORD, NEW_PASSWORD
from app.core.config import get_settings
from app.core.logging import RedactingFilter
from app.core import rate_limit
from app.models.account import PasswordResetToken, User, Session as UserSession
from app.models.security import EmailChangeToken, EmailDelivery
from app.security.tokens import hash_token
from app.services.auth import utc_now
from app.services.two_factor import decrypt_totp_secret
from app.services.mail_outbox import deliver_pending_mail, queue_mail
from app.services import resumes


def setup_user(client, db_session):
    assert register(client).status_code == 201
    assert login(client).status_code == 200
    return db_session.scalar(select(User))


def test_email_change_requires_password_mfa_and_verified_ownership(client, db_session, monkeypatch):
    user = setup_user(client, db_session)
    settings = get_settings()
    code = pyotp.TOTP(decrypt_totp_secret(settings, user.totp_secret_encrypted)).now()
    monkeypatch.setattr("app.services.email_change.generate_token", lambda: "C" * 43)
    assert client.patch("/me", json={"email": "new@example.com"}).status_code == 400
    bad = {"email": "new@example.com", "current_password": "wrong", "code": code}
    assert client.post("/auth/email-change/request", json=bad).status_code == 400
    assert db_session.scalar(select(EmailChangeToken)) is None
    good = {**bad, "current_password": STRONG_PASSWORD}
    assert client.post("/auth/email-change/request", json=good).status_code == 200
    db_session.refresh(user)
    assert user.email == "user@example.com"
    record = db_session.scalar(select(EmailChangeToken))
    assert record.token_hash != "C" * 43
    mail = db_session.scalar(select(EmailDelivery))
    assert "new@example.com" not in mail.encrypted_payload
    assert "C" * 43 not in mail.encrypted_payload
    assert client.post("/auth/email-change/confirm", json={"token": "D" * 43}).status_code == 400
    assert client.post("/auth/email-change/confirm", json={"token": "C" * 43}).status_code == 200
    db_session.refresh(user)
    assert user.email == "new@example.com"
    assert client.get("/me").status_code == 401
    assert all(s.revoked_at for s in db_session.scalars(select(UserSession)))
    assert record.used_at is not None


def test_email_change_tokens_cannot_cross_accounts_or_expire(client, db_session, monkeypatch):
    user = setup_user(client, db_session)
    settings = get_settings()
    db_session.add(EmailChangeToken(user_id=user.id, old_email=user.email, new_email="new@example.com",
        token_hash=hash_token("E" * 43, settings.password_reset_secret), expires_at=utc_now()-timedelta(seconds=1)))
    db_session.commit()
    assert client.post("/auth/email-change/confirm", json={"token": "E" * 43}).status_code == 400
    assert user.email == "user@example.com"
    client.post("/auth/logout")
    assert client.post("/auth/email-change/request", json={"email":"new@example.com", "current_password":STRONG_PASSWORD,"code":"123456"}).status_code == 401


def test_reset_revokes_every_outstanding_reset_token(client, db_session):
    user = setup_user(client, db_session)
    settings = get_settings()
    for token in ("F" * 43, "G" * 43):
        db_session.add(PasswordResetToken(user_id=user.id, token_hash=hash_token(token, settings.password_reset_secret),
            expires_at=utc_now()+timedelta(minutes=5)))
    db_session.commit()
    assert client.post("/auth/password-reset/confirm", json={"token":"F"*43,"new_password":NEW_PASSWORD}).status_code == 200
    assert client.post("/auth/password-reset/confirm", json={"token":"G"*43,"new_password":STRONG_PASSWORD}).status_code == 400
    assert all(t.used_at for t in db_session.scalars(select(PasswordResetToken)))


def test_rate_limits_are_shared_expiring_and_fail_closed(isolated_rate_limit_redis, monkeypatch):
    settings = get_settings().model_copy(update={"app_env": "development"})
    for _ in range(2):
        rate_limit.check_rate_limit("shared-account", 2, 30, settings)
    with pytest.raises(HTTPException) as blocked:
        rate_limit.check_rate_limit("shared-account", 2, 30, settings)
    assert blocked.value.status_code == 429
    keys = isolated_rate_limit_redis.keys("rate:*")
    assert len(keys) == 1 and b"shared-account" not in keys[0]
    assert 0 < isolated_rate_limit_redis.ttl(keys[0]) <= 30
    def fail(*args):
        raise ConnectionError("unavailable")
    monkeypatch.setattr(isolated_rate_limit_redis, "eval", fail)
    with pytest.raises(HTTPException) as outage:
        rate_limit.check_rate_limit("other", 2, 30, settings)
    assert outage.value.status_code == 503


def test_exception_traceback_and_extra_secrets_are_not_formatted():
    try:
        raise ValueError("PRIVATE_RESUME_BODY")
    except ValueError:
        record = logging.LogRecord("app", logging.ERROR, __file__, 1, "Operation failed", (), sys.exc_info())
    record.api_key = "PRIVATE_API_KEY"
    RedactingFilter().filter(record)
    formatted = logging.Formatter().format(record)
    assert "PRIVATE_RESUME_BODY" not in formatted
    assert "ValueError" in formatted
    assert record.api_key == "[REDACTED]"


def test_exception_argument_values_are_not_logged():
    error = ValueError("PRIVATE_PROVIDER_RESPONSE")
    record = logging.LogRecord("worker", logging.ERROR, __file__, 1, "Task failed: %r", (error,), None)
    RedactingFilter().filter(record)
    assert "PRIVATE_PROVIDER_RESPONSE" not in logging.Formatter().format(record)


def test_risk_initialization_is_exclusive(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from risk_engine import config
    target = tmp_path / "state.json"
    monkeypatch.setattr(config, "ENGINE_STATE_PATH", target)
    def initialize(_):
        try:
            config.write_engine_state_atomically("test-local-engine-credential")
            return "initialized"
        except FileExistsError:
            return "refused"
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(initialize, range(2))) == ["initialized", "refused"]
    with pytest.raises(FileExistsError):
        config.write_engine_state_atomically("replacement-not-permitted")


def test_independent_data_key_preserves_legacy_totp_and_worker_has_no_signing_keys():
    from pydantic import SecretStr
    from app.core.config import Settings
    from app.tests.test_config import production_kwargs
    from app.services.two_factor import encrypt_totp_secret
    original = get_settings().model_copy(update={"data_encryption_secret": None})
    encrypted = encrypt_totp_secret(original, "test-totp-enrollment")
    separated = original.model_copy(update={"data_encryption_secret": SecretStr("independent-data-encryption-key-for-testing")})
    assert decrypt_totp_secret(separated, encrypted) == "test-totp-enrollment"
    api_settings = Settings(_env_file=None, **production_kwargs())
    worker_settings = Settings(_env_file=None, SERVICE_ROLE="worker", **production_kwargs())
    assert worker_settings.session_secret != api_settings.session_secret
    assert worker_settings.password_reset_secret != api_settings.password_reset_secret
    assert worker_settings.data_encryption_secret == api_settings.data_encryption_secret
    from cryptography.fernet import InvalidToken
    with pytest.raises(InvalidToken):
        decrypt_totp_secret(worker_settings, encrypt_totp_secret(api_settings, "test-totp-enrollment"))
    from app.security.encryption import encrypt_mail_payload, decrypt_mail_payload
    encrypted = encrypt_mail_payload(api_settings, "test-encrypted-mail-content")
    assert decrypt_mail_payload(worker_settings, encrypted) == "test-encrypted-mail-content"


def test_invalid_startup_configuration_never_formats_secret_values(monkeypatch):
    monkeypatch.setenv("APP_ENV", "invalid-environment")
    monkeypatch.setenv("SESSION_SECRET", "private-startup-sentinel-must-not-be-formatted")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError) as error:
            get_settings()
        assert "private-startup-sentinel" not in str(error.value)
    finally:
        get_settings.cache_clear()


def test_mail_retries_are_bounded_and_expired_payload_is_erased(client, db_session, monkeypatch):
    user = setup_user(client, db_session)
    settings = get_settings()
    queue_mail(db_session, settings, user_id=user.id, kind="account", to_email=user.email, subject="Notice", body="private")
    db_session.commit()
    item = db_session.scalar(select(EmailDelivery))
    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE_PROVIDER_RESPONSE")
    monkeypatch.setattr("app.services.mail_outbox.send_account_email", fail)
    for _ in range(3):
        item.available_at = utc_now()-timedelta(seconds=1)
        db_session.commit()
        deliver_pending_mail(db_session, settings)
    assert item.status == "FAILED" and item.attempts == 3
    assert item.encrypted_payload is None


def test_parser_timeout_kills_the_child():
    settings = get_settings().model_copy(update={"resume_parser_timeout_seconds": 0.001})
    with pytest.raises(TimeoutError):
        resumes._isolated_parse(b"%PDF-1.7", ".pdf", settings)


def test_risk_engine_http_setup_never_returns_credentials(client):
    response = client.post("/risk-engine/setup")
    assert response.status_code == 404
    assert "api_key" not in response.text


def test_scheduler_heartbeat_records_successful_beat_publication(tmp_path, monkeypatch):
    from app.workers import celery_app as module
    heartbeat = tmp_path / "heartbeat"
    monkeypatch.setattr(module, "SCHEDULER_HEARTBEAT", heartbeat)
    monkeypatch.setattr(module, "settings", get_settings().model_copy(update={"service_role": "api"}))
    module.record_scheduler_dispatch()
    assert not heartbeat.exists()
    monkeypatch.setattr(module, "settings", get_settings().model_copy(update={"service_role": "beat"}))
    module.record_scheduler_dispatch()
    assert heartbeat.is_file()
