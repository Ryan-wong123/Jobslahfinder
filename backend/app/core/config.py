from functools import lru_cache
from pathlib import Path
import re
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

COOKIE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}$")
HOSTNAME_PATTERN = re.compile(
    r"^(?=.{1,253}$)(?!-)(?:[A-Za-z0-9-]{1,63}\.)*[A-Za-z0-9-]{1,63}(?<!-)$"
)
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_url(value: str, *, field_name: str, allowed_schemes: set[str]) -> str:
    cleaned = value.strip()
    try:
        parsed = urlsplit(cleaned)
        _ = parsed.port
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid URL.") from exc
    if parsed.scheme not in allowed_schemes or not parsed.hostname:
        raise ValueError(f"{field_name} must use one of: {', '.join(sorted(allowed_schemes))}.")
    if parsed.username is not None or parsed.password is not None:
        if field_name not in {"DATABASE_URL", "REDIS_URL"}:
            raise ValueError(f"{field_name} must not contain credentials.")
    return cleaned


def validate_hostname(value: str, *, field_name: str) -> str:
    cleaned = value.strip().lower().rstrip(".")
    if not cleaned or "/" in cleaned or ":" in cleaned or not HOSTNAME_PATTERN.fullmatch(cleaned):
        raise ValueError(f"{field_name} must be a valid hostname.")
    return cleaned


