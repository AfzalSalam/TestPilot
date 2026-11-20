"""Endpoints designed for CI systems such as GitHub Actions (authenticated with X-API-Key)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import get_api_key_project
from app.errors import AppError
from app.models import Project, Run
from app.ratelimit import check_rate
from app.schemas import CIRunIn, CIRunOut
from app.services.dispatch import dispatch_run_safe
from app.services.regression import compute_regression
from app.services.runner import create_run

router = APIRouter(prefix="/ci", tags=["CI integration"])


def conclusion_for(run: Run, regression: dict | None, fail_on_performance: bool) -> str:
    if run.status in ("queued", "running"):
        return "pending"
    if run.status != "completed" or run.failed or run.errored:
        return "failure"
    verdict = (regression or {}).get("verdict")
    if verdict == "fail" or (fail_on_performance and verdict == "warn"):
        return "failure"
    return "success"


def _out(db: Session, run: Run, fail_on_performance: bool) -> CIRunOut:
    regression = None
    if run.status == "completed":
        report = compute_regression(db, run, db.get(Run, run.baseline_run_id) if run.baseline_run_id else None)
        regression = {
            "verdict": report["verdict"],
            "baseline_run_id": report["baseline_run_id"],
            **report["summary"],
            "new_failures_detail": [
                {"test": e["test_name"], "status": e["status"], "error": e["error"]} for e in report["new_failures"]
            ],
            "performance_detail": [
                {"test": e["test_name"], **(e["performance"] or {})} for e in report["performance_regressions"]
            ],
        }
    return CIRunOut(
        id=run.id,
        status=run.status,
        finished=run.status not in ("queued", "running"),
        conclusion=conclusion_for(run, regression, fail_on_performance),
        total=run.total,
        passed=run.passed,
        failed=run.failed,
        errored=run.errored,
        regression=regression,
        error_message=run.error_message,
        url_path=f"/projects/{run.project_id}/runs/{run.id}",
    )


@router.post("/runs", response_model=CIRunOut, status_code=201, summary="Trigger a run from CI")
def trigger(body: CIRunIn, project: Project = Depends(get_api_key_project), db: Session = Depends(get_db)):
    check_rate("ci", str(project.id), get_settings().rate_limit_runs_per_minute)
    run = create_run(
        db, project,
        collection_id=body.collection_id,
        concurrency=body.concurrency,
        trigger="ci",
        label=body.label,
    )  # fmt: skip
    if not dispatch_run_safe(db, run):
        raise AppError(503, "queue_unavailable", "The job queue is unavailable; the run was not started")
    return _out(db, run, False)


@router.get("/runs/{run_id}", response_model=CIRunOut, summary="Poll a CI run: 'conclusion' is pending | success | failure")
def poll(
    run_id: int,
    fail_on_performance: bool = Query(default=False, description="Treat performance regressions as failures"),
    project: Project = Depends(get_api_key_project),
    db: Session = Depends(get_db),
):
    run = db.get(Run, run_id)
    if run is None or run.project_id != project.id:
        raise AppError(404, "run_not_found", "Run not found")
    return _out(db, run, fail_on_performance)
