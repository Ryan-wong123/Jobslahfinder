import hashlib
import hmac
import re
import secrets

from pydantic import SecretStr


DEFAULT_TOKEN_BYTE_LENGTH = 32
DEFAULT_TOKEN_URLSAFE_LENGTH = 43
PASSWORD_RESET_TOKEN_PATTERN = re.compile(
    rf"^[A-Za-z0-9_-]{{{DEFAULT_TOKEN_URLSAFE_LENGTH}}}$"
)


def generate_token(byte_length: int = DEFAULT_TOKEN_BYTE_LENGTH) -> str:
    return secrets.token_urlsafe(byte_length)


def hash_token(token: str, secret: SecretStr) -> str:
    secret_value = secret.get_secret_value().encode("utf-8")
    return hmac.new(secret_value, token.encode("utf-8"), hashlib.sha256).hexdigest()
