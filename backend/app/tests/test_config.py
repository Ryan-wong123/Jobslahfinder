import pytest

from app.core.config import Settings, get_settings


def test_config_loads_from_environment() -> None:
    get_settings.cache_clear()
    settings = get_settings()

    assert settings.app_env == "test"
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert "sg.jobstreet.com" in settings.allowed_job_source_domains
    assert "www.fastjobs.sg" in settings.allowed_job_source_domains
    assert settings.debug is False


def base_settings_kwargs() -> dict[str, object]:
    return {
        "DATABASE_URL": "postgresql+psycopg://user:password@localhost:5432/app",
        "REDIS_URL": "redis://localhost:6379/0",
        "SESSION_SECRET": "s" * 32,
        "PASSWORD_RESET_SECRET": "r" * 32,
        "UPLOAD_DIR": "/tmp/jobapp-test-uploads",
        "ALLOWED_JOB_SOURCE_DOMAINS": "sg.jobstreet.com,www.mycareersfuture.gov.sg",
        "FRONTEND_BASE_URL": "http://localhost:8080",
        "SESSION_EXPIRE_MINUTES": 480,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("DATABASE_URL", "sqlite:///tmp.db"),
        ("REDIS_URL", "http://localhost:6379"),
        ("FRONTEND_BASE_URL", "https://user:pass@example.com"),
        ("SESSION_COOKIE_NAME", "bad cookie"),
        ("SESSION_EXPIRE_MINUTES", 5),
        ("ALLOWED_JOB_SOURCE_DOMAINS", "https://sg.jobstreet.com/path"),
        ("SMTP_HOST", "smtp.example.com:587"),
        ("SMTP_FROM_EMAIL", "not-an-email"),
    ],
)
def test_config_rejects_malformed_security_sensitive_values(field: str, value: object) -> None:
    kwargs = base_settings_kwargs()
    kwargs[field] = value

    with pytest.raises(ValueError):
        Settings(**kwargs)


def test_config_accepts_explicit_trust_proxy_setting() -> None:
    kwargs = base_settings_kwargs()
    kwargs["TRUST_PROXY_HEADERS"] = True

    settings = Settings(**kwargs)

    assert settings.trust_proxy_headers is True


def production_kwargs() -> dict[str, object]:
    kwargs = base_settings_kwargs()
    kwargs.update(
        {
            "APP_ENV": "production",
            "FRONTEND_BASE_URL": "https://jobs.mycompany.sg",
            "SESSION_SECRET": "s" * 40,
            "PASSWORD_RESET_SECRET": "r" * 40,
            "SMTP_HOST": "email-smtp.ap-southeast-1.amazonaws.com",
            "SMTP_FROM_EMAIL": "noreply@mycompany.sg",
            "GEMINI_API_KEY": "real-looking-key-123",
        }
    )
    return kwargs


def test_production_accepts_valid_configuration() -> None:
    settings = Settings(_env_file=None, **production_kwargs())
    assert settings.secure_cookies is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("FRONTEND_BASE_URL", "http://jobs.mycompany.sg"),
        ("FRONTEND_BASE_URL", "https://localhost"),
        ("SESSION_SECRET", "change-me-generate-with-openssl-rand-base64-48"),
        ("PASSWORD_RESET_SECRET", "replace-with-a-real-secret-value-0000000"),
        ("GEMINI_API_KEY", "change-me"),
        ("DATABASE_URL", "postgresql+psycopg://jobapp:change-me@postgres:5432/jobapp"),
        ("PASSWORD_RESET_SECRET", "s" * 40),
    ],
)
def test_production_rejects_unsafe_configuration(field: str, value: str) -> None:
    kwargs = production_kwargs()
    kwargs[field] = value
    with pytest.raises(ValueError):
        Settings(_env_file=None, **kwargs)
