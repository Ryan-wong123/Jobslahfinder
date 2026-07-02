from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import re

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.job import JobPosting
from app.schemas.job_roles import JobRoleDetailResponse, JobRoleListResponse, JobRoleSummaryResponse
from app.schemas.jobs import SalaryTrendPointResponse
from app.services.jobs import clean_text, job_to_summary_response, monthly_salary_midpoint, safe_response_text


MAX_ROLE_GROUPS = 40
MAX_JOBS_TO_ANALYZE = 1000
ROLE_TITLE_MAX_WORDS = 6
WORD_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z+#.\-]{1,}")
SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+|\n+")
SLUG_PATTERN = re.compile(r"[^a-z0-9]+")
SEPARATOR_PATTERN = re.compile(r"\s+[-|]\s+|\s+\bat\b\s+", re.IGNORECASE)

TITLE_PREFIXES = {
    "senior",
    "junior",
    "lead",
    "principal",
    "associate",
    "assistant",
    "entry",
    "head",
    "chief",
    "regional",
}
TITLE_SUFFIXES = {
    "contract",
    "intern",
    "internship",
    "temporary",
    "temp",
    "part",
    "full",
    "remote",
    "hybrid",
    "singapore",
}
SKILL_KEYWORDS = {
    "python": "Python",
    "java": "Java",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "react": "React",
    "next.js": "Next.js",
    "node": "Node.js",
    "sql": "SQL",
    "postgresql": "PostgreSQL",
    "mysql": "MySQL",
    "aws": "AWS",
    "azure": "Azure",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "linux": "Linux",
    "cybersecurity": "Cybersecurity",
    "security": "Security",
    "incident": "Incident response",
    "testing": "Testing",
    "api": "API design",
    "data": "Data analysis",
    "excel": "Excel",
    "tableau": "Tableau",
    "power bi": "Power BI",
    "communication": "Communication",
    "stakeholder": "Stakeholder management",
    "project": "Project management",
    "sales": "Sales",
    "marketing": "Marketing",
    "customer": "Customer service",
}
TASK_HINTS = (
    "develop",
    "design",
    "build",
    "manage",
    "support",
    "monitor",
    "analyze",
    "analyse",
    "maintain",
    "coordinate",
    "implement",
    "review",
    "prepare",
    "lead",
    "collaborate",
    "troubleshoot",
)
ROLE_FAMILY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Backend Developer", ("backend", "back-end", "api", "server")),
    ("Frontend Developer", ("frontend", "front-end", "react", "ui")),
    ("DevOps Engineer", ("devops", "sre", "site reliability", "cloud engineer", "platform engineer")),
    ("Software Engineer", ("software", "developer", "engineer", "programmer", "fullstack", "full-stack")),
    ("Data Analyst", ("data analyst", "business analyst", "analytics", "reporting", "bi analyst")),
    ("Data Engineer", ("data engineer", "etl", "pipeline")),
    ("Security Analyst", ("security analyst", "cybersecurity", "soc", "information security", "it security")),
    ("Product Manager", ("product manager", "product owner")),
    ("Project Manager", ("project manager", "programme manager", "program manager")),
    ("Marketing Executive", ("marketing", "digital marketing", "seo", "sem")),
    ("Sales Executive", ("sales", "business development", "account executive")),
    ("Customer Service Officer", ("customer service", "customer support", "call centre", "call center")),
    ("Human Resources Executive", ("human resource", "hr executive", "recruiter", "talent acquisition")),
    ("Finance Executive", ("finance", "accounting", "accounts", "audit")),
    ("Operations Executive", ("operations", "admin executive", "administrator")),
)


@dataclass(frozen=True)
class DynamicRole:
    slug: str
    name: str
    category: str
    keywords: tuple[str, ...]
    jobs: tuple[JobPosting, ...]


def slugify(value: str) -> str:
    slug = SLUG_PATTERN.sub("-", value.strip().lower()).strip("-")
    return slug[:80] or "job-role"


