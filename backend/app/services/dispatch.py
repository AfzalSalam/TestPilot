"""Hands a created run to whichever execution backend is configured."""

import logging
import threading

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Run
from app.services.runner import execute_run
from app.utils import utcnow

logger = logging.getLogger("testpilot.dispatch")


def dispatch_run(run_id: int) -> str | None:
    """Queue a run. Returns a task id for Celery mode, otherwise None."""
    mode = get_settings().execution_mode
    if mode == "celery":
        from app.worker.tasks import execute_run_task  # imported lazily: Celery is optional in dev

        return execute_run_task.delay(run_id).id
    if mode == "thread":
        threading.Thread(target=_safe_execute, args=(run_id,), daemon=True, name=f"run-{run_id}").start()
        return None
    _safe_execute(run_id)  # inline
    return None


def _safe_execute(run_id: int) -> None:
    try:
        execute_run(run_id)
    except Exception:  # already recorded on the run row by execute_run
        logger.exception("background run crashed", extra={"run_id": run_id})


def dispatch_run_safe(db: Session, run: Run) -> bool:
    """Dispatch and, if the queue is unreachable, record that on the run instead of losing it."""
    try:
        task_id = dispatch_run(run.id)
        if task_id:
            run.task_id = task_id
            db.commit()
        db.refresh(run)
        return True
    except Exception as exc:
        logger.exception("could not enqueue run", extra={"run_id": run.id})
        run.status = "failed"
        run.error_message = f"Could not enqueue run: {type(exc).__name__}"
        run.finished_at = utcnow()
        db.commit()
        return False
