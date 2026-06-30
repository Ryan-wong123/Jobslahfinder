from __future__ import annotations

from typing import Any


def fetch_fastjobs_jobs(*, timeout_seconds: int) -> list[dict[str, Any]]:
    """Coursework-safe FastJobs adapter with the production data shape."""
    _ = timeout_seconds
    return [
        {
            "external_job_id": "fastjobs-demo-1",
            "title": "IT Support Specialist",
            "company": "FastJobs Demo Employer",
            "location": "Singapore",
            "category": "Information Technology",
            "description": "Support endpoint troubleshooting, account access requests, and basic security checks.",
            "job_url": "https://www.fastjobs.sg/singapore-job-ad/it-support-specialist-demo",
            "posting_date": "2026-04-26",
        }
    ]
