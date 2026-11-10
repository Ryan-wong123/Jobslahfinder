"""Outbox encryption is independent of authentication and TOTP keys."""
import base64
import hashlib

from cryptography.fernet import Fernet
from app.core.config import Settings


def _cipher(settings: Settings) -> Fernet:
    # Production requires a dedicated data secret. Session fallback is only for
    # existing isolated development/test configurations.
    key = settings.data_encryption_secret or settings.session_secret
    digest = hashlib.sha256(key.get_secret_value().encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_mail_payload(settings: Settings, value: str) -> str:
    return _cipher(settings).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_mail_payload(settings: Settings, value: str) -> str:
    return _cipher(settings).decrypt(value.encode("ascii")).decode("utf-8")
