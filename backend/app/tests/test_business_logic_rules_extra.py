from datetime import date

from pydantic import ValidationError

from app.models.job import JobPosting
from app.schemas.roadmaps import RoadmapCreateRequest
from app.services.job_roles import (
    extract_skills,
    normalize_role_title,
    salary_points_for_jobs,
    typical_salary_for_jobs,
)
from app.services.roadmaps import build_roadmap, roadmap_focus_for_role, safe_milestones


def test_business_logic_role_title_normalization_groups_common_variants() -> None:
    assert normalize_role_title("Senior Backend Engineer - Payments") == "Backend Developer"
    assert normalize_role_title("Frontend React Developer at Startup") == "Frontend Developer"
    assert normalize_role_title("Cybersecurity SOC Analyst (Shift)") == "Security Analyst"


def test_business_logic_salary_points_ignore_jobs_without_salary_and_bucket_by_month() -> None:
    jobs = [
        JobPosting(
            title="Backend Developer",
            company="A",
            job_url="https://sg.jobstreet.com/job/1",
            content_hash="one",
            source_id=1,
            salary_min=4000,
            salary_max=6000,
            salary_period="month",
            posting_date=date(2026, 1, 15),
        ),
        JobPosting(
            title="Backend Developer",
            company="B",
            job_url="https://sg.jobstreet.com/job/2",
            content_hash="two",
            source_id=1,
            salary_min=6000,
            salary_max=8000,
            salary_period="month",
            posting_date=date(2026, 1, 20),
        ),
        JobPosting(
            title="Backend Developer",
            company="C",
            job_url="https://sg.jobstreet.com/job/3",
            content_hash="three",
            source_id=1,
            salary_period=None,
            posting_date=date(2026, 2, 1),
        ),
    ]

    assert typical_salary_for_jobs(jobs) == 6000
    assert [point.model_dump() for point in salary_points_for_jobs(jobs)] == [
        {"period": "2026-01", "average_salary": 6000.0, "sample_count": 2}
    ]


def test_business_logic_skill_extraction_counts_signals_from_titles_categories_and_descriptions() -> None:
    jobs = [
        JobPosting(
            title="Python Security Engineer",
            company="A",
            category="Cybersecurity",
            description="Build Python APIs, monitor Linux systems, and improve Docker deployments.",
            job_url="https://sg.jobstreet.com/job/1",
            content_hash="one",
            source_id=1,
        )
    ]

    extracted = extract_skills(jobs)

    assert extracted[0] == "Python"
    assert {"Security", "Cybersecurity", "Docker", "Linux"}.issubset(extracted)


def test_business_logic_roadmap_schema_deduplicates_skills_and_rejects_html() -> None:
    request = RoadmapCreateRequest(
        target_role="Security Analyst",
        target_level="JUNIOR",
        timeline_months=6,
        current_skills=["Python", " python ", "SQL"],
        notes="Building portfolio evidence",
    )

    assert request.current_skills == ["Python", "SQL"]

    try:
        RoadmapCreateRequest(
            target_role="<script>alert(1)</script>",
            target_level="JUNIOR",
            timeline_months=6,
            current_skills=[],
        )
    except ValidationError as exc:
        assert "Invalid target_role" in str(exc) or "Invalid target role" in str(exc)
    else:
        raise AssertionError("HTML target role should be rejected")


def test_business_logic_generated_roadmap_uses_role_specific_focus_and_bounds_milestones() -> None:
    request = RoadmapCreateRequest(
        target_role="Cloud Security Engineer",
        target_level="MID",
        timeline_months=8,
        current_skills=["Python"],
    )

    assert roadmap_focus_for_role(request.target_role) == [
        "secure coding basics",
        "threat modeling",
        "security testing evidence",
    ]

    roadmap = build_roadmap(request)
    milestones = safe_milestones(roadmap["milestones"], timeline_months=request.timeline_months)

    assert len(milestones) == 4
    assert milestones[0]["month"] == 1
    assert milestones[-1]["month"] == 8
    assert all(1 <= milestone["month"] <= 8 for milestone in milestones)
