from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    password_reset_expire_minutes: int = Field(
        default=30, validation_alias="PASSWORD_RESET_EXPIRE_MINUTES"
    )

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("allowed_job_source_domains")
    @classmethod
    def normalize_allowed_domains(cls, value: str) -> str:
        return ",".join(item.strip().lower() for item in value.split(",") if item.strip())

    @model_validator(mode="after")
    def validate_secure_production_settings(self) -> "Settings":
        if self.scraping_request_timeout_seconds < 1 or self.scraping_request_timeout_seconds > 120:
            raise ValueError("SCRAPING_REQUEST_TIMEOUT_SECONDS must be between 1 and 120.")
        if self.scraping_max_retries < 0 or self.scraping_max_retries > 5:
            raise ValueError("SCRAPING_MAX_RETRIES must be between 0 and 5.")
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
