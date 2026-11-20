"""Regression detection and the run-claiming / idempotency guarantees."""

from datetime import timedelta

from sqlalchemy import select

from app.config import Settings, get_settings
from app.database import SessionLocal
from app.models import Run, TestCase, TestResult
from app.services.regression import performance_check
from app.services.runner import claim_run, execute_run
from app.utils import utcnow
from tests.conftest import add_case, start_run

API = "/api/v1"
S = Settings()


# ---------------------------------------------------------------- statistics (pure functions)
def test_perf_needs_enough_history():
    assert performance_check(900, [100, 100], S)["state"] == "insufficient_data"


def test_normal_jitter_is_not_a_regression():
    history = [100, 120, 90, 110, 105]
    assert performance_check(140, history, S)["state"] == "normal"  # +30%: inside noise and below 1.5x


def test_clear_slowdown_is_flagged():
    check = performance_check(400, [100, 120, 90, 110, 105], S)
    assert check["state"] == "regressed" and check["change_pct"] > 200


def test_small_absolute_change_on_fast_endpoint_is_ignored():
    """5 ms -> 12 ms is +140% but only 7 ms: not worth alerting on (min_delta_ms)."""
    assert performance_check(12, [5, 5, 6, 5, 5], S)["state"] == "normal"


def test_one_outlier_in_history_does_not_hide_a_regression():
    """Median/MAD are robust: a single 2 s outlier in history must not inflate the threshold."""
    check = performance_check(500, [100, 100, 105, 95, 2000], S)
    assert check["state"] == "regressed"


# ---------------------------------------------------------------- end-to-end regression
def test_new_failure_fixed_and_verdicts(client, auth, project, target):
    pid = project["id"]
    add_case(client, auth, project, name="widget")
    add_case(client, auth, project, name="text", path="/text")

    first = start_run(client, auth, project)
    assert first["regression_summary"]["verdict"] == "no_baseline"

    target.state["broken"] = True
    second = start_run(client, auth, project)
    assert second["baseline_run_id"] == first["id"]
    assert second["regression_summary"]["verdict"] == "fail" and second["regression_summary"]["new_failures"] == 1

    report = client.get(f"{API}/projects/{pid}/runs/{second['id']}/regression", headers=auth).json()
    assert [e["test_name"] for e in report["new_failures"]] == ["widget"]
    assert report["new_failures"][0]["baseline_status"] == "passed" and report["new_failures"][0]["status"] == "failed"

    target.state["broken"] = False
    third = start_run(client, auth, project)
    assert third["regression_summary"]["verdict"] == "pass" and third["regression_summary"]["fixed"] == 1

    # explicit baseline: compare run 3 against run 1
    custom = client.get(f"{API}/projects/{pid}/runs/{third['id']}/regression", headers=auth, params={"baseline_run_id": first["id"]}).json()
    assert custom["baseline_run_id"] == first["id"] and custom["verdict"] == "pass"
    assert client.get(f"{API}/projects/{pid}/runs/{third['id']}/regression", headers=auth, params={"baseline_run_id": third["id"]}).status_code == 422


def test_still_failing_and_new_tests(client, auth, project):
    pid = project["id"]
    add_case(client, auth, project, name="always bad", path="/status/500")
    start_run(client, auth, project)
    add_case(client, auth, project, name="added later", path="/text")
    second = start_run(client, auth, project)
    report = client.get(f"{API}/projects/{pid}/runs/{second['id']}/regression", headers=auth).json()
    assert [e["test_name"] for e in report["still_failing"]] == ["always bad"]
    assert [e["test_name"] for e in report["new_tests"]] == ["added later"]
    assert report["verdict"] == "pass"  # nothing NEWLY broke


def test_performance_regression_detected_through_the_api(client, auth, project, target):
    pid = project["id"]
    add_case(client, auth, project, name="slowish", path="/slow")
    target.state["delay_ms"] = 20
    for _ in range(4):  # build history
        start_run(client, auth, project)
    target.state["delay_ms"] = 600
    regressed = start_run(client, auth, project)
    assert regressed["regression_summary"]["verdict"] == "warn"
    report = client.get(f"{API}/projects/{pid}/runs/{regressed['id']}/regression", headers=auth).json()
    perf = report["performance_regressions"][0]["performance"]
    assert perf["state"] == "regressed" and perf["current_ms"] > perf["threshold_ms"] > perf["baseline_median_ms"]


def test_baselines_are_per_collection(client, auth, project):
    pid = project["id"]
    col = client.post(f"{API}/projects/{pid}/collections", headers=auth, json={"name": "Smoke"}).json()
    add_case(client, auth, project, name="in col", collection_id=col["id"])
    all_run = start_run(client, auth, project)
    col_run = start_run(client, auth, project, collection_id=col["id"])
    assert col_run["baseline_run_id"] is None and col_run["regression_summary"]["verdict"] == "no_baseline"
    assert start_run(client, auth, project)["baseline_run_id"] == all_run["id"]


