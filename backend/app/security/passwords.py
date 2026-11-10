from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, VerifyMismatchError


_PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,
    parallelism=2,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    return _PASSWORD_HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _PASSWORD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, Argon2Error):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _PASSWORD_HASHER.check_needs_rehash(password_hash)


# Match the cost of an existing account without generating a new hash on every
# unknown-account login. The random value is never a valid account credential.
import secrets
_DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


def dummy_password_verification(password: str) -> None:
    verify_password(password, _DUMMY_HASH)
