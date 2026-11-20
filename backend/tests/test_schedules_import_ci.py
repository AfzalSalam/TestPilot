"""Schedules, OpenAPI import and the CI (GitHub Actions) integration."""

import json
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.database import SessionLocal
from app.errors import AppError
from app.models import Run, Schedule
from app.services.scheduler import run_due_schedules, validate_cron
from app.utils import utcnow
from tests.conftest import add_case, register, start_run

API = "/api/v1"


# ---------------------------------------------------------------- schedules
def test_cron_validation():
    assert validate_cron("*/15  * * * *") == "*/15 * * * *"
    for bad in ("nonsense", "* * * *", "61 * * * *", "* * * * * *"):
        with pytest.raises(AppError):
            validate_cron(bad)


def test_schedule_crud_preview_and_pause(client, auth, project):
    pid = project["id"]
    add_case(client, auth, project)
    preview = client.get(f"{API}/projects/{pid}/schedules/preview", headers=auth, params={"cron": "0 * * * *"}).json()
    assert preview["valid"] and len(preview["upcoming"]) == 5
    assert client.get(f"{API}/projects/{pid}/schedules/preview", headers=auth, params={"cron": "bad"}).json()["valid"] is False

    created = client.post(f"{API}/projects/{pid}/schedules", headers=auth, json={"name": "Hourly", "cron": "0 * * * *"})
    assert created.status_code == 201 and created.json()["next_run_at"]
    sid = created.json()["id"]
    assert client.post(f"{API}/projects/{pid}/schedules", headers=auth, json={"name": "x", "cron": "bad cron expr"}).status_code == 422
    paused = client.patch(f"{API}/projects/{pid}/schedules/{sid}", headers=auth, json={"enabled": False}).json()
    assert paused["enabled"] is False and paused["next_run_at"] is None
    resumed = client.patch(f"{API}/projects/{pid}/schedules/{sid}", headers=auth, json={"enabled": True, "cron": "*/5 * * * *"}).json()
    assert resumed["cron"] == "*/5 * * * *" and resumed["next_run_at"]

    manual = client.post(f"{API}/projects/{pid}/schedules/{sid}/trigger", headers=auth)
    assert manual.status_code == 201 and manual.json()["schedule_id"] == sid
    assert client.delete(f"{API}/projects/{pid}/schedules/{sid}", headers=auth).status_code == 204


def test_due_schedule_creates_one_run_and_advances(client, auth, project):
    pid = project["id"]
    add_case(client, auth, project)
    sid = client.post(f"{API}/projects/{pid}/schedules", headers=auth, json={"name": "Every 5", "cron": "*/5 * * * *"}).json()["id"]
    with SessionLocal() as db:
        db.execute(update(Schedule).where(Schedule.id == sid).values(next_run_at=utcnow() - timedelta(minutes=1)))
        db.commit()
    with SessionLocal() as db:
        created = run_due_schedules(db)
        assert len(created) == 1
        assert run_due_schedules(db) == []  # next_run_at moved into the future: no double firing
        run = db.get(Run, created[0])
        assert run.trigger == "schedule" and run.schedule_id == sid and run.status == "completed"
        assert db.get(Schedule, sid).next_run_at > utcnow()


def test_overlapping_scheduled_runs_are_skipped(client, auth, project, monkeypatch):
    pid = project["id"]
    add_case(client, auth, project)
    monkeypatch.setattr("app.services.scheduler.dispatch_run_safe", lambda db, run: True)  # stays 'queued'
    sid = client.post(f"{API}/projects/{pid}/schedules", headers=auth, json={"name": "s", "cron": "*/5 * * * *"}).json()["id"]
    for _ in range(2):
        with SessionLocal() as db:
            db.execute(update(Schedule).where(Schedule.id == sid).values(next_run_at=utcnow() - timedelta(minutes=1)))
            db.commit()
            run_due_schedules(db)
    with SessionLocal() as db:
        assert len(db.scalars(select(Run).where(Run.schedule_id == sid)).all()) == 1


