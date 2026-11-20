"""Regression detection: compare a run with a baseline and with historical timings.

Two independent signals are produced for every test case:

1. **Functional regression** — the test passed in the baseline run and now fails/errors
   ("new failure"). This is a hard, deterministic signal.
2. **Performance regression** — the response time is clearly above what this test
   normally takes. Timings are noisy, so we only flag a test when the current time
   exceeds ALL of:
       * ``median * slowdown_ratio``                      (relative change)
       * ``median + 3 * 1.4826 * MAD``                    (outside normal spread)
       * ``median + min_delta_ms``                        (absolute change that matters)
   and only when at least ``min_samples`` historical passing samples exist. Otherwise
   the state is "insufficient_data" — we never guess.

MAD = median absolute deviation, a robust spread estimate that a single outlier cannot
distort (unlike the standard deviation). See docs/adr/ADR-003-robust-performance-regression.md.
"""

import statistics
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import Run, TestResult

MAD_SCALE = 1.4826  # makes MAD comparable to a standard deviation for normal data


def default_baseline(db: Session, run: Run) -> Run | None:
    """Most recent earlier *completed* run of the same project and collection."""
    stmt = select(Run).where(Run.project_id == run.project_id, Run.id < run.id, Run.status == "completed")
    stmt = stmt.where(Run.collection_id.is_(None) if run.collection_id is None else Run.collection_id == run.collection_id)
    return db.scalar(stmt.order_by(Run.id.desc()).limit(1))


def performance_check(current_ms: float, history: list[float], settings: Settings) -> dict[str, Any]:
    if len(history) < settings.regression_min_samples:
        return {"state": "insufficient_data", "samples": len(history)}
    median = statistics.median(history)
    mad = statistics.median(abs(x - median) for x in history)
    threshold = max(
        median * settings.regression_slowdown_ratio,
        median + 3 * MAD_SCALE * mad,
        median + settings.regression_min_delta_ms,
    )
    regressed = current_ms > threshold
    return {
        "state": "regressed" if regressed else "normal",
        "samples": len(history),
        "baseline_median_ms": round(median, 2),
        "mad_ms": round(mad, 2),
        "threshold_ms": round(threshold, 2),
        "current_ms": round(current_ms, 2),
        "change_pct": round((current_ms - median) / median * 100, 1) if median else None,
    }


def _history(db: Session, run: Run, case_ids: list[int], settings: Settings) -> dict[int, list[float]]:
    if not case_ids:
        return {}
    recent_run_ids = db.scalars(
        select(Run.id)
        .where(Run.project_id == run.project_id, Run.id < run.id, Run.status == "completed")
        .order_by(Run.id.desc())
        .limit(30)
    ).all()
    if not recent_run_ids:
        return {}
    rows = db.execute(
        select(TestResult.test_case_id, TestResult.response_time_ms)
        .where(
            TestResult.run_id.in_(recent_run_ids),
            TestResult.test_case_id.in_(case_ids),
            TestResult.status == "passed",
            TestResult.response_time_ms.is_not(None),
        )
        .order_by(TestResult.run_id.desc())
    ).all()
    history: dict[int, list[float]] = {}
    for case_id, ms in rows:
        bucket = history.setdefault(case_id, [])
        if len(bucket) < settings.regression_history_window:
            bucket.append(ms)
    return history


def _entry(result: TestResult, change: str, base: TestResult | None, perf: dict | None) -> dict[str, Any]:
    return {
        "test_case_id": result.test_case_id,
        "test_name": result.test_name,
        "method": result.method,
        "url": result.url,
        "change": change,
        "status": result.status,
        "baseline_status": base.status if base else None,
        "status_code": result.status_code,
        "baseline_status_code": base.status_code if base else None,
        "response_time_ms": result.response_time_ms,
        "error": result.error,
        "performance": perf,
    }


def compute_regression(
    db: Session, run: Run, baseline: Run | None = None, settings: Settings | None = None
) -> dict[str, Any]:
    settings = settings or get_settings()
    baseline = baseline or default_baseline(db, run)

    current = db.scalars(select(TestResult).where(TestResult.run_id == run.id)).all()
    base_by_case: dict[int, TestResult] = {}
    if baseline:
        base_rows = db.scalars(select(TestResult).where(TestResult.run_id == baseline.id)).all()
        base_by_case = {r.test_case_id: r for r in base_rows if r.test_case_id is not None}

    history = _history(db, run, [r.test_case_id for r in current if r.test_case_id], settings)

    buckets: dict[str, list] = {k: [] for k in ("new_failures", "fixed", "still_failing", "new_tests", "performance_regressions")}
    still_passing = 0
    for result in current:
        base = base_by_case.get(result.test_case_id) if result.test_case_id else None
        perf = None
        if result.status == "passed" and result.response_time_ms is not None and result.test_case_id:
            perf = performance_check(result.response_time_ms, history.get(result.test_case_id, []), settings)

        if baseline is None or base is None:
            change = "new_test"
        elif base.status == "passed" and result.status != "passed":
            change = "new_failure"
        elif base.status != "passed" and result.status == "passed":
            change = "fixed"
        elif result.status != "passed":
            change = "still_failing"
        else:
            change = "still_passing"

        entry = _entry(result, change, base, perf)
        if change == "new_failure":
            buckets["new_failures"].append(entry)
        elif change == "fixed":
            buckets["fixed"].append(entry)
        elif change == "still_failing":
            buckets["still_failing"].append(entry)
        elif change == "new_test" and baseline is not None:
            buckets["new_tests"].append(entry)
        else:
            still_passing += 1
        if perf and perf["state"] == "regressed":
            buckets["performance_regressions"].append(entry)

    if baseline is None:
        verdict = "no_baseline"
    elif buckets["new_failures"]:
        verdict = "fail"
    elif buckets["performance_regressions"]:
        verdict = "warn"
    else:
        verdict = "pass"

    return {
        "run_id": run.id,
        "baseline_run_id": baseline.id if baseline else None,
        "verdict": verdict,
        "summary": {
            "new_failures": len(buckets["new_failures"]),
            "fixed": len(buckets["fixed"]),
            "still_failing": len(buckets["still_failing"]),
            "still_passing": still_passing,
            "new_tests": len(buckets["new_tests"]),
            "performance_regressions": len(buckets["performance_regressions"]),
        },
        **buckets,
        "thresholds": {
            "history_window": settings.regression_history_window,
            "min_samples": settings.regression_min_samples,
            "slowdown_ratio": settings.regression_slowdown_ratio,
            "min_delta_ms": settings.regression_min_delta_ms,
        },
    }


def store_summary(db: Session, run: Run, report: dict[str, Any]) -> None:
    run.baseline_run_id = report["baseline_run_id"]
    run.regression_summary = {"verdict": report["verdict"], **report["summary"]}
    db.commit()
