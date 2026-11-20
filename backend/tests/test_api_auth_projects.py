"""Authentication, project CRUD and project-level access control."""

from sqlalchemy import text

from app.database import engine
from tests.conftest import add_case, register

API = "/api/v1"


def test_register_login_me(client):
    headers = register(client, "a@example.com")
    assert client.get(f"{API}/auth/me", headers=headers).json()["email"] == "a@example.com"
    ok = client.post(f"{API}/auth/login", json={"email": "A@Example.com", "password": "correct-horse-1"})
    assert ok.status_code == 200 and ok.json()["token_type"] == "bearer"


def test_duplicate_email_and_bad_credentials(client):
    register(client, "a@example.com")
    dup = client.post(f"{API}/auth/register", json={"email": "a@example.com", "password": "correct-horse-1", "full_name": "X"})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "email_taken"
    bad = client.post(f"{API}/auth/login", json={"email": "a@example.com", "password": "wrong-password"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "invalid_credentials"
    ghost = client.post(f"{API}/auth/login", json={"email": "nobody@example.com", "password": "wrong-password"})
    assert ghost.status_code == 401 and ghost.json()["error"]["message"] == bad.json()["error"]["message"]


def test_password_is_hashed_not_stored(client):
    register(client, "a@example.com", password="correct-horse-1")
    with engine.connect() as conn:
        stored = conn.execute(text("SELECT hashed_password FROM users")).scalar()
    assert stored != "correct-horse-1" and stored.startswith("$2")


def test_validation_errors_use_the_standard_envelope(client):
    res = client.post(f"{API}/auth/register", json={"email": "not-an-email", "password": "short", "full_name": ""})
    body = res.json()
    assert res.status_code == 422 and body["error"]["code"] == "validation_error"
    assert {d["field"] for d in body["error"]["details"]} >= {"email", "password", "full_name"}


def test_endpoints_require_authentication(client):
    assert client.get(f"{API}/projects").status_code == 401
    assert client.get(f"{API}/projects", headers={"Authorization": "Bearer garbage"}).json()["error"]["code"] == "invalid_token"


def test_project_crud(client, auth):
    created = client.post(f"{API}/projects", headers=auth, json={"name": "Shop", "base_url": "https://api.shop.test/", "variables": {"token": "abc"}})
    assert created.status_code == 201
    project = created.json()
    assert project["base_url"] == "https://api.shop.test" and project["role"] == "owner"
    assert project["variables"] == {"token": "abc"}  # owners/editors can read variable values

    dup = client.post(f"{API}/projects", headers=auth, json={"name": "Shop"})
    assert dup.status_code == 409

    patched = client.patch(f"{API}/projects/{project['id']}", headers=auth, json={"description": "Shop API", "default_timeout_s": 5})
    assert patched.json()["description"] == "Shop API" and patched.json()["default_timeout_s"] == 5
    assert len(client.get(f"{API}/projects", headers=auth).json()) == 1
    assert client.delete(f"{API}/projects/{project['id']}", headers=auth).status_code == 204
    assert client.get(f"{API}/projects/{project['id']}", headers=auth).status_code == 404


def test_invalid_project_input(client, auth):
    assert client.post(f"{API}/projects", headers=auth, json={"name": "x", "base_url": "ftp://nope"}).status_code == 422
    assert client.post(f"{API}/projects", headers=auth, json={"name": "x", "variables": {"bad name": "1"}}).status_code == 422
    assert client.post(f"{API}/projects", headers=auth, json={"name": "x", "default_timeout_s": 999}).status_code == 422


def test_other_users_cannot_see_a_project(client, project):
    stranger = register(client, "stranger@example.com")
    assert client.get(f"{API}/projects/{project['id']}", headers=stranger).status_code == 404
    assert client.get(f"{API}/projects/{project['id']}/test-cases", headers=stranger).status_code == 404
    assert client.post(f"{API}/projects/{project['id']}/runs", headers=stranger, json={}).status_code == 404
    assert client.get(f"{API}/projects", headers=stranger).json() == []


def test_roles_viewer_editor_owner(client, auth, project):
    viewer, editor = register(client, "v@example.com"), register(client, "e@example.com")
    pid = project["id"]
    assert client.post(f"{API}/projects/{pid}/members", headers=auth, json={"email": "v@example.com", "role": "viewer"}).status_code == 201
    assert client.post(f"{API}/projects/{pid}/members", headers=auth, json={"email": "e@example.com", "role": "editor"}).status_code == 201
    case = add_case(client, auth, project, name="Secured", auth_type="bearer", auth_config={"token": "s3cret"})

    # viewer: read-only, variable values and credentials masked
    assert client.get(f"{API}/projects/{pid}/test-cases", headers=viewer).status_code == 200
    assert client.post(f"{API}/projects/{pid}/test-cases", headers=viewer, json={"name": "n", "path": "/ok"}).status_code == 403
    assert client.delete(f"{API}/projects/{pid}/test-cases/{case['id']}", headers=viewer).status_code == 403
    assert client.post(f"{API}/projects/{pid}/runs", headers=viewer, json={}).status_code == 403
    assert client.get(f"{API}/projects/{pid}", headers=viewer).json()["role"] == "viewer"

    # editor: can write but cannot manage members, keys or delete the project
    assert client.post(f"{API}/projects/{pid}/test-cases", headers=editor, json={"name": "n", "path": "/ok"}).status_code == 201
    assert client.post(f"{API}/projects/{pid}/members", headers=editor, json={"email": "v@example.com"}).status_code == 403
    assert client.get(f"{API}/projects/{pid}/api-keys", headers=editor).status_code == 403
    assert client.delete(f"{API}/projects/{pid}", headers=editor).status_code == 403

    members = client.get(f"{API}/projects/{pid}/members", headers=auth).json()
    assert {m["role"] for m in members} == {"owner", "viewer", "editor"}
    editor_id = next(m["user_id"] for m in members if m["role"] == "editor")
    assert client.patch(f"{API}/projects/{pid}/members/{editor_id}", headers=auth, json={"role": "viewer"}).json()["role"] == "viewer"
    assert client.delete(f"{API}/projects/{pid}/members/{editor_id}", headers=auth).status_code == 204
    assert client.get(f"{API}/projects/{pid}", headers=editor).status_code == 404  # removed -> no access


def test_member_edge_cases(client, auth, project):
    pid = project["id"]
    assert client.post(f"{API}/projects/{pid}/members", headers=auth, json={"email": "ghost@example.com"}).status_code == 404
    register(client, "v@example.com")
    assert client.post(f"{API}/projects/{pid}/members", headers=auth, json={"email": "v@example.com"}).status_code == 201
    assert client.post(f"{API}/projects/{pid}/members", headers=auth, json={"email": "v@example.com"}).status_code == 409
    owner_id = client.get(f"{API}/auth/me", headers=auth).json()["id"]
    assert client.delete(f"{API}/projects/{pid}/members/{owner_id}", headers=auth).json()["error"]["code"] == "owner_immutable"


def test_credentials_are_masked_and_encrypted_at_rest(client, auth, project):
    case = add_case(client, auth, project, auth_type="bearer", auth_config={"token": "super-secret-token"})
    assert case["auth_config"] == {"token": "********"}
    with engine.connect() as conn:
        raw = conn.execute(text("SELECT auth_config FROM test_cases")).scalar()
    assert "super-secret-token" not in raw  # ciphertext in the database

    # Echoing the mask back keeps the stored secret
    pid = project["id"]
    client.patch(f"{API}/projects/{pid}/test-cases/{case['id']}", headers=auth, json={"auth_config": {"token": "********"}, "name": "renamed"})
    from app.database import SessionLocal
    from app.models import TestCase

    with SessionLocal() as db:
        assert db.get(TestCase, case["id"]).auth_config == {"token": "super-secret-token"}


def test_project_variables_masked_for_viewers_and_preserved_on_echo(client, auth):
    project = client.post(f"{API}/projects", headers=auth, json={"name": "V", "variables": {"token": "t0k3n", "env": "prod"}}).json()
    viewer = register(client, "v@example.com")
    client.post(f"{API}/projects/{project['id']}/members", headers=auth, json={"email": "v@example.com"})
    assert client.get(f"{API}/projects/{project['id']}", headers=viewer).json()["variables"] == {"token": "********", "env": "********"}
    updated = client.patch(f"{API}/projects/{project['id']}", headers=auth, json={"variables": {"token": "********", "env": "staging"}})
    assert updated.json()["variables"] == {"token": "t0k3n", "env": "staging"}


def test_health_and_request_id(client):
    res = client.get(f"{API}/health")
    assert res.status_code == 200 and res.json()["checks"]["database"] == "ok"
    assert "x-request-id" in res.headers


def test_rate_limit_on_auth(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    monkeypatch.setattr(get_settings(), "rate_limit_auth_per_minute", 3)
    codes = [client.post(f"{API}/auth/login", json={"email": "x@example.com", "password": "whatever-1"}).status_code for _ in range(5)]
    assert codes[:3] == [401, 401, 401] and codes[3:] == [429, 429]
    limited = client.post(f"{API}/auth/login", json={"email": "x@example.com", "password": "whatever-1"})
    assert limited.json()["error"]["code"] == "rate_limited" and "retry-after" in limited.headers
