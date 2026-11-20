from sqlalchemy.exc import OperationalError

from app.database import SessionLocal
from app.services.runner import execute_run
from app.services.scheduler import run_due_schedules
from app.worker.celery_app import celery_app


@celery_app.task(
    bind=True,
    name="testpilot.execute_run",
    autoretry_for=(OperationalError,),  # transient DB outages only; test failures are results, not errors
    retry_backoff=True,
    retry_backoff_max=60,
    retry_kwargs={"max_retries": 3},
)
def execute_run_task(self, run_id: int) -> None:
    execute_run(run_id)


@celery_app.task(name="testpilot.tick_schedules")
def tick_schedules() -> list[int]:
    with SessionLocal() as db:
        return run_due_schedules(db)
