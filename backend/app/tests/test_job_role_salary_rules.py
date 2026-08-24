from decimal import Decimal

import pytest

from app.models.job import JobPosting
from app.services.job_roles import (
    experience_band_for_years,
    normalized_monthly_salary,
    parse_minimum_experience_years,
)


@pytest.mark.parametrize(
    ("years", "expected"),
    [(0, "entry"), (2, "entry"), (3, "mid-level"), (5, "mid-level"), (6, "senior"), (9, "senior"), (10, "lead-expert")],
)
def test_experience_band_boundaries(years: int, expected: str) -> None:
    assert experience_band_for_years(years) == expected
    assert parse_minimum_experience_years(f"{years} years") == years


@pytest.mark.parametrize(
    ("period", "salary", "expected"),
    [("month", 6000, 6000), ("year", 72000, 6000), ("week", 1200, 5200), ("day", 240, 5200), ("hour", 30, 5200)],
)
def test_salary_period_conversion_assumptions(period: str, salary: float, expected: float) -> None:
    job = JobPosting(
        salary_min=Decimal(str(salary)),
        salary_max=Decimal(str(salary)),
        salary_currency="SGD",
        salary_period=period,
    )
    assert normalized_monthly_salary(job) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("lower", "upper", "currency", "period"),
    [(None, 5000, "SGD", "month"), (6000, 5000, "SGD", "month"), (4000, 5000, "USD", "month"), (4000, 5000, "SGD", "fortnight")],
)
def test_invalid_salary_data_is_excluded(lower, upper, currency: str, period: str) -> None:
    job = JobPosting(salary_min=lower, salary_max=upper, salary_currency=currency, salary_period=period)
    assert normalized_monthly_salary(job) is None
