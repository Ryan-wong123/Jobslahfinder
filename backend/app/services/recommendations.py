from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session, selectinload

from app.models.account import User
from app.models.activity import Recommendation
from app.models.enums import AuditOutcome, ProcessingStatus, UploadStatus
from app.models.job import JobPosting
from app.models.resume import Resume, ResumeExtraction
from app.security.text import sanitize_text
from app.services.application_history import add_application_history
from app.services.audit import create_audit_log
from app.services.resumes import looks_like_prompt_instruction


MAX_RECOMMENDATIONS = 25
SCORING_VERSION = "deterministic-v1"
WORD_PATTERN = re.compile(r"[a-z0-9][a-z0-9.+#-]*")
SENIOR_TERMS = {"senior", "lead", "principal", "manager", "architect"}
JUNIOR_TERMS = {"junior", "associate", "entry", "graduate", "intern"}
GENERIC_PROFILE_TERMS = {
    "api",
    "apis",
    "built",
    "build",
    "developer",
    "engineer",
    "systems",
}


class RecommendationInputMissingError(ValueError):
    pass


@dataclass(frozen=True)
class ProfileSignals:
    resume_id: int
    extraction_id: int
    skills: tuple[str, ...]
    skill_terms: frozenset[str]
    experience_terms: frozenset[str]
    education_terms: frozenset[str]
    years_experience: float | None


@dataclass(frozen=True)
class ScoredJob:
    job: JobPosting
    score: float
    rationale: str
    metadata: dict[str, object]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def json_items(value: dict | None) -> list:
    if not isinstance(value, dict):
        return []
    items = value.get("items")
    return items if isinstance(items, list) else []


def normalize_phrase(value: object, *, max_chars: int = 80) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned_text = sanitize_text(
        value,
        field_name="profile signal",
        max_length=max_chars,
        empty_to_none=True,
        html_policy="strip",
        overflow="truncate",
        control_policy="strip",
        collapse_whitespace=True,
        allow_multiline=False,
    )
    if cleaned_text is None:
        return None
    cleaned = re.sub(r"\s+", " ", cleaned_text).strip().casefold()
    if not cleaned:
        return None
    return cleaned[:max_chars]


def text_terms(*values: object) -> frozenset[str]:
    terms: set[str] = set()
    for value in values:
        if isinstance(value, str):
            if looks_like_prompt_instruction(value):
                continue
            cleaned = sanitize_text(
                value,
                field_name="recommendation text",
                max_length=2000,
                empty_to_none=True,
                html_policy="strip",
                overflow="truncate",
                control_policy="strip",
                collapse_whitespace=True,
            )
            if cleaned:
                terms.update(WORD_PATTERN.findall(cleaned.casefold()))
    return frozenset(term[:40] for term in terms if len(term) >= 2 and term not in GENERIC_PROFILE_TERMS)


def latest_completed_profile(db: Session, *, user_id: int) -> ProfileSignals | None:
    extraction = db.scalar(
        select(ResumeExtraction)
        .join(Resume)
        .where(
            Resume.user_id == user_id,
            Resume.upload_status == UploadStatus.STORED.value,
            ResumeExtraction.processing_status == ProcessingStatus.COMPLETED.value,
        )
        .order_by(desc(ResumeExtraction.processed_at), desc(ResumeExtraction.id))
    )
    if extraction is None:
        return None

    skills: list[str] = []
    skill_terms: set[str] = set()
    for item in json_items(extraction.skills_json):
        skill = normalize_phrase(item)
        if skill and skill not in skill_terms:
            skills.append(skill)
            skill_terms.add(skill)

    experience_terms: set[str] = set()
    for item in json_items(extraction.experience_json):
        if isinstance(item, dict):
            experience_terms.update(text_terms(item.get("title"), item.get("company")))

    education_terms: set[str] = set()
    for item in json_items(extraction.education_json):
        if isinstance(item, dict):
            education_terms.update(text_terms(item.get("credential"), item.get("field"), item.get("institution")))

    return ProfileSignals(
        resume_id=extraction.resume_id,
        extraction_id=extraction.id,
        skills=tuple(skills),
        skill_terms=frozenset(skill_terms),
        experience_terms=frozenset(experience_terms),
        education_terms=frozenset(education_terms),
        years_experience=float(extraction.years_experience)
        if extraction.years_experience is not None
        else None,
    )


def job_search_text(job: JobPosting) -> str:
    return " ".join(
        value
        for value in [job.title, job.location, job.category, job.description]
        if value
    ).casefold()


