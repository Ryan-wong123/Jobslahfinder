from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.account import User
from app.models.enums import AuditOutcome
from app.models.roadmap import JobRoleRoadmap
from app.schemas.roadmaps import (
    JobRoleRoadmapListResponse,
    JobRoleRoadmapResponse,
    RoadmapCreateRequest,
    RoadmapUpdateRequest,
)
from app.security.auth import assert_owner_or_admin
from app.security.text import sanitize_text
from app.services.audit import create_audit_log
from app.services.jobs import DEFAULT_PAGE_SIZE


class RoadmapNotFoundError(ValueError):
    pass


ROLE_FOCUS: dict[str, list[str]] = {
    "data": ["Python and SQL foundations", "analytics portfolio", "business communication"],
    "security": ["secure coding basics", "threat modeling", "security testing evidence"],
    "software": ["backend and frontend fundamentals", "testing discipline", "deployment workflow"],
    "cloud": ["cloud architecture basics", "container operations", "monitoring and cost awareness"],
    "ai": ["model evaluation basics", "data handling safety", "responsible AI workflow"],
}


def roadmap_focus_for_role(target_role: str) -> list[str]:
    normalized = target_role.casefold()
    for key, focus in ROLE_FOCUS.items():
        if key in normalized:
            return focus
    return ["role fundamentals", "portfolio evidence", "interview preparation"]


def skill_gap_actions(current_skills: list[str], focus: str) -> list[str]:
    current = {skill.casefold() for skill in current_skills}
    if any(part in " ".join(current) for part in focus.casefold().split()):
        return [f"Deepen {focus} with one practical mini-project."]
    return [f"Learn {focus} through a guided course or documentation path."]