def test_two_tickers_racing_create_a_single_run(client, auth, project, monkeypatch):
    pid = project["id"]
    add_case(client, auth, project)
    monkeypatch.setattr("app.services.scheduler.dispatch_run_safe", lambda db, run: True)
    sid = client.post(f"{API}/projects/{pid}/schedules", headers=auth, json={"name": "s", "cron": "*/5 * * * *"}).json()["id"]
    with SessionLocal() as setup:
        setup.execute(update(Schedule).where(Schedule.id == sid).values(next_run_at=utcnow() - timedelta(minutes=1)))
        setup.commit()
    with SessionLocal() as a, SessionLocal() as b:
        stale_a = a.scalars(select(Schedule)).all()  # both tickers read the same due row...
        stale_b = b.scalars(select(Schedule)).all()
        assert stale_a and stale_b
        first, second = run_due_schedules(a), run_due_schedules(b)
    assert len(first) + len(second) == 1  # ...but only one wins the compare-and-set


# ---------------------------------------------------------------- OpenAPI import
SPEC = {
    "openapi": "3.0.3",
    "info": {"title": "Pet Store", "version": "1"},
    "servers": [{"url": "https://pets.example.com/v1/"}],
    "paths": {
        "/pets": {
            "get": {"operationId": "listPets", "parameters": [{"name": "limit", "in": "query", "required": True, "schema": {"type": "integer", "default": 10}}],
                    "responses": {"200": {"description": "ok"}}},
            "post": {"summary": "Create pet", "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Pet"}}}},
                     "responses": {"201": {"description": "created"}, "400": {"description": "bad"}}},
        },
        "/pets/{petId}": {
            "parameters": [{"name": "petId", "in": "path", "required": True, "schema": {"type": "integer"}}],
            "get": {"responses": {"200": {"description": "ok"}, "404": {"description": "nope"}}},
            "delete": {"responses": {"204": {"description": "gone"}}},
        },
    },
    "components": {"schemas": {"Pet": {"type": "object", "properties": {"name": {"type": "string", "example": "Rex"}, "age": {"type": "integer"}}}}},
}


def test_openapi_import_json_creates_endpoints_and_tests(client, auth, project):
    pid = project["id"]
    res = client.post(f"{API}/projects/{pid}/import/openapi", headers=auth,
                      json={"spec_text": json.dumps(SPEC), "create_collection": True, "set_base_url": True})
    body = res.json()
    assert res.status_code == 200 and body["title"] == "Pet Store"
    assert (body["endpoints_created"], body["test_cases_created"]) == (4, 4) and body["base_url_updated"]

    cases = {c["name"]: c for c in client.get(f"{API}/projects/{pid}/test-cases", headers=auth).json()}
    assert cases["listPets"]["query_params"] == {"limit": "10"}
    assert cases["Create pet"]["body"] == {"name": "Rex", "age": 1} and cases["Create pet"]["expected_status"] == 201
    assert cases["GET /pets/{petId}"]["path"] == "/pets/1" and cases["GET /pets/{petId}"]["collection_id"] == body["collection_id"]
    assert cases["DELETE /pets/{petId}"]["expected_status"] == 204
    assert client.get(f"{API}/projects/{pid}", headers=auth).json()["base_url"] == "https://pets.example.com/v1"

    again = client.post(f"{API}/projects/{pid}/import/openapi", headers=auth, json={"spec_text": json.dumps(SPEC)}).json()
    assert (again["endpoints_created"], again["endpoints_skipped"], again["test_cases_created"], again["test_cases_skipped"]) == (0, 4, 0, 4)


def test_openapi_import_yaml_and_endpoints_only(client, auth, project):
    yaml_spec = "openapi: 3.0.0\ninfo: {title: T, version: '1'}\npaths:\n  /a:\n    get:\n      responses:\n        '200': {description: ok}\n"
    res = client.post(f"{API}/projects/{project['id']}/import/openapi", headers=auth, json={"spec_text": yaml_spec, "create_test_cases": False}).json()
    assert res["endpoints_created"] == 1 and res["test_cases_created"] == 0


def test_swagger2_body_parameter(client, auth, project):
    spec = {"swagger": "2.0", "info": {"title": "Old"}, "host": "old.example.com", "basePath": "/api", "schemes": ["https"],
            "paths": {"/items": {"post": {"parameters": [{"in": "body", "name": "b", "schema": {"type": "object", "properties": {"n": {"type": "string"}}}}],
                                          "responses": {"201": {}}}}}}
    body = client.post(f"{API}/projects/{project['id']}/import/openapi", headers=auth, json={"spec_text": json.dumps(spec)}).json()
    assert body["servers"] == ["https://old.example.com/api"] and body["test_cases_created"] == 1


