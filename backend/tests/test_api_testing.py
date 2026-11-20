"""Endpoints, collections, test cases and run execution through the HTTP API."""

from tests.conftest import add_case, start_run

API = "/api/v1"


def test_endpoint_crud_and_uniqueness(client, auth, project):
    base = f"{API}/projects/{project['id']}/endpoints"
    created = client.post(base, headers=auth, json={"name": "List users", "method": "GET", "path": "/users"})
    assert created.status_code == 201
    assert client.post(base, headers=auth, json={"name": "dup", "method": "GET", "path": "/users"}).status_code == 409
    assert client.post(base, headers=auth, json={"name": "bad", "path": "users"}).status_code == 422
    eid = created.json()["id"]
    assert client.patch(f"{base}/{eid}", headers=auth, json={"description": "All users"}).json()["description"] == "All users"
    assert len(client.get(base, headers=auth).json()) == 1
    assert client.delete(f"{base}/{eid}", headers=auth).status_code == 204
    assert client.get(f"{base}/{eid}", headers=auth).status_code == 404


def test_collection_crud_and_test_case_counts(client, auth, project):
    pid = project["id"]
    col = client.post(f"{API}/projects/{pid}/collections", headers=auth, json={"name": "Smoke"}).json()
    assert client.post(f"{API}/projects/{pid}/collections", headers=auth, json={"name": "Smoke"}).status_code == 409
    add_case(client, auth, project, collection_id=col["id"])
    assert client.get(f"{API}/projects/{pid}/collections", headers=auth).json()[0]["test_case_count"] == 1
    assert client.delete(f"{API}/projects/{pid}/collections/{col['id']}", headers=auth).status_code == 204
    # tests survive, uncategorised
    assert client.get(f"{API}/projects/{pid}/test-cases", headers=auth).json()[0]["collection_id"] is None


def test_test_case_validation(client, auth, project):
    base = f"{API}/projects/{project['id']}/test-cases"
    bad = [
        {"name": "x", "path": "/ok", "method": "FETCH"},
        {"name": "x", "path": "/ok", "expected_status": 99},
        {"name": "x", "path": "/ok", "assertions": [{"type": "json_path", "operator": "eq", "value": 1}]},
        {"name": "x", "path": "/ok", "assertions": [{"type": "json_path", "path": "$.a", "operator": "bogus"}]},
        {"name": "x", "path": "/ok", "body_type": "form", "body": "not-an-object"},
        {"name": "x", "path": "/ok", "collection_id": 9999},
    ]
    assert [client.post(base, headers=auth, json=b).status_code for b in bad] == [422, 422, 422, 422, 422, 404]


def test_test_case_update_duplicate_search(client, auth, project):
    pid = project["id"]
    case = add_case(client, auth, project, name="Alpha widget")
    add_case(client, auth, project, name="Beta", path="/text")
    base = f"{API}/projects/{pid}/test-cases"
    upd = client.patch(f"{base}/{case['id']}", headers=auth, json={"expected_status": 404, "enabled": False,
                                                                    "assertions": [{"type": "body_contains", "value": "x"}]})
    assert upd.json()["expected_status"] == 404 and upd.json()["enabled"] is False and upd.json()["assertions"][0]["type"] == "body_contains"
    assert [c["name"] for c in client.get(base, headers=auth, params={"q": "beta"}).json()] == ["Beta"]
    assert len(client.get(base, headers=auth, params={"enabled": "true"}).json()) == 1
    copy = client.post(f"{base}/{case['id']}/duplicate", headers=auth)
    assert copy.status_code == 201 and copy.json()["name"] == "Alpha widget (copy)"


def test_try_it_endpoints_do_not_store_results(client, auth, project):
    pid = project["id"]
    unsaved = client.post(f"{API}/projects/{pid}/test-cases/execute", headers=auth,
                          json={"name": "t", "path": "/ok", "assertions": [{"type": "json_path", "path": "$.name", "value": "widget"}]})
    assert unsaved.status_code == 200 and unsaved.json()["status"] == "passed"
    case = add_case(client, auth, project)
    saved = client.post(f"{API}/projects/{pid}/test-cases/{case['id']}/execute", headers=auth)
    assert saved.json()["status"] == "passed" and saved.json()["response_time_ms"] > 0
    assert client.get(f"{API}/projects/{pid}/runs", headers=auth).json()["total"] == 0


def test_run_lifecycle_and_results(client, auth, project):
    pid = project["id"]
    add_case(client, auth, project, name="ok")
    add_case(client, auth, project, name="wrong status", path="/status/500", expected_status=200)
    add_case(client, auth, project, name="timeouts", path="/hang", timeout_s=0.5)

    run = start_run(client, auth, project, concurrency=3, label="abc123")
    assert run["status"] == "completed" and run["total"] == 3 and run["progress"] == 3
    assert (run["passed"], run["failed"], run["errored"]) == (1, 1, 1)
    assert run["label"] == "abc123" and run["trigger"] == "manual" and run["duration_ms"] > 0

    results = client.get(f"{API}/projects/{pid}/runs/{run['id']}/results", headers=auth).json()
    assert results["total"] == 3
    by_name = {r["test_name"]: r for r in results["items"]}
    assert by_name["ok"]["status"] == "passed" and by_name["wrong status"]["status"] == "failed"
    assert by_name["timeouts"]["error_type"] == "timeout"
    only_failed = client.get(f"{API}/projects/{pid}/runs/{run['id']}/results", headers=auth, params={"status": "failed"}).json()
    assert [r["test_name"] for r in only_failed["items"]] == ["wrong status"]

    listing = client.get(f"{API}/projects/{pid}/runs", headers=auth, params={"status": "completed"}).json()
    assert listing["total"] == 1
    assert client.get(f"{API}/projects/{pid}/runs/{run['id']}", headers=auth).json()["id"] == run["id"]


