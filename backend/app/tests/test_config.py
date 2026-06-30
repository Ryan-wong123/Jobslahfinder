import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


def test_config_loads_from_environment() -> None:
    get_settings.cache_clear()
    settings = get_settings()

    assert settings.app_env == "test"
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert "sg.jobstreet.com" in settings.allowed_job_source_domains
    assert settings.debug is False


def test_config_normalizes_and_deduplicates_allowed_domains(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOWED_JOB_SOURCE_DOMAINS", " SG.JobStreet.com. ,sg.jobstreet.com")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.allowed_job_source_domain_list == ["sg.jobstreet.com"]


def test_config_rejects_invalid_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///local.db")
    get_settings.cache_clear()

    with pytest.raises(ValidationError):
        get_settings()


def test_config_rejects_invalid_cookie_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_NAME", "bad cookie")
    get_settings.cache_clear()

    with pytest.raises(ValidationError):
        get_settings()


def test_production_requires_secure_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SESSION_SECRET", "short")
    get_settings.cache_clear()

    with pytest.raises(ValidationError):
        get_settings()


@pytest.mark.parametrize(
    ("env_name", "env_value"),
    [
        ("API_PORT", "70000"),
        ("SESSION_EXPIRE_MINUTES", "5"),
        ("PASSWORD_RESET_EXPIRE_MINUTES", "2"),
        ("MAX_UPLOAD_BYTES", str(26 * 1024 * 1024)),
    ],
)
def test_config_rejects_out_of_range_values(
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    env_value: str,
) -> None:
    monkeypatch.setenv(env_name, env_value)
    get_settings.cache_clear()

    with pytest.raises(ValidationError):
        get_settings()


def test_settings_constructor_rejects_malformed_allowed_domain() -> None:
    with pytest.raises(ValidationError):
        Settings(
            DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/db",
            REDIS_URL="redis://localhost:6379/0",
            SESSION_SECRET="test_session_secret_value_at_least_32_chars",
            PASSWORD_RESET_SECRET="test_reset_secret_value_at_least_32_chars",
            UPLOAD_DIR="/tmp/uploads",
            ALLOWED_JOB_SOURCE_DOMAINS="https://sg.jobstreet.com",
        )