def display_title(value: str) -> str:
    return " ".join(word.capitalize() if word.islower() else word for word in value.split())


def normalize_role_title(title: str) -> str:
    title = SEPARATOR_PATTERN.split(title, maxsplit=1)[0]
    title = re.sub(r"\([^)]*\)|\[[^]]*]", " ", title)
    lower_title = title.lower()
    for family_name, markers in ROLE_FAMILY_RULES:
        if any(marker in lower_title for marker in markers):
            return family_name

    words = [word.lower().strip(".-/") for word in WORD_PATTERN.findall(title)]
    words = [word for word in words if word and word not in TITLE_PREFIXES]
    while words and words[-1] in TITLE_SUFFIXES:
        words.pop()
    if not words:
        return "General Role"
    return display_title(" ".join(words[:ROLE_TITLE_MAX_WORDS]))


def visible_jobs_statement():
    return (
        select(JobPosting)
        .options(selectinload(JobPosting.source))
        .where(
            JobPosting.is_active.is_(True),
            JobPosting.is_suspicious.is_(False),
        )
        .order_by(JobPosting.posting_date.desc().nullslast(), JobPosting.scraped_at.desc(), JobPosting.id.desc())
        .limit(MAX_JOBS_TO_ANALYZE)
    )


def build_dynamic_roles(db: Session) -> list[DynamicRole]:
    jobs = list(db.scalars(visible_jobs_statement()).all())
    grouped: dict[str, list[JobPosting]] = defaultdict(list)
    for job in jobs:
        grouped[normalize_role_title(job.title)].append(job)

    roles: list[DynamicRole] = []
    for role_name, role_jobs in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))[:MAX_ROLE_GROUPS]:
        category = Counter(
            safe_response_text(job.category, max_length=100) or "General" for job in role_jobs
        ).most_common(1)[0][0]
        keywords = tuple(
            dict.fromkeys(
                [role_name, *[clean_text(job.title, max_length=100) for job in role_jobs[:12]]]
            )
        )
        roles.append(
            DynamicRole(
                slug=slugify(role_name),
                name=role_name,
                category=category,
                keywords=keywords,
                jobs=tuple(role_jobs),
            )
        )
    return roles


