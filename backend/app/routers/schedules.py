from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import ProjectContext, editor_access, viewer_access
from app.errors import AppError
from app.models import Collection, Schedule
from app.routers.common import check_related, get_in_project, run_outs
from app.schemas import CronPreviewOut, RunOut, ScheduleIn, ScheduleOut, ScheduleUpdate
from app.services.dispatch import dispatch_run_safe
from app.services.runner import create_run
from app.services.scheduler import next_after, upcoming, validate_cron
from app.utils import utcnow

router = APIRouter(prefix="/projects/{project_id}/schedules", tags=["Schedules"])


def _out(db: Session, s: Schedule) -> ScheduleOut:
    collection = db.get(Collection, s.collection_id) if s.collection_id else None
    return ScheduleOut(
        id=s.id,
        project_id=s.project_id,
        collection_id=s.collection_id,
        collection_name=collection.name if collection else None,
        name=s.name,
        cron=s.cron,
        enabled=s.enabled,
        concurrency=s.concurrency,
        last_run_at=s.last_run_at,
        next_run_at=s.next_run_at if s.enabled else None,
        upcoming=upcoming(s.cron, 3) if s.enabled else [],
        created_at=s.created_at,
    )


@router.get("/preview", response_model=CronPreviewOut, summary="Validate a cron expression and show its next run times")
def preview(cron: str = Query(min_length=1, max_length=100), ctx: ProjectContext = Depends(viewer_access)):
    try:
        expression = validate_cron(cron)
    except AppError as exc:
        return CronPreviewOut(valid=False, message=exc.message)
    return CronPreviewOut(valid=True, upcoming=upcoming(expression, 5))


@router.get("", response_model=list[ScheduleOut], summary="List schedules")
def list_schedules(ctx: ProjectContext = Depends(viewer_access), db: Session = Depends(get_db)):
    rows = db.scalars(select(Schedule).where(Schedule.project_id == ctx.project.id).order_by(Schedule.id)).all()
    return [_out(db, s) for s in rows]


@router.post("", response_model=ScheduleOut, status_code=201, summary="Create a recurring schedule")
def create_schedule(body: ScheduleIn, ctx: ProjectContext = Depends(editor_access), db: Session = Depends(get_db)):
    cron = validate_cron(body.cron)
    check_related(db, ctx.project.id, body.collection_id)
    schedule = Schedule(
        project_id=ctx.project.id,
        name=body.name,
        cron=cron,
        collection_id=body.collection_id,
        concurrency=body.concurrency,
        enabled=body.enabled,
        next_run_at=next_after(cron, utcnow()),
        created_by=ctx.user.id,
    )
    db.add(schedule)
    db.commit()
    return _out(db, schedule)


@router.patch("/{schedule_id}", response_model=ScheduleOut, summary="Update, pause or resume a schedule")
def update_schedule(schedule_id: int, body: ScheduleUpdate, ctx: ProjectContext = Depends(editor_access), db: Session = Depends(get_db)):
    schedule = get_in_project(db, Schedule, schedule_id, ctx.project.id, "schedule")
    changes = body.model_dump(exclude_unset=True)
    if "cron" in changes and changes["cron"] is not None:
        changes["cron"] = validate_cron(changes["cron"])
    if "collection_id" in changes:
        check_related(db, ctx.project.id, changes["collection_id"])
    for key, value in changes.items():
        if value is None and key != "collection_id":
            continue
        setattr(schedule, key, value)
    if schedule.enabled and ("cron" in changes or changes.get("enabled")):
        schedule.next_run_at = next_after(schedule.cron, utcnow())  # never "catch up" missed ticks
    db.commit()
    return _out(db, schedule)


@router.post("/{schedule_id}/trigger", response_model=RunOut, status_code=201, summary="Run a schedule's tests right now")
def trigger_schedule(schedule_id: int, ctx: ProjectContext = Depends(editor_access), db: Session = Depends(get_db)):
    schedule = get_in_project(db, Schedule, schedule_id, ctx.project.id, "schedule")
    run = create_run(
        db, ctx.project,
        collection_id=schedule.collection_id,
        concurrency=schedule.concurrency,
        trigger="manual",
        triggered_by=ctx.user.id,
        schedule_id=schedule.id,
        label=f"schedule:{schedule.name} (manual)",
    )  # fmt: skip
    if not dispatch_run_safe(db, run):
        raise AppError(503, "queue_unavailable", "The job queue is unavailable; the run was not started")
    return run_outs(db, [run])[0]


@router.delete("/{schedule_id}", status_code=204, summary="Delete a schedule")
def delete_schedule(schedule_id: int, ctx: ProjectContext = Depends(editor_access), db: Session = Depends(get_db)):
    db.delete(get_in_project(db, Schedule, schedule_id, ctx.project.id, "schedule"))
    db.commit()
