"""Shared helpers for routers: serialisation, masking and lookups."""

from typing import Any, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import Collection, Run, TestCase, TestResult
from app.schemas import MASK, RunOut, TestCaseOut

M = TypeVar("M")


def mask_values(values: dict[str, Any] | None) -> dict[str, str]:
    return {k: MASK for k in (values or {})}


def merge_masked(incoming: dict[str, str], existing: dict[str, str] | None) -> dict[str, str]:
    """When the client echoes back the mask, keep the stored secret instead of overwriting it."""
    existing = existing or {}
    return {k: (existing.get(k, "") if v == MASK else v) for k, v in incoming.items()}


def get_in_project(db: Session, model: type[M], obj_id: int, project_id: int, label: str) -> M:
    obj = db.get(model, obj_id)
    if obj is None or getattr(obj, "project_id", None) != project_id:
        raise AppError(404, f"{label}_not_found", f"{label.replace('_', ' ').capitalize()} not found")
    return obj


def check_related(db: Session, project_id: int, collection_id: int | None, endpoint_id: int | None = None) -> None:
    from app.models import ApiEndpoint

    if collection_id is not None:
        get_in_project(db, Collection, collection_id, project_id, "collection")
    if endpoint_id is not None:
        get_in_project(db, ApiEndpoint, endpoint_id, project_id, "endpoint")


def latest_results(db: Session, case_ids: list[int]) -> dict[int, tuple[str, float | None]]:
    if not case_ids:
        return {}
    newest = (
        select(func.max(TestResult.id)).where(TestResult.test_case_id.in_(case_ids)).group_by(TestResult.test_case_id)
    )
    rows = db.execute(
        select(TestResult.test_case_id, TestResult.status, TestResult.response_time_ms).where(TestResult.id.in_(newest))
    ).all()
    return {cid: (status, ms) for cid, status, ms in rows}


def test_case_out(tc: TestCase, last: tuple[str, float | None] | None = None) -> TestCaseOut:
    data = TestCaseOut.model_validate(
        {
            **{c.name: getattr(tc, c.name) for c in TestCase.__table__.columns},
            "auth_config": mask_values(tc.auth_config),
        }
    )
    if last:
        data.last_status, data.last_response_time_ms = last
    return data


def run_outs(db: Session, runs: list[Run]) -> list[RunOut]:
    """Serialise runs with progress/collection/project names using batched queries."""
    from app.models import Project

    if not runs:
        return []
    ids = [r.id for r in runs]
    progress = dict(
        db.execute(select(TestResult.run_id, func.count()).where(TestResult.run_id.in_(ids)).group_by(TestResult.run_id)).all()
    )
    collection_ids = {r.collection_id for r in runs if r.collection_id}
    project_ids = {r.project_id for r in runs}
    collections = (
        dict(db.execute(select(Collection.id, Collection.name).where(Collection.id.in_(collection_ids))).all())
        if collection_ids
        else {}
    )
    projects = dict(db.execute(select(Project.id, Project.name).where(Project.id.in_(project_ids))).all())
    out = []
    for r in runs:
        duration = None
        if r.started_at and r.finished_at:
            duration = round((r.finished_at - r.started_at).total_seconds() * 1000, 1)
        out.append(
            RunOut(
                id=r.id,
                project_id=r.project_id,
                project_name=projects.get(r.project_id),
                collection_id=r.collection_id,
                collection_name=collections.get(r.collection_id),
                schedule_id=r.schedule_id,
                trigger=r.trigger,
                label=r.label,
                status=r.status,
                concurrency=r.concurrency,
                total=r.total,
                passed=r.passed,
                failed=r.failed,
                errored=r.errored,
                progress=progress.get(r.id, 0),
                error_message=r.error_message,
                baseline_run_id=r.baseline_run_id,
                regression_summary=r.regression_summary,
                created_at=r.created_at,
                started_at=r.started_at,
                finished_at=r.finished_at,
                duration_ms=duration,
            )
        )
    return out
