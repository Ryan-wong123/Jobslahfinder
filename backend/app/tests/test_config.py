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


def test_role_discovery_defaults_use_dbscan_and_require_admin_approval() -> None:
    settings = Settings(**base_settings_kwargs())

    assert settings.role_discovery_enabled is False
    assert settings.role_discovery_model == "sentence-transformers/all-MiniLM-L6-v2"
    assert settings.role_discovery_dbscan_eps == 0.35
    assert settings.role_discovery_dbscan_min_samples == 5
    assert settings.role_discovery_require_admin_approval is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ROLE_DISCOVERY_MODEL", " "),
        ("ROLE_DISCOVERY_DBSCAN_EPS", 0),
        ("ROLE_DISCOVERY_DBSCAN_EPS", 2.1),
        ("ROLE_DISCOVERY_DBSCAN_MIN_SAMPLES", 1),
        ("ROLE_DISCOVERY_REQUIRE_ADMIN_APPROVAL", False),
    ],
)
def test_config_rejects_unsafe_role_discovery_settings(field: str, value: object) -> None:
    kwargs = base_settings_kwargs()
    kwargs[field] = value

    with pytest.raises(ValueError):
        Settings(**kwargs)
