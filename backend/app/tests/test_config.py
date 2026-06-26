from app.core.config import get_settings


def test_config_loads_from_environment() -> None:
    get_settings.cache_clear()
    settings = get_settings()

    assert settings.app_env == "test"
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert "sg.jobstreet.com" in settings.allowed_job_source_domains
    assert settings.debug is False