class Settings(BaseSettings):
    app_name: str = "Secure Job Platform API"
    app_env: str = Field(default="development", validation_alias="APP_ENV")
    debug: bool = Field(default=False, validation_alias="DEBUG")
    api_host: str = Field(default="0.0.0.0", validation_alias="API_HOST")
    api_port: int = Field(default=8000, validation_alias="API_PORT")

    database_url: str = Field(validation_alias="DATABASE_URL")
    redis_url: str = Field(validation_alias="REDIS_URL")

    session_secret: SecretStr = Field(validation_alias="SESSION_SECRET")
    password_reset_secret: SecretStr = Field(validation_alias="PASSWORD_RESET_SECRET")
    session_cookie_name: str = Field(default="job_platform_session", validation_alias="SESSION_COOKIE_NAME")
    session_expire_minutes: int = Field(default=60 * 8, validation_alias="SESSION_EXPIRE_MINUTES")
    trust_proxy_headers: bool = Field(default=False, validation_alias="TRUST_PROXY_HEADERS")
    admin_session_max_age_minutes: int = Field(
        default=120, validation_alias="ADMIN_SESSION_MAX_AGE_MINUTES"
    )
    password_reset_expire_minutes: int = Field(
        default=30, validation_alias="PASSWORD_RESET_EXPIRE_MINUTES"
    )

    frontend_base_url: str = Field(default="https://18.218.236.144", validation_alias="FRONTEND_BASE_URL")
    smtp_host: str | None = Field(default=None, validation_alias="SMTP_HOST")
    smtp_port: int = Field(default=587, validation_alias="SMTP_PORT")
    smtp_username: str | None = Field(default=None, validation_alias="SMTP_USERNAME")
    smtp_password: SecretStr | None = Field(default=None, validation_alias="SMTP_PASSWORD")
    smtp_from_email: str | None = Field(default=None, validation_alias="SMTP_FROM_EMAIL")
    smtp_use_tls: bool = Field(default=True, validation_alias="SMTP_USE_TLS")

    upload_dir: Path = Field(validation_alias="UPLOAD_DIR")
    max_upload_bytes: int = Field(default=5 * 1024 * 1024, validation_alias="MAX_UPLOAD_BYTES")
    resume_parser_timeout_seconds: int = Field(
        default=10, validation_alias="RESUME_PARSER_TIMEOUT_SECONDS"
    )
    resume_parser_max_text_chars: int = Field(
        default=20000, validation_alias="RESUME_PARSER_MAX_TEXT_CHARS"
    )
    resume_extraction_provider: str = Field(
        default="gemini", validation_alias="RESUME_EXTRACTION_PROVIDER"
    )
    gemini_api_key: SecretStr | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    gemini_resume_model: str = Field(
        default="gemini-2.5-flash-lite", validation_alias="GEMINI_RESUME_MODEL"
    )
    gemini_resume_max_output_tokens: int = Field(
        default=2048, validation_alias="GEMINI_RESUME_MAX_OUTPUT_TOKENS"
    )
    cover_letter_generation_provider: str = Field(
        default="gemini", validation_alias="COVER_LETTER_GENERATION_PROVIDER"
    )
    gemini_cover_letter_model: str = Field(
        default="gemini-2.5-flash-lite", validation_alias="GEMINI_COVER_LETTER_MODEL"
    )
    gemini_cover_letter_max_output_tokens: int = Field(
        default=2048, validation_alias="GEMINI_COVER_LETTER_MAX_OUTPUT_TOKENS"
    )
    allowed_job_source_domains: str = Field(
        default="", validation_alias="ALLOWED_JOB_SOURCE_DOMAINS"
    )
    scraping_request_timeout_seconds: int = Field(
        default=15, validation_alias="SCRAPING_REQUEST_TIMEOUT_SECONDS"
    )
    scraping_max_retries: int = Field(default=2, validation_alias="SCRAPING_MAX_RETRIES")
    role_discovery_model_name: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        validation_alias="ROLE_DISCOVERY_MODEL_NAME",
    )
    role_discovery_dbscan_eps: float = Field(
        default=0.3, validation_alias="ROLE_DISCOVERY_DBSCAN_EPS"
    )
    role_discovery_dbscan_min_samples: int = Field(
        default=5, validation_alias="ROLE_DISCOVERY_DBSCAN_MIN_SAMPLES"
    )
    role_discovery_require_admin_approval: bool = Field(
        default=True, validation_alias="ROLE_DISCOVERY_REQUIRE_ADMIN_APPROVAL"
    )
    celery_queue_max_length: int = Field(default=1000, validation_alias="CELERY_QUEUE_MAX_LENGTH")
    celery_result_expires_seconds: int = Field(default=3600, validation_alias="CELERY_RESULT_EXPIRES_SECONDS")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("allowed_job_source_domains")
    @classmethod
    def normalize_allowed_domains(cls, value: str) -> str:
        domains = [validate_hostname(item, field_name="ALLOWED_JOB_SOURCE_DOMAINS") for item in value.split(",") if item.strip()]
        return ",".join(dict.fromkeys(domains))

    @field_validator("database_url")
    @classmethod
    def database_url_is_valid(cls, value: str) -> str:
        return validate_url(value, field_name="DATABASE_URL", allowed_schemes={"postgresql", "postgresql+psycopg"})

    @field_validator("redis_url")
    @classmethod
    def redis_url_is_valid(cls, value: str) -> str:
        return validate_url(value, field_name="REDIS_URL", allowed_schemes={"redis", "rediss"})

    @field_validator("frontend_base_url")
    @classmethod
    def frontend_base_url_is_valid(cls, value: str) -> str:
        return validate_url(value, field_name="FRONTEND_BASE_URL", allowed_schemes={"http", "https"}).rstrip("/")

    @field_validator("session_cookie_name")
    @classmethod
    def session_cookie_name_is_valid(cls, value: str) -> str:
        cleaned = value.strip()
        if not COOKIE_NAME_PATTERN.fullmatch(cleaned):
            raise ValueError("SESSION_COOKIE_NAME contains invalid characters.")
        return cleaned

    @field_validator("smtp_host")
    @classmethod
    def smtp_host_is_valid(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return validate_hostname(value, field_name="SMTP_HOST")

    @field_validator("smtp_from_email")
    @classmethod
    def smtp_from_email_is_valid(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        cleaned = value.strip().lower()
        if len(cleaned) > 255 or not EMAIL_PATTERN.fullmatch(cleaned):
            raise ValueError("SMTP_FROM_EMAIL must be a valid email address.")
        return cleaned

    @field_validator("smtp_username")
    @classmethod
    def smtp_username_is_valid(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        cleaned = value.strip()
        if len(cleaned) > 255 or any(character.isspace() or ord(character) < 32 for character in cleaned):
            raise ValueError("SMTP_USERNAME contains invalid characters.")
        return cleaned

    @model_validator(mode="after")
    def validate_secure_production_settings(self) -> "Settings":
        if self.session_expire_minutes < 15 or self.session_expire_minutes > 24 * 60:
            raise ValueError("SESSION_EXPIRE_MINUTES must be between 15 and 1440.")
        if self.scraping_request_timeout_seconds < 1 or self.scraping_request_timeout_seconds > 120:
            raise ValueError("SCRAPING_REQUEST_TIMEOUT_SECONDS must be between 1 and 120.")
        if self.admin_session_max_age_minutes < 5 or self.admin_session_max_age_minutes > 24 * 60:
            raise ValueError("ADMIN_SESSION_MAX_AGE_MINUTES must be between 5 and 1440.")
        if self.scraping_max_retries < 0 or self.scraping_max_retries > 5:
            raise ValueError("SCRAPING_MAX_RETRIES must be between 0 and 5.")
        if not self.role_discovery_model_name.strip():
            raise ValueError("ROLE_DISCOVERY_MODEL_NAME must not be empty.")
        if self.role_discovery_dbscan_eps <= 0 or self.role_discovery_dbscan_eps > 2:
            raise ValueError("ROLE_DISCOVERY_DBSCAN_EPS must be greater than 0 and at most 2.")
        if (
            self.role_discovery_dbscan_min_samples < 2
            or self.role_discovery_dbscan_min_samples > 1000
        ):
            raise ValueError("ROLE_DISCOVERY_DBSCAN_MIN_SAMPLES must be between 2 and 1000.")
        if not self.role_discovery_require_admin_approval:
            raise ValueError("ROLE_DISCOVERY_REQUIRE_ADMIN_APPROVAL must remain enabled.")
        if self.celery_queue_max_length < 10 or self.celery_queue_max_length > 100000:
            raise ValueError("CELERY_QUEUE_MAX_LENGTH must be between 10 and 100000.")
        if self.celery_result_expires_seconds < 60 or self.celery_result_expires_seconds > 86400:
            raise ValueError("CELERY_RESULT_EXPIRES_SECONDS must be between 60 and 86400.")
        if self.smtp_port < 1 or self.smtp_port > 65535:
            raise ValueError("SMTP_PORT must be between 1 and 65535.")
        if self.smtp_password is not None and not self.smtp_username:
            raise ValueError("SMTP_USERNAME is required when SMTP_PASSWORD is configured.")
        if self.resume_parser_timeout_seconds < 1 or self.resume_parser_timeout_seconds > 60:
            raise ValueError("RESUME_PARSER_TIMEOUT_SECONDS must be between 1 and 60.")
        if self.resume_parser_max_text_chars < 1000 or self.resume_parser_max_text_chars > 100000:
            raise ValueError("RESUME_PARSER_MAX_TEXT_CHARS must be between 1000 and 100000.")
        if self.resume_extraction_provider not in {"gemini", "local"}:
            raise ValueError("RESUME_EXTRACTION_PROVIDER must be either 'gemini' or 'local'.")
        if self.cover_letter_generation_provider not in {"gemini", "local"}:
            raise ValueError("COVER_LETTER_GENERATION_PROVIDER must be either 'gemini' or 'local'.")
        if not self.gemini_resume_model.strip():
            raise ValueError("GEMINI_RESUME_MODEL must not be empty.")
        if not self.gemini_cover_letter_model.strip():
            raise ValueError("GEMINI_COVER_LETTER_MODEL must not be empty.")
        if self.gemini_resume_max_output_tokens < 256 or self.gemini_resume_max_output_tokens > 8192:
            raise ValueError("GEMINI_RESUME_MAX_OUTPUT_TOKENS must be between 256 and 8192.")
        if self.gemini_cover_letter_max_output_tokens < 256 or self.gemini_cover_letter_max_output_tokens > 8192:
            raise ValueError("GEMINI_COVER_LETTER_MAX_OUTPUT_TOKENS must be between 256 and 8192.")

        if self.app_env.lower() == "production":
            if self.debug:
                raise ValueError("DEBUG must be false in production.")
            if len(self.session_secret.get_secret_value()) < 32:
                raise ValueError("SESSION_SECRET must be at least 32 characters.")
            if len(self.password_reset_secret.get_secret_value()) < 32:
                raise ValueError("PASSWORD_RESET_SECRET must be at least 32 characters.")
            if not self.smtp_host or not self.smtp_from_email:
                raise ValueError("SMTP_HOST and SMTP_FROM_EMAIL are required in production.")
            if self.resume_extraction_provider == "gemini" and self.gemini_api_key is None:
                raise ValueError("GEMINI_API_KEY is required when Gemini resume extraction is enabled.")
            if self.cover_letter_generation_provider == "gemini" and self.gemini_api_key is None:
                raise ValueError("GEMINI_API_KEY is required when Gemini cover letter generation is enabled.")

        return self

    @property
    def enable_docs(self) -> bool:
        return self.app_env.lower() != "production"

    @property
    def secure_cookies(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def allowed_job_source_domain_list(self) -> list[str]:
        if not self.allowed_job_source_domains:
            return []
        return [item for item in self.allowed_job_source_domains.split(",") if item]


@lru_cache
def get_settings() -> Settings:
    return Settings()
