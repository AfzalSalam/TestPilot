"""Run lifecycle: creation, safe claiming, concurrent execution and finalisation.

Delivery semantics (important, see docs/adr/ADR-001-idempotent-at-least-once-runs.md):
Celery with ``acks_late`` gives AT-LEAST-ONCE delivery: a task may run twice (worker
crash, broker redelivery). We make execution *idempotent* instead of pretending to have
exactly-once delivery:

* ``claim_run`` performs an atomic compare-and-set (queued -> running). A duplicate
  delivery finds the run already claimed and exits.
* A run stuck in ``running`` whose heartbeat is older than the lease is considered
  orphaned and may be re-claimed by another worker.
* ``UNIQUE(run_id, test_case_id)`` on results + "skip cases that already have a
  result" means a resumed run never double-records a test.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

import httpx
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.errors import AppError
from app.models import Collection, Project, Run, TestCase, TestResult
from app.services.engine import TestCaseSpec, execute_test_case
from app.services.regression import compute_regression, store_summary
from app.services.ssrf import Resolver
from app.utils import utcnow

logger = logging.getLogger("testpilot.runner")


def spec_from_model(tc: TestCase) -> TestCaseSpec:
    return TestCaseSpec(
        id=tc.id,
        name=tc.name,
        method=tc.method,
        path=tc.path,
        headers=dict(tc.headers or {}),
        query_params=dict(tc.query_params or {}),
        body_type=tc.body_type,
        body=tc.body,
        auth_type=tc.auth_type,
        auth_config=dict(tc.auth_config or {}),
        expected_status=tc.expected_status,
        assertions=list(tc.assertions or []),
        timeout_s=tc.timeout_s,
        follow_redirects=tc.follow_redirects,
    )


# --------------------------------------------------------------------------- creation
def create_run(
    db: Session,
    project: Project,
    *,
    collection_id: int | None = None,
    test_case_ids: list[int] | None = None,
    concurrency: int | None = None,
    trigger: str = "manual",
    triggered_by: int | None = None,
    label: str = "",
    schedule_id: int | None = None,
) -> Run:
    settings = get_settings()
    stmt = select(TestCase.id).where(TestCase.project_id == project.id, TestCase.enabled.is_(True))
    if collection_id is not None:
        if db.scalar(select(Collection.id).where(Collection.id == collection_id, Collection.project_id == project.id)) is None:
            raise AppError(404, "collection_not_found", "Collection not found in this project")
        stmt = stmt.where(TestCase.collection_id == collection_id)
    if test_case_ids:
        stmt = stmt.where(TestCase.id.in_(test_case_ids))
    ids = list(db.scalars(stmt.order_by(TestCase.id)).all())

    if not ids:
        raise AppError(422, "no_test_cases", "There are no enabled test cases to run for this selection")
    if len(ids) > settings.max_tests_per_run:
        raise AppError(422, "too_many_tests", f"A run may contain at most {settings.max_tests_per_run} test cases")

    workers = max(1, min(concurrency or settings.default_concurrency, settings.max_concurrency))
    run = Run(
        project_id=project.id,
        collection_id=collection_id,
        schedule_id=schedule_id,
        triggered_by=triggered_by,
        trigger=trigger,
        label=label[:200],
        status="queued",
        concurrency=workers,
        test_case_ids=ids,
        total=len(ids),
    )
    db.add(run)
    db.commit()
    return run


# --------------------------------------------------------------------------- execution
def claim_run(db: Session, run_id: int) -> bool:
    """Atomically move a run to 'running'. Returns False if someone else owns it."""
    settings = get_settings()
    now = utcnow()
    lease_cutoff = now - timedelta(seconds=settings.run_lease_seconds)
    result = db.execute(
        update(Run)
        .where(
            Run.id == run_id,
            or_(Run.status == "queued", (Run.status == "running") & (Run.heartbeat_at < lease_cutoff)),
        )
        .values(
            status="running",
            started_at=func.coalesce(Run.started_at, now),
            heartbeat_at=now,
            attempts=Run.attempts + 1,
        )
    )
    db.commit()
    return result.rowcount == 1


def execute_run(
    run_id: int,
    *,
    session_factory=SessionLocal,
    resolver: Resolver | None = None,
    transport: httpx.BaseTransport | None = None,
) -> None:
    settings = get_settings()
    with session_factory() as db:
        if not claim_run(db, run_id):
            logger.info("run already claimed or finished; skipping", extra={"run_id": run_id})
            return
        try:
            _execute_claimed(db, run_id, settings, resolver, transport)
        except OperationalError:
            # Transient database trouble: hand the run back so Celery's retry can re-claim it.
            db.rollback()
            logger.warning("database error during run; releasing for retry", extra={"run_id": run_id})
            db.execute(update(Run).where(Run.id == run_id, Run.status == "running").values(status="queued"))
            db.commit()
            raise
        except Exception as exc:  # unexpected bug: record it on the run so users can see it
            db.rollback()
            logger.exception("run failed", extra={"run_id": run_id})
            run = db.get(Run, run_id)
            if run and run.status == "running":
                run.status = "failed"
                run.error_message = f"{type(exc).__name__}: {exc}"[:1000]
                run.finished_at = utcnow()
                db.commit()
            raise


def _execute_claimed(db: Session, run_id: int, settings, resolver, transport) -> None:
    run = db.get(Run, run_id)
    db.refresh(run)
    project = db.get(Project, run.project_id)

    done_ids = set(db.scalars(select(TestResult.test_case_id).where(TestResult.run_id == run.id)).all())
    cases = db.scalars(select(TestCase).where(TestCase.id.in_(run.test_case_ids))).all()
    specs = [spec_from_model(tc) for tc in cases if tc.id not in done_ids]

    variables = dict(project.variables or {})
    cancelled = False
    executor = ThreadPoolExecutor(max_workers=run.concurrency, thread_name_prefix=f"run-{run.id}")
    try:
        futures = [
            executor.submit(
                execute_test_case,
                spec,
                base_url=project.base_url,
                variables=variables,
                settings=settings,
                default_timeout_s=project.default_timeout_s,
                resolver=resolver,
                transport=transport,
            )
            for spec in specs
        ]
        for future in as_completed(futures):
            payload = future.result()  # engine never raises; it returns an error result
            db.add(TestResult(run_id=run.id, **payload))
            try:
                db.flush()
            except IntegrityError:  # duplicate delivery already stored this result
                db.rollback()
            db.execute(update(Run).where(Run.id == run.id).values(heartbeat_at=utcnow()))
            db.commit()
            current = db.scalar(select(Run.status).where(Run.id == run.id))
            if current == "cancelled":
                cancelled = True
                executor.shutdown(wait=False, cancel_futures=True)
                break
    finally:
        executor.shutdown(wait=True, cancel_futures=True)

    counts = dict(
        db.execute(
            select(TestResult.status, func.count()).where(TestResult.run_id == run.id).group_by(TestResult.status)
        ).all()
    )
    db.refresh(run)
    run.passed = counts.get("passed", 0)
    run.failed = counts.get("failed", 0)
    run.errored = counts.get("error", 0)
    run.finished_at = utcnow()
    if not cancelled and run.status == "running":
        run.status = "completed"
    db.commit()

    if run.status == "completed":
        try:  # regression analysis must never turn a finished run into a failed one
            store_summary(db, run, compute_regression(db, run, settings=settings))
        except Exception:  # pragma: no cover - defensive
            db.rollback()
            logger.exception("regression analysis failed", extra={"run_id": run.id})


def recover_interrupted_runs(db: Session) -> int:
    """Thread/inline mode only: after a restart nothing is still executing, so mark leftovers failed."""
    runs = db.scalars(select(Run).where(Run.status.in_(("queued", "running")))).all()
    for run in runs:
        run.status = "failed"
        run.error_message = "Interrupted by a server restart"
        run.finished_at = utcnow()
    db.commit()
    return len(runs)
