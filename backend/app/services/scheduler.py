"""Cron-style scheduling.

A schedule row stores a 5-field cron expression and ``next_run_at``. A "tick" (Celery
beat every minute, or a background thread in thread mode) finds due schedules and
creates runs. Multiple ticks can race, so each schedule is *claimed* with an atomic
compare-and-set on ``next_run_at`` — only one ticker wins and creates the run.
"""

import logging
import threading
from datetime import datetime

from croniter import croniter
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.errors import AppError
from app.models import Project, Run, Schedule
from app.services.dispatch import dispatch_run_safe
from app.services.runner import create_run
from app.utils import utcnow

logger = logging.getLogger("testpilot.scheduler")


def validate_cron(expression: str) -> str:
    expression = " ".join(expression.split())
    if len(expression.split()) != 5 or not croniter.is_valid(expression):
        raise AppError(422, "invalid_cron", "Use a valid 5-field cron expression, e.g. '*/15 * * * *'")
    base = utcnow()
    it = croniter(expression, base)
    first, second = it.get_next(datetime), it.get_next(datetime)
    if (second - first).total_seconds() < get_settings().min_schedule_interval_minutes * 60:
        raise AppError(
            422, "schedule_too_frequent",
            f"Schedules may run at most every {get_settings().min_schedule_interval_minutes} minute(s)",
        )  # fmt: skip
    return expression


def next_after(expression: str, base: datetime) -> datetime:
    return croniter(expression, base).get_next(datetime)


def upcoming(expression: str, count: int = 5, base: datetime | None = None) -> list[datetime]:
    it = croniter(expression, base or utcnow())
    return [it.get_next(datetime) for _ in range(count)]


def run_due_schedules(db: Session, now: datetime | None = None) -> list[int]:
    now = now or utcnow()
    due = db.scalars(select(Schedule).where(Schedule.enabled.is_(True), Schedule.next_run_at <= now)).all()
    created: list[int] = []
    for schedule in due:
        claimed = db.execute(
            update(Schedule)
            .where(Schedule.id == schedule.id, Schedule.next_run_at == schedule.next_run_at)
            .values(next_run_at=next_after(schedule.cron, now), last_run_at=now)
        ).rowcount
        db.commit()
        if claimed != 1:
            continue  # another ticker already handled it

        active = db.scalar(
            select(func.count()).select_from(Run).where(Run.schedule_id == schedule.id, Run.status.in_(("queued", "running")))
        )
        if active:  # no-overlap policy: skip this tick while the previous run is still going
            logger.info("schedule skipped (previous run active)", extra={"run_id": None})
            continue
        project = db.get(Project, schedule.project_id)
        try:
            run = create_run(
                db, project,
                collection_id=schedule.collection_id,
                concurrency=schedule.concurrency,
                trigger="schedule",
                schedule_id=schedule.id,
                label=f"schedule:{schedule.name}",
            )  # fmt: skip
        except AppError as exc:
            logger.warning("scheduled run not created: %s", exc.message)
            continue
        created.append(run.id)
        dispatch_run_safe(db, run)
    return created


def scheduler_loop(stop: threading.Event, interval_s: float = 30.0) -> None:
    """Background ticker used in thread mode (Celery beat does this in production)."""
    while not stop.wait(interval_s):
        try:
            with SessionLocal() as db:
                run_due_schedules(db)
        except Exception:  # keep the loop alive
            logger.exception("scheduler tick failed")