def build_roadmap(payload: RoadmapCreateRequest) -> dict:
    focus_items = roadmap_focus_for_role(payload.target_role)
    interval = max(1, payload.timeline_months // 4)
    months = sorted({1, min(payload.timeline_months, 1 + interval), min(payload.timeline_months, 1 + interval * 2), payload.timeline_months})
    milestone_titles = ["Foundation", "Practice", "Portfolio", "Application readiness"]
    milestones = []

    for index, month in enumerate(months):
        focus = focus_items[min(index, len(focus_items) - 1)] if index < 3 else "job search preparation"
        actions = skill_gap_actions(payload.current_skills, focus)
        if index == 0:
            actions.append("Map job descriptions for this role into required skills and recurring keywords.")
        elif index == 1:
            actions.append("Build one small project that demonstrates the focus area.")
        elif index == 2:
            actions.append("Write a concise case study explaining your decisions, tradeoffs, and results.")
        else:
            actions.append("Tailor resume bullets and interview stories to the target role.")

        milestones.append(
            {
                "month": month,
                "title": milestone_titles[min(index, len(milestone_titles) - 1)],
                "focus": focus,
                "actions": actions,
                "evidence": [
                    "Updated resume/profile entry",
                    "Project, notes, certificate, or interview story showing progress",
                ],
            }
        )

    return {
        "version": "deterministic-job-role-roadmap-v1",
        "milestones": milestones,
    }


def safe_roadmap_text(value: object, *, max_length: int) -> str | None:
    if not isinstance(value, str):
        return None
    return sanitize_text(
        value,
        field_name="roadmap",
        max_length=max_length,
        empty_to_none=True,
        html_policy="strip",
        overflow="truncate",
        control_policy="strip",
        collapse_whitespace=True,
    )


def safe_roadmap_list(value: object, *, max_items: int = 10, max_length: int = 200) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    for item in value:
        text = safe_roadmap_text(item, max_length=max_length)
        if text:
            cleaned.append(text)
        if len(cleaned) >= max_items:
            break
    return cleaned


def safe_milestones(value: object, *, timeline_months: int) -> list[dict]:
    if not isinstance(value, list):
        return []
    milestones: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        month = item.get("month")
        if not isinstance(month, int):
            continue
        month = max(1, min(month, max(timeline_months, 1)))
        title = safe_roadmap_text(item.get("title"), max_length=120)
        focus = safe_roadmap_text(item.get("focus"), max_length=200)
        if not title or not focus:
            continue
        milestones.append(
            {
                "month": month,
                "title": title,
                "focus": focus,
                "actions": safe_roadmap_list(item.get("actions"), max_items=10, max_length=240),
                "evidence": safe_roadmap_list(item.get("evidence"), max_items=10, max_length=240),
            }
        )
        if len(milestones) >= 12:
            break
    return milestones


def roadmap_to_response(roadmap: JobRoleRoadmap) -> JobRoleRoadmapResponse:
    current_skills = []
    if isinstance(roadmap.current_skills_json, dict):
        items = roadmap.current_skills_json.get("items")
        current_skills = safe_roadmap_list(items, max_items=30, max_length=80)
    milestones = []
    if isinstance(roadmap.roadmap_json, dict):
        raw_milestones = roadmap.roadmap_json.get("milestones")
        milestones = safe_milestones(raw_milestones, timeline_months=roadmap.timeline_months)

    return JobRoleRoadmapResponse(
        id=roadmap.id,
        target_role=safe_roadmap_text(roadmap.target_role, max_length=120) or "Target role",
        target_level=roadmap.target_level,
        timeline_months=roadmap.timeline_months,
        current_skills=current_skills,
        milestones=milestones,
        notes=safe_roadmap_text(roadmap.notes, max_length=1000),
        status=roadmap.status,
        created_at=roadmap.created_at,
        updated_at=roadmap.updated_at,
    )


def create_roadmap_for_user(
    db: Session,
    request,
    *,
    current_user: User,
    payload: RoadmapCreateRequest,
) -> JobRoleRoadmapResponse:
    roadmap = JobRoleRoadmap(
        user_id=current_user.id,
        target_role=payload.target_role,
        target_level=payload.target_level,
        timeline_months=payload.timeline_months,
        current_skills_json={"items": payload.current_skills},
        roadmap_json=build_roadmap(payload),
        notes=payload.notes,
        status="ACTIVE",
    )
    db.add(roadmap)
    db.flush()
    create_audit_log(
        db,
        event_type="job_role_roadmap.create",
        outcome=AuditOutcome.SUCCESS,
        request=request,
        user_id=current_user.id,
        target_type="job_role_roadmap",
        target_id=roadmap.id,
        details={
            "target_role": roadmap.target_role,
            "target_level": roadmap.target_level,
            "timeline_months": roadmap.timeline_months,
            "skill_count": len(payload.current_skills),
        },
    )
    db.commit()
    db.refresh(roadmap)
    return roadmap_to_response(roadmap)


def list_roadmaps_for_user(
    db: Session,
    *,
    user_id: int,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> JobRoleRoadmapListResponse:
    base_stmt = select(JobRoleRoadmap).where(JobRoleRoadmap.user_id == user_id)
    total = db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0
    roadmaps = list(
        db.scalars(
            base_stmt.order_by(desc(JobRoleRoadmap.updated_at), desc(JobRoleRoadmap.id))
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return JobRoleRoadmapListResponse(
        items=[roadmap_to_response(roadmap) for roadmap in roadmaps],
        page=page,
        page_size=page_size,
        total=total,
    )


def get_roadmap_for_user(
    db: Session,
    request,
    *,
    current_user: User,
    roadmap_id: int,
) -> JobRoleRoadmapResponse:
    roadmap = db.get(JobRoleRoadmap, roadmap_id)
    if roadmap is None:
        raise RoadmapNotFoundError("Resource not found.")
    assert_owner_or_admin(
        db,
        request,
        current_user=current_user,
        owner_user_id=roadmap.user_id,
        target_type="job_role_roadmap",
        target_id=roadmap.id,
    )
    return roadmap_to_response(roadmap)


def update_roadmap_for_user(
    db: Session,
    request,
    *,
    current_user: User,
    roadmap_id: int,
    payload: RoadmapUpdateRequest,
) -> JobRoleRoadmapResponse:
    roadmap = db.get(JobRoleRoadmap, roadmap_id)
    if roadmap is None:
        raise RoadmapNotFoundError("Resource not found.")
    assert_owner_or_admin(
        db,
        request,
        current_user=current_user,
        owner_user_id=roadmap.user_id,
        target_type="job_role_roadmap",
        target_id=roadmap.id,
    )
    roadmap.status = payload.status
    create_audit_log(
        db,
        event_type="job_role_roadmap.update",
        outcome=AuditOutcome.SUCCESS,
        request=request,
        user_id=current_user.id,
        target_type="job_role_roadmap",
        target_id=roadmap.id,
        details={"status": payload.status},
    )
    db.commit()
    db.refresh(roadmap)
    return roadmap_to_response(roadmap)