# ---------------------------------------------------------------- claiming & idempotency
def _queued_run(client, auth, project, monkeypatch, cases=2):
    """Create a run but do not execute it (simulate 'sitting in the queue')."""
    import app.routers.runs as runs_router

    for i in range(cases):
        add_case(client, auth, project, name=f"t{i}")
    monkeypatch.setattr("app.services.dispatch.dispatch_run", lambda run_id: None)
    monkeypatch.setattr(runs_router, "dispatch_run_safe", lambda db, run: True)
    return start_run(client, auth, project)


def test_only_one_worker_can_claim_a_run(client, auth, project, monkeypatch):
    run = _queued_run(client, auth, project, monkeypatch)
    assert run["status"] == "queued"
    with SessionLocal() as db1, SessionLocal() as db2:
        assert claim_run(db1, run["id"]) is True
        assert claim_run(db2, run["id"]) is False  # duplicate delivery loses the race


def test_duplicate_delivery_does_not_duplicate_results(client, auth, project, monkeypatch):
    run = _queued_run(client, auth, project, monkeypatch)
    execute_run(run["id"])
    execute_run(run["id"])  # same message delivered twice
    with SessionLocal() as db:
        results = db.scalars(select(TestResult).where(TestResult.run_id == run["id"])).all()
        stored = db.get(Run, run["id"])
        assert len(results) == 2 and stored.status == "completed" and stored.attempts == 1


def test_orphaned_run_is_reclaimed_and_resumed_without_rerunning_finished_tests(client, auth, project, monkeypatch):
    run = _queued_run(client, auth, project, monkeypatch, cases=3)
    with SessionLocal() as db:
        first_case = db.scalars(select(TestCase).order_by(TestCase.id)).first()
        # Simulate a worker that crashed after finishing one test, long ago.
        db.add(TestResult(run_id=run["id"], test_case_id=first_case.id, test_name="t0", method="GET", url="x", status="passed", status_code=200, response_time_ms=1))
        stored = db.get(Run, run["id"])
        stored.status, stored.heartbeat_at, stored.started_at = "running", utcnow() - timedelta(seconds=get_settings().run_lease_seconds + 30), utcnow() - timedelta(minutes=5)
        db.commit()
    with SessionLocal() as db:
        assert claim_run(db, run["id"]) is True  # stale lease -> a new worker may take over
        db.execute(Run.__table__.update().where(Run.id == run["id"]).values(status="queued"))
        db.commit()
    execute_run(run["id"])
    with SessionLocal() as db:
        results = db.scalars(select(TestResult).where(TestResult.run_id == run["id"])).all()
        stored = db.get(Run, run["id"])
        assert len(results) == 3 and stored.status == "completed" and stored.total == 3
        assert next(r for r in results if r.test_case_id == first_case.id).url == "x"  # not re-executed


def test_fresh_running_run_cannot_be_stolen(client, auth, project, monkeypatch):
    run = _queued_run(client, auth, project, monkeypatch)
    with SessionLocal() as db:
        assert claim_run(db, run["id"]) is True
    with SessionLocal() as db:
        assert claim_run(db, run["id"]) is False  # heartbeat is fresh -> still owned


def test_cancelled_run_is_never_executed(client, auth, project, monkeypatch):
    run = _queued_run(client, auth, project, monkeypatch)
    assert client.post(f"{API}/projects/{project['id']}/runs/{run['id']}/cancel", headers=auth).json()["status"] == "cancelled"
    execute_run(run["id"])
    with SessionLocal() as db:
        assert db.scalar(select(TestResult).where(TestResult.run_id == run["id"])) is None
        assert db.get(Run, run["id"]).status == "cancelled"


def test_queue_failure_marks_run_failed_and_returns_503(client, auth, project, monkeypatch):
    add_case(client, auth, project)

    def boom(run_id):
        raise ConnectionError("redis down")

    monkeypatch.setattr("app.services.dispatch.dispatch_run", boom)
    res = client.post(f"{API}/projects/{project['id']}/runs", headers=auth, json={})
    assert res.status_code == 503 and res.json()["error"]["code"] == "queue_unavailable"
    runs = client.get(f"{API}/projects/{project['id']}/runs", headers=auth).json()["items"]
    assert runs[0]["status"] == "failed" and "enqueue" in runs[0]["error_message"]


def test_celery_app_is_configured_for_at_least_once_delivery():
    from app.worker.celery_app import celery_app

    assert celery_app.conf.task_acks_late is True and celery_app.conf.task_reject_on_worker_lost is True
    import app.worker.tasks  # noqa: F401

    assert "testpilot.execute_run" in celery_app.tasks and "testpilot.tick_schedules" in celery_app.tasks


def test_celery_dispatch_path_runs_the_same_code(client, auth, project, monkeypatch):
    """Eager mode executes the Celery task in-process: proves dispatch -> task -> runner wiring."""
    from app.worker.celery_app import celery_app

    add_case(client, auth, project)
    monkeypatch.setattr(get_settings(), "execution_mode", "celery")
    monkeypatch.setattr(celery_app.conf, "task_always_eager", True)
    run = start_run(client, auth, project)
    fresh = client.get(f"{API}/projects/{project['id']}/runs/{run['id']}", headers=auth).json()
    assert fresh["status"] == "completed" and fresh["passed"] == 1
    with SessionLocal() as db:
        assert db.get(Run, run["id"]).task_id  # the Celery task id was recorded