@pytest.mark.parametrize("text", ["not: [valid", "{}", "just text", '{"paths": {}}', '{"openapi": "3.0.0", "paths": {}}'])
def test_invalid_specs_rejected(client, auth, project, text):
    res = client.post(f"{API}/projects/{project['id']}/import/openapi", headers=auth, json={"spec_text": text})
    assert res.status_code == 422


def test_recursive_refs_do_not_hang(client, auth, project):
    spec = {"openapi": "3.0.0", "info": {"title": "R"}, "components": {"schemas": {"Node": {"type": "object", "properties": {"next": {"$ref": "#/components/schemas/Node"}}}}},
            "paths": {"/n": {"post": {"requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Node"}}}}, "responses": {"200": {}}}}}}
    assert client.post(f"{API}/projects/{project['id']}/import/openapi", headers=auth, json={"spec_text": json.dumps(spec)}).status_code == 200


# ---------------------------------------------------------------- CI / GitHub Actions
def _key(client, auth, project):
    res = client.post(f"{API}/projects/{project['id']}/api-keys", headers=auth, json={"name": "github"})
    assert res.status_code == 201
    return res.json()


def test_api_key_lifecycle(client, auth, project):
    created = _key(client, auth, project)
    assert created["key"].startswith("tp_") and created["prefix"] == created["key"][:10]
    listed = client.get(f"{API}/projects/{project['id']}/api-keys", headers=auth).json()
    assert "key" not in listed[0] and "key_hash" not in listed[0]
    assert client.delete(f"{API}/projects/{project['id']}/api-keys/{created['id']}", headers=auth).status_code == 204
    assert client.post(f"{API}/ci/runs", headers={"X-API-Key": created["key"]}, json={}).status_code == 401


def test_ci_trigger_and_poll_success_and_failure(client, auth, project, target):
    key = {"X-API-Key": _key(client, auth, project)["key"]}
    add_case(client, auth, project)
    started = client.post(f"{API}/ci/runs", headers=key, json={"label": "sha-1234"})
    assert started.status_code == 201 and started.json()["conclusion"] == "success"
    run_id = started.json()["id"]
    assert client.get(f"{API}/projects/{project['id']}/runs/{run_id}", headers=auth).json()["trigger"] == "ci"

    target.state["broken"] = True
    broken = client.post(f"{API}/ci/runs", headers=key, json={"label": "sha-5678"}).json()
    assert broken["conclusion"] == "failure" and broken["regression"]["verdict"] == "fail"
    assert broken["regression"]["new_failures_detail"][0]["test"] == "Get widget"
    polled = client.get(f"{API}/ci/runs/{broken['id']}", headers=key).json()
    assert polled["finished"] and polled["conclusion"] == "failure"


def test_ci_key_cannot_read_other_projects_or_use_wrong_key(client, auth, project):
    key = {"X-API-Key": _key(client, auth, project)["key"]}
    other_headers = register(client, "other@example.com")
    other_project = client.post(f"{API}/projects", headers=other_headers, json={"name": "Theirs", "base_url": "http://127.0.0.1:1"}).json()
    add_case(client, other_headers, other_project)
    their_run = start_run(client, other_headers, other_project)
    assert client.get(f"{API}/ci/runs/{their_run['id']}", headers=key).status_code == 404
    assert client.post(f"{API}/ci/runs", headers={"X-API-Key": "tp_wrong"}, json={}).status_code == 401
    assert client.post(f"{API}/ci/runs", json={}).status_code == 401
    assert client.post(f"{API}/ci/runs", headers=key, json={}).status_code == 422  # project has no enabled tests yet


def test_ci_fail_on_performance_flag(client, auth, project, target):
    key = {"X-API-Key": _key(client, auth, project)["key"]}
    add_case(client, auth, project, path="/slow")
    target.state["delay_ms"] = 20
    for _ in range(4):
        client.post(f"{API}/ci/runs", headers=key, json={})
    target.state["delay_ms"] = 600
    slow = client.post(f"{API}/ci/runs", headers=key, json={}).json()
    assert slow["regression"]["verdict"] == "warn" and slow["conclusion"] == "success"
    strict = client.get(f"{API}/ci/runs/{slow['id']}", headers=key, params={"fail_on_performance": "true"}).json()
    assert strict["conclusion"] == "failure"