def typical_salary_for_jobs(jobs: tuple[JobPosting, ...] | list[JobPosting]) -> float | None:
    salaries = [monthly_salary_midpoint(job) for job in jobs]
    values = [value for value in salaries if value is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def salary_points_for_jobs(jobs: tuple[JobPosting, ...] | list[JobPosting], *, months: int = 12) -> list[SalaryTrendPointResponse]:
    buckets: dict[str, list[float]] = {}
    for job in jobs:
        midpoint = monthly_salary_midpoint(job)
        if midpoint is None:
            continue
        bucket_date = job.posting_date or job.scraped_at.date()
        buckets.setdefault(bucket_date.strftime("%Y-%m"), []).append(midpoint)

    return [
        SalaryTrendPointResponse(
            period=period,
            average_salary=round(sum(values) / len(values), 2),
            sample_count=len(values),
        )
        for period, values in sorted(buckets.items())[-months:]
    ]


def category_salary_fallback_jobs(db: Session, category: str) -> list[JobPosting]:
    jobs = list(db.scalars(visible_jobs_statement()).all())
    return [
        job
        for job in jobs
        if (safe_response_text(job.category, max_length=100) or "General") == category
        and monthly_salary_midpoint(job) is not None
    ]


def extract_skills(jobs: tuple[JobPosting, ...] | list[JobPosting]) -> list[str]:
    text = " ".join(
        filter(
            None,
            [
                *(job.title for job in jobs),
                *(job.category for job in jobs),
                *(job.description for job in jobs),
            ],
        )
    ).lower()
    counts: Counter[str] = Counter()
    for token, label in SKILL_KEYWORDS.items():
        if token in text:
            counts[label] += text.count(token)
    return [skill for skill, _count in counts.most_common(10)]


def extract_tasks(jobs: tuple[JobPosting, ...] | list[JobPosting], role_name: str) -> list[str]:
    candidates: list[str] = []
    for job in jobs[:8]:
        if not job.description:
            continue
        for sentence in SENTENCE_PATTERN.split(job.description):
            cleaned = clean_text(sentence, max_length=180)
            lower = cleaned.lower()
            if 35 <= len(cleaned) <= 180 and any(hint in lower for hint in TASK_HINTS):
                candidates.append(cleaned.rstrip(".") + ".")
            if len(candidates) >= 6:
                return list(dict.fromkeys(candidates))
    if candidates:
        return list(dict.fromkeys(candidates))
    return [
        f"Review and respond to requirements found in current {role_name} job postings.",
        "Work with internal teams or customers to deliver the outcomes described by employers.",
        "Maintain clear documentation, communication, and progress tracking for assigned work.",
    ]


def role_tagline(role: DynamicRole) -> str:
    companies = len({job.company for job in role.jobs})
    return f"Based on {len(role.jobs)} current scraped postings from {companies} employer{'s' if companies != 1 else ''}."


def role_overview(role: DynamicRole, skills: list[str]) -> str:
    skill_text = ", ".join(skills[:5]) if skills else "the skills repeatedly mentioned in current postings"
    return (
        f"This role profile is generated from stored job postings for {role.name}. "
        f"The current dataset shows demand across {len(role.jobs)} visible posting{'s' if len(role.jobs) != 1 else ''}, "
        f"mostly in {role.category}. Common signals in these postings include {skill_text}."
    )


def become_steps(role: DynamicRole, skills: list[str]) -> tuple[str, ...]:
    skill_step = (
        f"Build evidence for the most common requested skills: {', '.join(skills[:5])}."
        if skills
        else "Build evidence for the tools, responsibilities, and domain terms repeated in matching job descriptions."
    )
    return (
        f"Read several current {role.name} postings and list the repeated requirements.",
        skill_step,
        "Prepare a resume section or portfolio example that maps your experience to those requirements.",
        "Apply first to postings where your current skills match most of the required responsibilities.",
    )


def role_to_summary(role: DynamicRole) -> JobRoleSummaryResponse:
    return JobRoleSummaryResponse(
        slug=role.slug,
        name=role.name,
        tagline=role_tagline(role),
        category=role.category,
        job_count=len(role.jobs),
        typical_monthly_salary=typical_salary_for_jobs(role.jobs),
    )


def list_job_roles(db: Session) -> JobRoleListResponse:
    return JobRoleListResponse(items=[role_to_summary(role) for role in build_dynamic_roles(db)])


def get_job_role_detail(db: Session, slug: str) -> JobRoleDetailResponse | None:
    role = next((candidate for candidate in build_dynamic_roles(db) if candidate.slug == slug), None)
    if role is None:
        return None

    latest_jobs = sorted(
        role.jobs,
        key=lambda job: (job.posting_date is not None, job.posting_date, job.scraped_at, job.id),
        reverse=True,
    )[:5]
    skills = extract_skills(role.jobs)
    salary_points = salary_points_for_jobs(role.jobs, months=12)
    if not salary_points:
        salary_points = salary_points_for_jobs(category_salary_fallback_jobs(db, role.category), months=12)
    summary = role_to_summary(role)
    return JobRoleDetailResponse(
        **summary.model_dump(),
        overview=role_overview(role, skills),
        tasks=extract_tasks(role.jobs, role.name),
        how_to_become_intro=(
            f"Use the live {role.name} postings in this platform as the roadmap source. "
            "The steps below are generated from the currently scraped jobs and should be refreshed after new scraping runs."
        ),
        how_to_become_steps=list(become_steps(role, skills)),
        top_skills=skills,
        salary_points=salary_points,
        latest_jobs=[job_to_summary_response(job) for job in latest_jobs],
    )