def score_job(job: JobPosting, profile: ProfileSignals) -> ScoredJob:
    haystack = job_search_text(job)
    job_terms = text_terms(haystack)

    matched_skills = tuple(skill for skill in profile.skills if skill in haystack)
    skill_score = 0.0
    if profile.skills:
        skill_score = min(65.0, (len(matched_skills) / len(profile.skills)) * 65.0)

    experience_overlap = profile.experience_terms.intersection(job_terms)
    experience_score = min(10.0, len(experience_overlap) * 2.0)
    years_signal = "not_used"
    has_domain_signal = bool(matched_skills or experience_overlap)
    if profile.years_experience is not None and has_domain_signal:
        if profile.years_experience >= 5 and SENIOR_TERMS.intersection(job_terms):
            experience_score += 15.0
            years_signal = "senior_alignment"
        elif profile.years_experience <= 2 and JUNIOR_TERMS.intersection(job_terms):
            experience_score += 12.0
            years_signal = "junior_alignment"
        else:
            experience_score += 6.0
            years_signal = "experience_available"

    education_overlap = profile.education_terms.intersection(job_terms)
    education_score = min(10.0, len(education_overlap) * 2.5)
    has_domain_signal = has_domain_signal or bool(education_overlap)

    title_category_score = 0.0
    title_category = " ".join(value for value in [job.title, job.category] if value).casefold()
    if any(skill in title_category for skill in profile.skills):
        title_category_score = 10.0

    score = min(100.0, round(skill_score + experience_score + education_score + title_category_score, 2))

    rationale_parts: list[str] = []
    if matched_skills:
        display_skills = ", ".join(skill[:40] for skill in matched_skills[:5])
        rationale_parts.append(f"Matched profile skills: {display_skills}.")
    if experience_score > 0:
        rationale_parts.append("Experience signals align with this role.")
    if education_score > 0:
        rationale_parts.append("Education signals appear relevant.")
    if not rationale_parts:
        rationale_parts.append("Limited deterministic match signals found.")

    metadata = {
        "scoring_version": SCORING_VERSION,
        "matched_skill_count": len(matched_skills),
        "profile_skill_count": len(profile.skills),
        "experience_term_matches": len(experience_overlap),
        "education_term_matches": len(education_overlap),
        "years_experience_signal": years_signal,
    }
    return ScoredJob(job=job, score=score, rationale=" ".join(rationale_parts)[:1000], metadata=metadata)


def score_active_jobs(db: Session, profile: ProfileSignals) -> list[ScoredJob]:
    jobs = list(
        db.scalars(
            select(JobPosting)
            .options(selectinload(JobPosting.source))
            .where(JobPosting.is_active.is_(True), JobPosting.is_suspicious.is_(False))
        ).all()
    )
    scored = [score_job(job, profile) for job in jobs]
    positive_matches = [item for item in scored if item.score > 0]
    return sorted(positive_matches, key=lambda item: (-item.score, item.job.id))[:MAX_RECOMMENDATIONS]


def refresh_recommendations_for_user(
    db: Session,
    request,
    *,
    current_user: User,
) -> list[Recommendation]:
    profile = latest_completed_profile(db, user_id=current_user.id)
    if profile is None:
        create_audit_log(
            db,
            event_type="recommendation.refresh",
            outcome=AuditOutcome.FAILURE,
            request=request,
            user_id=current_user.id,
            target_type="recommendation",
            details={"reason": "no_completed_extraction"},
        )
        db.commit()
        raise RecommendationInputMissingError("No completed resume extraction is available.")

    scored_jobs = score_active_jobs(db, profile)
    db.execute(delete(Recommendation).where(Recommendation.user_id == current_user.id))

    generated_at = utc_now()
    recommendations: list[Recommendation] = []
    for rank, scored in enumerate(scored_jobs, start=1):
        recommendation = Recommendation(
            user_id=current_user.id,
            job_id=scored.job.id,
            resume_id=profile.resume_id,
            match_score=scored.score,
            rank=rank,
            rationale=scored.rationale,
            metadata_json=scored.metadata,
            generated_at=generated_at,
        )
        db.add(recommendation)
        recommendations.append(recommendation)

    add_application_history(
        db,
        user_id=current_user.id,
        action_type="recommendations_refreshed",
    )
    create_audit_log(
        db,
        event_type="recommendation.refresh",
        outcome=AuditOutcome.SUCCESS,
        request=request,
        user_id=current_user.id,
        target_type="recommendation",
        details={
            "recommendation_count": len(recommendations),
            "resume_id": profile.resume_id,
            "extraction_id": profile.extraction_id,
            "scoring_version": SCORING_VERSION,
        },
    )
    db.commit()
    for recommendation in recommendations:
        db.refresh(recommendation)
    return recommendations
