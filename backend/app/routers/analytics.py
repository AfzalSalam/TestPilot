"""Execution history and analytics (project-level and cross-project dashboard)."""

from collections import defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import ProjectContext, get_current_user, viewer_access
from app.models import ApiEndpoint, Collection, Project, ProjectMember, Run, Schedule, TestCase, TestResult, User
from app.routers.common import run_outs
from app.utils import utcnow

router = APIRouter(tags=["Analytics"])


def _pct(passed: int, total: int) -> float | None:
    return round(passed / total * 100, 1) if total else None


@router.get("/projects/{project_id}/analytics", summary="Trends, slowest and flakiest tests for a project")
def project_analytics(
    window: int = Query(default=30, ge=5, le=100, description="Number of most recent completed runs to analyse"),
    ctx: ProjectContext = Depends(viewer_access),
    db: Session = Depends(get_db),
):
    pid = ctx.project.id

    def count(model) -> int:
        return db.scalar(select(func.count()).select_from(model).where(model.project_id == pid)) or 0

    runs = list(
        reversed(
            db.scalars(select(Run).where(Run.project_id == pid, Run.status == "completed").order_by(Run.id.desc()).limit(window)).all()
        )
    )
    run_ids = [r.id for r in runs]
    avg_by_run: dict[int, float] = {}
    slowest, flaky = [], []
    avg_ms = None
    if run_ids:
        avg_by_run = {
            rid: round(avg, 1)
            for rid, avg in db.execute(
                select(TestResult.run_id, func.avg(TestResult.response_time_ms))
                .where(TestResult.run_id.in_(run_ids), TestResult.response_time_ms.is_not(None))
                .group_by(TestResult.run_id)
            ).all()
        }
        stats = db.execute(
            select(
                TestResult.test_case_id,
                func.max(TestResult.test_name),
                func.avg(TestResult.response_time_ms),
                func.max(TestResult.response_time_ms),
                func.count(),
            )
            .where(TestResult.run_id.in_(run_ids), TestResult.response_time_ms.is_not(None), TestResult.test_case_id.is_not(None))
            .group_by(TestResult.test_case_id)
            .order_by(func.avg(TestResult.response_time_ms).desc())
            .limit(5)
        ).all()
        slowest = [
            {"test_case_id": cid, "name": name, "avg_ms": round(avg, 1), "max_ms": round(mx, 1), "samples": n}
            for cid, name, avg, mx, n in stats
        ]
        avg_ms = db.scalar(
            select(func.avg(TestResult.response_time_ms)).where(TestResult.run_id.in_(run_ids), TestResult.response_time_ms.is_not(None))
        )

        # Flakiness = how often a test flips between passed and not-passed from one run to the next.
        history: dict[int, list[tuple[str, str]]] = defaultdict(list)
        for cid, name, status in db.execute(
            select(TestResult.test_case_id, TestResult.test_name, TestResult.status)
            .where(TestResult.run_id.in_(run_ids), TestResult.test_case_id.is_not(None))
            .order_by(TestResult.run_id)
        ).all():
            history[cid].append((name, status))
        for cid, seq in history.items():
            flips = sum(1 for a, b in zip(seq, seq[1:]) if (a[1] == "passed") != (b[1] == "passed"))
            if flips:
                passed = sum(1 for _, s in seq if s == "passed")
                flaky.append({"test_case_id": cid, "name": seq[-1][0], "flips": flips, "runs": len(seq), "pass_rate": _pct(passed, len(seq))})
        flaky = sorted(flaky, key=lambda f: (-f["flips"], f["name"]))[:5]

    trend = [
        {
            "run_id": r.id,
            "created_at": r.created_at,
            "total": r.total,
            "passed": r.passed,
            "failed": r.failed,
            "errored": r.errored,
            "pass_rate": _pct(r.passed, r.total),
            "avg_response_ms": avg_by_run.get(r.id),
            "verdict": (r.regression_summary or {}).get("verdict"),
            "trigger": r.trigger,
        }
        for r in runs
    ]
    total_exec = sum(r.total for r in runs)
    return {
        "totals": {
            "test_cases": count(TestCase),
            "endpoints": count(ApiEndpoint),
            "collections": count(Collection),
            "schedules": count(Schedule),
            "runs": count(Run),
        },
        "overall": {
            "window_runs": len(runs),
            "executions": total_exec,
            "pass_rate": _pct(sum(r.passed for r in runs), total_exec),
            "avg_response_ms": round(avg_ms, 1) if avg_ms is not None else None,
            "regressions_detected": sum(1 for r in runs if (r.regression_summary or {}).get("verdict") == "fail"),
        },
        "trend": trend,
        "slowest": slowest,
        "flaky": flaky,
    }


@router.get("/dashboard", summary="Cross-project overview for the signed-in user")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project_ids = list(db.scalars(select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)).all())
    now = utcnow()
    since = now - timedelta(days=14)
    empty = {"projects": 0, "test_cases": 0, "active_runs": 0, "runs_14d": 0, "pass_rate_14d": None,
             "avg_response_ms_14d": None, "recent_runs": [], "alerts": [], "daily": []}  # fmt: skip
    if not project_ids:
        return empty

    recent_runs = db.scalars(
        select(Run).where(Run.project_id.in_(project_ids), Run.created_at >= since).order_by(Run.id.desc())
    ).all()
    completed = [r for r in recent_runs if r.status == "completed"]
    avg_ms = db.scalar(
        select(func.avg(TestResult.response_time_ms)).where(
            TestResult.run_id.in_([r.id for r in completed] or [0]), TestResult.response_time_ms.is_not(None)
        )
    )
    daily: dict[str, dict] = {}
    for offset in range(14):
        day = (now - timedelta(days=13 - offset)).date().isoformat()
        daily[day] = {"date": day, "runs": 0, "passed": 0, "failed": 0}
    for r in completed:
        bucket = daily.get(r.created_at.date().isoformat())
        if bucket:
            bucket["runs"] += 1
            bucket["passed"] += r.passed
            bucket["failed"] += r.failed + r.errored

    projects = {p.id: p.name for p in db.scalars(select(Project).where(Project.id.in_(project_ids))).all()}
    alerts = [
        {
            "run_id": r.id,
            "project_id": r.project_id,
            "project_name": projects.get(r.project_id),
            "verdict": r.regression_summary["verdict"],
            "new_failures": r.regression_summary.get("new_failures", 0),
            "performance_regressions": r.regression_summary.get("performance_regressions", 0),
            "created_at": r.created_at,
        }
        for r in completed
        if r.regression_summary and r.regression_summary.get("verdict") in ("fail", "warn")
    ][:6]
    total = sum(r.total for r in completed)
    return {
        "projects": len(project_ids),
        "test_cases": db.scalar(select(func.count()).select_from(TestCase).where(TestCase.project_id.in_(project_ids))) or 0,
        "active_runs": sum(1 for r in recent_runs if r.status in ("queued", "running")),
        "runs_14d": len(recent_runs),
        "pass_rate_14d": _pct(sum(r.passed for r in completed), total),
        "avg_response_ms_14d": round(avg_ms, 1) if avg_ms is not None else None,
        "recent_runs": [o.model_dump(mode="json") for o in run_outs(db, list(recent_runs[:8]))],
        "alerts": alerts,
        "daily": list(daily.values()),
    }
