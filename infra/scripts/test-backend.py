"""Run isolated backend tests without inheriting production dotenv settings."""
import os
from pathlib import Path
import sys
import uuid

root = Path(__file__).resolve().parents[2]
os.environ.update({
    "APP_ENV": "test", "SERVICE_ROLE": "api", "DEBUG": "false",
    "DATABASE_URL": "postgresql+psycopg://test_user:test_password@127.0.0.1:5432/test_db",
    "REDIS_URL": "redis://127.0.0.1:6379/15",
    "SESSION_SECRET": "test_session_secret_value_at_least_32_chars",
    "PASSWORD_RESET_SECRET": "test_reset_secret_value_at_least_32_chars",
    "UPLOAD_DIR": str(root / ".tmp/test-uploads"),
    "RISK_ENGINE_DATA_DIR": str(root / ".tmp/test-risk"),
    "RESUME_EXTRACTION_PROVIDER": "local", "COVER_LETTER_GENERATION_PROVIDER": "local",
    "FRONTEND_BASE_URL": "http://testserver",
    "ALLOWED_JOB_SOURCE_DOMAINS": "sg.jobstreet.com,www.mycareersfuture.gov.sg,www.jobslah.com,www.fastjobs.sg",
})
os.chdir(root / "backend")
sys.path.insert(0, str(root / "backend"))
import pytest
raise SystemExit(pytest.main(["--basetemp", str(root / ".tmp" / f"pytest-{uuid.uuid4().hex}"), *sys.argv[1:]]))