def test_run_selection_collection_ids_and_disabled(client, auth, project):
    pid = project["id"]
    col = client.post(f"{API}/projects/{pid}/collections", headers=auth, json={"name": "A"}).json()
    in_col = add_case(client, auth, project, name="in", collection_id=col["id"])
    add_case(client, auth, project, name="out")
    add_case(client, auth, project, name="disabled", collection_id=col["id"], enabled=False)

    assert start_run(client, auth, project, collection_id=col["id"])["total"] == 1
    assert start_run(client, auth, project)["total"] == 2  # disabled test skipped
    assert start_run(client, auth, project, test_case_ids=[in_col["id"]])["total"] == 1
    empty = client.post(f"{API}/projects/{pid}/runs", headers=auth, json={"collection_id": col["id"], "test_case_ids": [99999]})
    assert empty.status_code == 422 and empty.json()["error"]["code"] == "no_test_cases"
    assert client.post(f"{API}/projects/{pid}/runs", headers=auth, json={"collection_id": 12345}).status_code == 404


def test_results_survive_test_case_deletion(client, auth, project):
    case = add_case(client, auth, project)
    run = start_run(client, auth, project)
    client.delete(f"{API}/projects/{project['id']}/test-cases/{case['id']}", headers=auth)
    results = client.get(f"{API}/projects/{project['id']}/runs/{run['id']}/results", headers=auth).json()
    assert results["items"][0]["test_case_id"] is None and results["items"][0]["test_name"] == "Get widget"


def test_concurrent_execution_is_faster_than_serial(client, auth, project, target):
    """Six 300 ms requests with 6 workers should finish well under the 1.8 s serial time."""
    target.state["delay_ms"] = 300
    for i in range(6):
        add_case(client, auth, project, name=f"slow {i}", path="/slow")
    run = start_run(client, auth, project, concurrency=6)
    assert run["passed"] == 6 and run["duration_ms"] < 1500


def test_cancel_rerun_delete(client, auth, project):
    pid = project["id"]
    add_case(client, auth, project)
    run = start_run(client, auth, project)
    assert client.post(f"{API}/projects/{pid}/runs/{run['id']}/cancel", headers=auth).status_code == 409  # already completed
    again = client.post(f"{API}/projects/{pid}/runs/{run['id']}/rerun", headers=auth)
    assert again.status_code == 201 and again.json()["label"] == f"rerun of #{run['id']}"
    assert client.delete(f"{API}/projects/{pid}/runs/{run['id']}", headers=auth).status_code == 204
    assert client.get(f"{API}/projects/{pid}/runs/{run['id']}", headers=auth).status_code == 404


def test_run_for_another_projects_data_is_404(client, auth, project):
    other = client.post(f"{API}/projects", headers=auth, json={"name": "Other"}).json()
    run = start_run(client, auth, project) if add_case(client, auth, project) else None
    assert client.get(f"{API}/projects/{other['id']}/runs/{run['id']}", headers=auth).status_code == 404
    case = add_case(client, auth, project)
    assert client.get(f"{API}/projects/{other['id']}/test-cases/{case['id']}", headers=auth).status_code == 404


def test_ssrf_is_reported_per_test_in_a_run(client, auth):
    """A project pointing at the metadata service: the run completes, the test errors."""
    from app.config import get_settings

    settings = get_settings()
    original = settings.ssrf_allowed_hosts
    settings.ssrf_allowed_hosts = ""
    try:
        project = client.post(f"{API}/projects", headers=auth, json={"name": "Evil", "base_url": "http://169.254.169.254"}).json()
        add_case(client, auth, project, path="/latest/meta-data/")
        run = start_run(client, auth, project)
        results = client.get(f"{API}/projects/{project['id']}/runs/{run['id']}/results", headers=auth).json()["items"]
        assert run["errored"] == 1 and results[0]["error_type"] == "ssrf_blocked"
    finally:
        settings.ssrf_allowed_hosts = original


def test_analytics_and_dashboard(client, auth, project, target):
    pid = project["id"]
    add_case(client, auth, project, name="stable")
    add_case(client, auth, project, name="flaky", path="/ok")
    for broken in (False, True, False):
        target.state["broken"] = broken
        start_run(client, auth, project)
    data = client.get(f"{API}/projects/{pid}/analytics", headers=auth).json()
    assert data["totals"]["runs"] == 3 and len(data["trend"]) == 3
    assert data["overall"]["pass_rate"] is not None and data["overall"]["regressions_detected"] >= 1
    assert {f["name"] for f in data["flaky"]} == {"stable", "flaky"} and data["slowest"]

    dash = client.get(f"{API}/dashboard", headers=auth).json()
    assert dash["projects"] == 1 and dash["runs_14d"] == 3 and len(dash["daily"]) == 14
    assert dash["recent_runs"][0]["project_name"] == "Demo"
    assert any(a["verdict"] == "fail" for a in dash["alerts"])
