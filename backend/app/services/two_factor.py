from __future__ import annotations

import base64
import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pyotp
from cryptography.fernet import Fernet
from redis import Redis

from app.core.config import Settings
from app.models.account import User

_CHALLENGE_KEY_PREFIX = "2fa_challenge:"
_CHALLENGE_TTL_SECONDS = 5 * 60  # 5 minutes


@dataclass(frozen=True)
class PendingTwoFactorChallenge:
    user_id: int
    expires_at: datetime
    force_rotate_device_cookie: bool
    ip_prefix: str | None = None


def _redis(settings: Settings) -> Redis:
    return Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=2,
        socket_timeout=2,
        decode_responses=True,
    )


def _fernet(settings: Settings) -> Fernet:
    digest = hashlib.sha256(settings.session_secret.get_secret_value().encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_totp_secret(settings: Settings, secret: str) -> str:
    return _fernet(settings).encrypt(secret.encode("utf-8")).decode("utf-8")


def decrypt_totp_secret(settings: Settings, encrypted_secret: str) -> str:
    return _fernet(settings).decrypt(encrypted_secret.encode("utf-8")).decode("utf-8")


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(*, email: str, secret: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="SSD Resume Analysis")


def verify_totp_code(settings: Settings, user: User, code: str) -> bool:
    if not user.totp_secret_encrypted:
        return False
    try:
        secret = decrypt_totp_secret(settings, user.totp_secret_encrypted)
    except Exception:
        return False
    normalized = code.strip().replace(" ", "")
    return pyotp.TOTP(secret).verify(normalized, valid_window=1)


def create_pending_2fa_challenge(
    *,
    user_id: int,
    force_rotate_device_cookie: bool,
    settings: Settings,
    ip_prefix: str | None = None,
) -> str:
    """Store a pending 2FA challenge in Redis and return an opaque token.

    Redis TTL enforces the 5-minute expiry; the ``expires_at`` field inside the
    payload provides a secondary wall-clock check when the challenge is consumed.
    """
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(seconds=_CHALLENGE_TTL_SECONDS)
    payload = json.dumps(
        {
            "user_id": user_id,
            "force_rotate_device_cookie": force_rotate_device_cookie,
            "ip_prefix": ip_prefix,
            "expires_at": expires_at.isoformat(),
        }
    )
    _redis(settings).setex(
        f"{_CHALLENGE_KEY_PREFIX}{token}",
        _CHALLENGE_TTL_SECONDS,
        payload,
    )
    return token


def get_pending_2fa_challenge(
    token: str, settings: Settings
) -> PendingTwoFactorChallenge | None:
    """Read a pending 2FA challenge without consuming it.

    Returns ``None`` if the token does not exist, is expired, or is malformed.
    Call ``invalidate_pending_2fa_challenge`` after a successful TOTP
    verification to prevent replay.
    """
    client = _redis(settings)
    key = f"{_CHALLENGE_KEY_PREFIX}{token}"
    raw = client.get(key)
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
        expires_at = datetime.fromisoformat(parsed["expires_at"])
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        # Corrupt payload: purge it and fail closed.
        client.delete(key)
        return None
    if expires_at <= datetime.now(UTC):
        # Expired but Redis TTL has not fired yet: purge and fail.
        client.delete(key)
        return None
    return PendingTwoFactorChallenge(
        user_id=int(parsed["user_id"]),
        expires_at=expires_at,
        force_rotate_device_cookie=bool(parsed["force_rotate_device_cookie"]),
        ip_prefix=parsed.get("ip_prefix"),
    )


def invalidate_pending_2fa_challenge(token: str, settings: Settings) -> bool:
    """Delete a pending 2FA challenge after it has been successfully verified."""
    return bool(_redis(settings).delete(f"{_CHALLENGE_KEY_PREFIX}{token}"))
