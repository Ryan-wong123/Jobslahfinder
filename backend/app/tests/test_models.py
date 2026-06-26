from app.models import Base


def test_required_table_metadata_imports() -> None:
    expected_tables = {
        "users",
        "sessions",
        "password_reset_tokens",
        "user_profiles",
        "resumes",
        "resume_extractions",
        "job_sources",
        "scraping_runs",
        "job_postings",
        "saved_jobs",
        "recommendations",
        "cover_letters",
        "application_history",
        "audit_logs",
    }

    assert expected_tables.issubset(set(Base.metadata.tables.keys()))
