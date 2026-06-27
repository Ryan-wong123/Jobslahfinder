import hashlib
import hmac
import secrets

from pydantic import SecretStr


def generate_token(byte_length: int = 32) -> str:
    return secrets.token_urlsafe(byte_length)


def hash_token(token: str, secret: SecretStr) -> str:
    secret_value = secret.get_secret_value().encode("utf-8")
    return hmac.new(secret_value, token.encode("utf-8"), hashlib.sha256).hexdigest()
