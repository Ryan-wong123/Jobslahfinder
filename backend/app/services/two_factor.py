from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
import secrets

import pyotp
from cryptography.fernet import Fernet
from redis import Redis

from app.core.config import Settings
from app.models.account import User

CHALLENGE_KEY_PREFIX = "2fa_challenge:"
CHALLENGE_TTL_SECONDS = 5 * 60


@dataclass(frozen=True)
class PendingTwoFactorChallenge:
    user_id: int
    expires_at: datetime


def redis_client(settings: Settings) -> Redis:
    return Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=2,
        socket_timeout=2,
        decode_responses=True,
    )


def fernet(settings: Settings) -> Fernet:
    digest = hashlib.sha256(settings.session_secret.get_secret_value().encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_totp_secret(settings: Settings, secret: str) -> str:
    return fernet(settings).encrypt(secret.encode("utf-8")).decode("utf-8")


def decrypt_totp_secret(settings: Settings, encrypted_secret: str) -> str:
    return fernet(settings).decrypt(encrypted_secret.encode("utf-8")).decode("utf-8")


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(*, email: str, secret: str, issuer_name: str = "Jobslahfinder") -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer_name)


def verify_totp_code(settings: Settings, user: User, code: str) -> bool:
    if not user.totp_secret_encrypted:
        return False
    try:
        secret = decrypt_totp_secret(settings, user.totp_secret_encrypted)
    except Exception:
        return False
    normalized = code.strip().replace(" ", "")
    return pyotp.TOTP(secret).verify(normalized, valid_window=1)


def create_pending_2fa_challenge(*, user_id: int, settings: Settings) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(seconds=CHALLENGE_TTL_SECONDS)
    payload = json.dumps({"user_id": user_id, "expires_at": expires_at.isoformat()})
    redis_client(settings).setex(f"{CHALLENGE_KEY_PREFIX}{token}", CHALLENGE_TTL_SECONDS, payload)
    return token


def get_pending_2fa_challenge(token: str, settings: Settings) -> PendingTwoFactorChallenge | None:
    client = redis_client(settings)
    key = f"{CHALLENGE_KEY_PREFIX}{token}"
    raw = client.get(key)
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
        expires_at = datetime.fromisoformat(parsed["expires_at"])
        user_id = int(parsed["user_id"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        client.delete(key)
        return None
    if expires_at <= datetime.now(UTC):
        client.delete(key)
        return None
    return PendingTwoFactorChallenge(user_id=user_id, expires_at=expires_at)


def invalidate_pending_2fa_challenge(token: str, settings: Settings) -> bool:
    return bool(redis_client(settings).delete(f"{CHALLENGE_KEY_PREFIX}{token}"))
