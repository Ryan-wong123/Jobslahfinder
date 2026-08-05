from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base
from app.models.job import JobPosting, JobSource
from app.schemas.jobs import SalaryComparisonQuery
from app.services.jobs import get_salary_comparison, normalize_minimum_experience


@pytest.fixture
def comparison_db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def add_job(db: Session, source: JobSource, *, role: str, index: int, salary: float | None, experience: str | None) -> None:
    db.add(JobPosting(
        source_id=source.id,
        external_job_id=f"{role}-{index}",
        title=role,
        company=f"Company {index}",
        job_url=f"https://sg.jobstreet.com/job/{role.lower().replace(' ', '-')}-{index}",
        posting_date=date(2026, 8, 1),
        salary_min=salary,
        salary_max=salary + 1000 if salary is not None else None,
        salary_currency="SGD" if salary is not None else None,
        salary_period="month" if salary is not None else None,
        minimum_experience=experience,
        content_hash=f"hash-{role}-{index}",
    ))


def test_experience_normalization_preserves_explicit_zero_and_rejects_out_of_range() -> None:
    assert normalize_minimum_experience("At least 3 years") == 3
    assert normalize_minimum_experience("3-5 years") == 3
    assert normalize_minimum_experience("Fresh graduate welcome") == 0
    assert normalize_minimum_experience("No experience required") == 0
    assert normalize_minimum_experience("51 years") is None
    assert normalize_minimum_experience("Competitive experience") is None


def test_comparison_query_strictly_validates_roles_and_pagination() -> None:
    query = SalaryComparisonQuery(roles=["Software Engineer", "Data Analyst"], page=1, page_size=2)
    assert query.roles == ["Software Engineer", "Data Analyst"]
    for invalid in (
        {"roles": ["Only one"]},
        {"roles": ["A", "Data Analyst"]},
        {"roles": ["Data Analyst", "data analyst"]},
        {"roles": ["One", "Two", "Three", "Four", "Five"]},
        {"roles": ["One", "Two"], "page_size": 5},
    ):
        with pytest.raises(ValidationError):
            SalaryComparisonQuery(**invalid)


def test_salary_comparison_threshold_experience_coverage_and_pagination(comparison_db: Session) -> None:
    source = JobSource(source_name="JobStreet", base_url="https://sg.jobstreet.com")
    comparison_db.add(source)
    comparison_db.flush()
    experience = ["At least 3 years", "3-5 years", "Fresh graduate welcome", None, "51 years"]
    for index in range(5):
        add_job(comparison_db, source, role="Software Engineer", index=index, salary=4000 + index * 1000, experience=experience[index])
    for index in range(4):
        add_job(comparison_db, source, role="Data Analyst", index=index, salary=3000 + index * 500, experience="2 years")
    comparison_db.commit()

    first_page = get_salary_comparison(
        comparison_db, roles=["Software Engineer", "Data Analyst"], page=1, page_size=1
    )
    assert first_page.total == 2
    assert len(first_page.items) == 1
    software = first_page.items[0]
    assert software.minimum_salary == 4000
    assert software.maximum_salary == 9000
    assert software.median_salary == 6500
    assert software.average_salary == 6500
    assert software.valid_posting_count == 5
    assert software.median_minimum_experience_years == 3
    assert software.experience_data_coverage_percentage == 60
    assert software.statistics_available is True

    second_page = get_salary_comparison(
        comparison_db, roles=["Software Engineer", "Data Analyst"], page=2, page_size=1
    )
    analyst = second_page.items[0]
    assert analyst.valid_posting_count == 4
    assert analyst.statistics_available is False
    assert analyst.minimum_salary is None
    assert analyst.median_minimum_experience_years == 2


def test_nullable_job_metadata_is_optional_and_stored(comparison_db: Session) -> None:
    source = JobSource(source_name="JobStreet", base_url="https://sg.jobstreet.com")
    comparison_db.add(source)
    comparison_db.flush()
    job = JobPosting(
        source_id=source.id, title="Developer", company="Example", job_url="https://sg.jobstreet.com/job/1",
        content_hash="metadata", employment_type=None, workplace_type=None, seniority_level=None,
        skills=None, closing_date=None,
    )
    comparison_db.add(job)
    comparison_db.commit()
    assert comparison_db.get(JobPosting, job.id).skills is None
