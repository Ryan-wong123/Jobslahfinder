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

    upload_dir: Path = Field(validation_alias="UPLOAD_DIR")
    max_upload_bytes: int = Field(default=5 * 1024 * 1024, validation_alias="MAX_UPLOAD_BYTES")
    allowed_job_source_domains: str = Field(
        default="", validation_alias="ALLOWED_JOB_SOURCE_DOMAINS"
    )

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
        if self.app_env.lower() == "production":
            if self.debug:
                raise ValueError("DEBUG must be false in production.")
            if len(self.session_secret.get_secret_value()) < 32:
                raise ValueError("SESSION_SECRET must be at least 32 characters.")
            if len(self.password_reset_secret.get_secret_value()) < 32:
                raise ValueError("PASSWORD_RESET_SECRET must be at least 32 characters.")
        return self

    @property
    def enable_docs(self) -> bool:
        return self.app_env.lower() != "production"

    @property
    def allowed_job_source_domain_list(self) -> list[str]:
        if not self.allowed_job_source_domains:
            return []
        return [item for item in self.allowed_job_source_domains.split(",") if item]


@lru_cache
def get_settings() -> Settings:
    return Settings()
