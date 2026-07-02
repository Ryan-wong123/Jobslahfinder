import os
import pytest

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test_user:test_password@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("SESSION_SECRET", "test_session_secret_value_at_least_32_chars")
os.environ.setdefault("PASSWORD_RESET_SECRET", "test_reset_secret_value_at_least_32_chars")
os.environ.setdefault("UPLOAD_DIR", "/tmp/jobapp-test-uploads")
os.environ.setdefault(
    "ALLOWED_JOB_SOURCE_DOMAINS",
    "sg.jobstreet.com,www.mycareersfuture.gov.sg,www.jobslah.com,www.fastjobs.sg",
)
os.environ.setdefault("RISK_ENGINE_DATA_DIR", "risk_engine_data_test")

@pytest.fixture(autouse=True)
def reset_risk_engine_storage():
    from risk_engine.db.db_setup import AuditBase, Base, audit_engine, engine

    Base.metadata.drop_all(bind=engine)
    AuditBase.metadata.drop_all(bind=audit_engine)
    Base.metadata.create_all(bind=engine)
    AuditBase.metadata.create_all(bind=audit_engine)
    yield

