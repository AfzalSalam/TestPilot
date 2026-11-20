from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import ProjectContext, editor_access, viewer_access
from app.errors import AppError
from app.models import Run, TestResult
from app.ratelimit import check_rate
from app.routers.common import get_in_project, run_outs
from app.schemas import Page, ResultOut, RunCreate, RunOut
from app.services.dispatch import dispatch_run_safe
from app.services.regression import compute_regression
from app.services.runner import create_run
from app.config import get_settings
from app.utils import utcnow

router = APIRouter(prefix="/projects/{project_id}/runs", tags=["Runs"])


def _get_run(db: Session, ctx: ProjectContext, run_id: int) -> Run:
    return get_in_project(db, Run, run_id, ctx.project.id, "run")


def _start(db: Session, ctx: ProjectContext, **kwargs) -> RunOut:
    settings = get_settings()
    check_rate("runs", str(ctx.user.id), settings.rate_limit_runs_per_minute)
    run = create_run(db, ctx.project, trigger="manual", triggered_by=ctx.user.id, **kwargs)
    if not dispatch_run_safe(db, run):
        raise AppError(503, "queue_unavailable", "The job queue is unavailable; the run was not started")
    return run_outs(db, [run])[0]


@router.post("", response_model=RunOut, status_code=201, summary="Start a test run")
def start_run(body: RunCreate, ctx: ProjectContext = Depends(editor_access), db: Session = Depends(get_db)):
    return _start(
        db, ctx,
        collection_id=body.collection_id,
        test_case_ids=body.test_case_ids,
        concurrency=body.concurrency,
        label=body.label,
    )  # fmt: skip


@router.get("", response_model=Page[RunOut], summary="List runs (newest first)")
def list_runs(
    status: str | None = Query(default=None, pattern="^(queued|running|completed|failed|cancelled)$"),
    collection_id: int | None = None,
    trigger: str | None = Query(default=None, pattern="^(manual|schedule|ci)$"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    ctx: ProjectContext = Depends(viewer_access),
    db: Session = Depends(get_db),
):
    stmt = select(Run).where(Run.project_id == ctx.project.id)
    if status:
        stmt = stmt.where(Run.status == status)
    if collection_id is not None:
        stmt = stmt.where(Run.collection_id == collection_id)
    if trigger:
        stmt = stmt.where(Run.trigger == trigger)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    runs = db.scalars(stmt.order_by(Run.id.desc()).limit(limit).offset(offset)).all()
    return Page(items=run_outs(db, list(runs)), total=total, limit=limit, offset=offset)


@router.get("/{run_id}", response_model=RunOut, summary="Get a run (poll this while it is queued/running)")
def get_run(run_id: int, ctx: ProjectContext = Depends(viewer_access), db: Session = Depends(get_db)):
    return run_outs(db, [_get_run(db, ctx, run_id)])[0]


@router.get("/{run_id}/results", response_model=Page[ResultOut], summary="Per-test results of a run")
def run_results(
    run_id: int,
    status: str | None = Query(default=None, pattern="^(passed|failed|error)$"),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    ctx: ProjectContext = Depends(viewer_access),
    db: Session = Depends(get_db),
):
    run = _get_run(db, ctx, run_id)
    stmt = select(TestResult).where(TestResult.run_id == run.id)
    if status:
        stmt = stmt.where(TestResult.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(TestResult.id).limit(limit).offset(offset)).all()
    return Page(items=[ResultOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/{run_id}/regression", summary="Regression report: new failures, fixes and slowdowns vs a baseline")
def run_regression(
    run_id: int,
    baseline_run_id: int | None = Query(default=None, description="Compare against a specific run instead of the previous one"),
    ctx: ProjectContext = Depends(viewer_access),
    db: Session = Depends(get_db),
):
    run = _get_run(db, ctx, run_id)
    baseline = None
    if baseline_run_id is not None:
        baseline = _get_run(db, ctx, baseline_run_id)
        if baseline.id == run.id:
            raise AppError(422, "invalid_baseline", "A run cannot be its own baseline")
        if baseline.status != "completed":
            raise AppError(422, "invalid_baseline", "The baseline run must be completed")
    return compute_regression(db, run, baseline)


@router.post("/{run_id}/cancel", response_model=RunOut, summary="Cancel a queued or running run")
def cancel_run(run_id: int, ctx: ProjectContext = Depends(editor_access), db: Session = Depends(get_db)):
    run = _get_run(db, ctx, run_id)
    if run.status not in ("queued", "running"):
        raise AppError(409, "run_not_active", f"Run is already {run.status}")
    run.status = "cancelled"
    run.finished_at = utcnow()
    db.commit()
    return run_outs(db, [run])[0]


@router.post("/{run_id}/rerun", response_model=RunOut, status_code=201, summary="Start a new run with the same selection")
def rerun(run_id: int, ctx: ProjectContext = Depends(editor_access), db: Session = Depends(get_db)):
    run = _get_run(db, ctx, run_id)
    return _start(
        db, ctx,
        collection_id=run.collection_id,
        test_case_ids=list(run.test_case_ids),
        concurrency=run.concurrency,
        label=f"rerun of #{run.id}",
    )  # fmt: skip


@router.delete("/{run_id}", status_code=204, summary="Delete a finished run and its results")
def delete_run(run_id: int, ctx: ProjectContext = Depends(editor_access), db: Session = Depends(get_db)):
    run = _get_run(db, ctx, run_id)
    if run.status in ("queued", "running"):
        raise AppError(409, "run_active", "Cancel the run before deleting it")
    db.delete(run)
    db.commit()
