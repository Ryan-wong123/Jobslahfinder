from __future__ import annotations

from typing import Any


def fetch_jobslah_jobs(*, timeout_seconds: int) -> list[dict[str, Any]]:
    """Coursework-safe JobsLah adapter with the production data shape."""
    _ = timeout_seconds
    return [
        {
            "external_job_id": "jobslah-demo-1",
            "title": "Application Security Engineer",
            "company": "JobsLah Demo Employer",
            "location": "Singapore",
            "category": "Information Security",
            "description": "Review application risks, support secure SDLC, and document remediation plans.",
            "job_url": "https://www.jobslah.com/sg/jobsearch/application-security-engineer-demo",
            "posting_date": "2026-04-27",
        }
    ]
