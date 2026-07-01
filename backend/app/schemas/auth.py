from datetime import datetime
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value: str) -> str:
    return value.strip().lower()


def validate_email(value: str) -> str:
    normalized = normalize_email(value)
    if len(normalized) > 255 or not EMAIL_PATTERN.fullmatch(normalized):
        raise ValueError("Invalid email address.")
    return normalized


def validate_password_strength(value: str) -> str:
    if len(value) < 12 or len(value) > 128:
        raise ValueError("Password must be between 12 and 128 characters.")
    if not re.search(r"[A-Z]", value):
        raise ValueError("Password must contain an uppercase letter.")
    if not re.search(r"[a-z]", value):
        raise ValueError("Password must contain a lowercase letter.")
    if not re.search(r"\d", value):
        raise ValueError("Password must contain a digit.")
    return value


def validate_optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if any(ord(character) < 32 and character not in {"\t", "\n", "\r"} for character in cleaned):
        raise ValueError(f"Invalid {field_name}.")
    return cleaned


PHONE_PATTERN = re.compile(r"^[+()0-9][+()0-9 .-]{2,49}$")


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=12, max_length=128)

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    @field_validator("email")
    @classmethod
    def email_is_valid(cls, value: str) -> str:
        return validate_email(value)

    @field_validator("password")
    @classmethod
    def password_is_strong(cls, value: str) -> str:
        return validate_password_strength(value)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)

    model_config = ConfigDict(extra="forbid")

    @field_validator("email")
    @classmethod
    def email_is_valid(cls, value: str) -> str:
        return validate_email(value)


class LoginResponse(BaseModel):
    message: str
    requires_2fa: bool = False
    challenge_token: str | None = None

    model_config = ConfigDict(extra="forbid")


class TwoFactorSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str

    model_config = ConfigDict(extra="forbid")


class TwoFactorConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)

    model_config = ConfigDict(extra="forbid")


class TwoFactorVerifyRequest(BaseModel):
    challenge_token: str = Field(min_length=32, max_length=256)
    code: str = Field(min_length=6, max_length=8)

    model_config = ConfigDict(extra="forbid")


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)

    model_config = ConfigDict(extra="forbid")

    @field_validator("new_password")
    @classmethod
    def new_password_is_strong(cls, value: str) -> str:
        return validate_password_strength(value)


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)

    model_config = ConfigDict(extra="forbid")

    @field_validator("email")
    @classmethod
    def email_is_valid(cls, value: str) -> str:
        return validate_email(value)


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    new_password: str = Field(min_length=12, max_length=128)

    model_config = ConfigDict(extra="forbid")

    @field_validator("new_password")
    @classmethod
    def new_password_is_strong(cls, value: str) -> str:
        return validate_password_strength(value)


class MessageResponse(BaseModel):
    message: str

    model_config = ConfigDict(extra="forbid")


class ProfileResponse(BaseModel):
    user_id: int
    full_name: str | None
    phone: str | None
    location: str | None
    summary: str | None
    skills: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid")


class ProfileUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=255)
    summary: str | None = Field(default=None, max_length=2000)
    skills: list[str] | None = Field(default=None, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("full_name", "location", "summary")
    @classmethod
    def text_fields_are_safe(cls, value: str | None, info) -> str | None:
        return validate_optional_text(value, field_name=info.field_name)

    @field_validator("phone")
    @classmethod
    def phone_is_safe(cls, value: str | None) -> str | None:
        cleaned = validate_optional_text(value, field_name="phone")
        if cleaned is not None and not PHONE_PATTERN.fullmatch(cleaned):
            raise ValueError("Invalid phone.")
        return cleaned

    @field_validator("skills")
    @classmethod
    def skills_are_safe(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_skill in value:
            if not isinstance(raw_skill, str):
                raise ValueError("Invalid skill.")
            skill = validate_optional_text(raw_skill, field_name="skill")
            if skill is None:
                continue
            if len(skill) > 80:
                raise ValueError("Invalid skill.")
            folded = skill.casefold()
            if folded not in seen:
                normalized.append(skill)
                seen.add(folded)
        return normalized


class AccountUpdateRequest(ProfileUpdateRequest):
    email: str | None = Field(default=None, min_length=3, max_length=255)

    @field_validator("email")
    @classmethod
    def email_is_valid(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_email(value)


class AccountDeletionRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)

    model_config = ConfigDict(extra="forbid")


class UserResponse(BaseModel):
    id: int
    email: str
    role: str
    is_active: bool
    totp_enabled: bool
    created_at: datetime
    last_login_at: datetime | None

    model_config = ConfigDict(extra="forbid")
