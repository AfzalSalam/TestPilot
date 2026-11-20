"""Shared fixtures.

The environment is configured BEFORE the app is imported: tests use a throw-away SQLite
file, run jobs inline (no Redis needed) and allow 127.0.0.1 as an SSRF-exempt host so a
real local HTTP server can act as the "API under test".
"""

import json
import os
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_tmp = tempfile.mkdtemp(prefix="testpilot-")
os.environ.update(
    {
        # Set TESTPILOT_TEST_DATABASE_URL to run the whole suite against PostgreSQL instead of SQLite.
        "TESTPILOT_DATABASE_URL": os.environ.get("TESTPILOT_TEST_DATABASE_URL", f"sqlite:///{_tmp}/test.db"),
        "TESTPILOT_ENVIRONMENT": "test",
        "TESTPILOT_EXECUTION_MODE": "inline",
        "TESTPILOT_RATE_LIMIT_ENABLED": "false",
        "TESTPILOT_SSRF_ALLOWED_HOSTS": "127.0.0.1",
        "TESTPILOT_SECRET_KEY": "test-secret-key-for-pytest-only-0123456789",
        "TESTPILOT_MAX_RESPONSE_BYTES": "1000000",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import ratelimit  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

STATE = {"broken": False, "delay_ms": 0.0}


class TargetHandler(BaseHTTPRequestHandler):
    """A tiny API used as the system under test."""

    def log_message(self, *args):  # silence
        pass

    def _send(self, code, payload, ctype="application/json", headers=None):
        body = payload if isinstance(payload, bytes) else (json.dumps(payload).encode() if ctype == "application/json" else str(payload).encode())
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _route(self):
        path = self.path.split("?")[0]
        if path == "/ok":
            if STATE["broken"]:
                return self._send(500, {"error": "boom"})
            return self._send(200, {"id": 1, "name": "widget", "tags": ["a", "b"], "nested": {"price": 9.5}}, headers={"X-Version": "1.2"})
        if path == "/slow":
            time.sleep(STATE["delay_ms"] / 1000)
            return self._send(200, {"ok": True})
        if path.startswith("/status/"):
            return self._send(int(path.rsplit("/", 1)[1]), {"status": "custom"})
        if path == "/redirect":
            return self._send(302, b"", headers={"Location": "/ok"})
        if path == "/redirect-metadata":
            return self._send(302, b"", headers={"Location": "http://169.254.169.254/latest/meta-data/"})
        if path == "/big":
            return self._send(200, b"x" * 3_000_000, ctype="text/plain")
        if path == "/hang":
            time.sleep(3)
            return self._send(200, {"late": True})
        if path == "/secure":
            if self.headers.get("Authorization") != "Bearer s3cret":
                return self._send(401, {"error": "unauthorized"})
            return self._send(200, {"user": "tester"})
        if path == "/text":
            return self._send(200, "hello world", ctype="text/plain")
        if path == "/echo":
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length).decode() if length else ""
            try:
                parsed = json.loads(raw) if raw else None
            except ValueError:
                parsed = raw
            return self._send(201, {"received": parsed, "content_type": self.headers.get("Content-Type"), "query": self.path.partition("?")[2]})
        return self._send(404, {"error": "not found"})

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _route


class Target:
    def __init__(self, server):
        self.server = server
        self.url = f"http://127.0.0.1:{server.server_address[1]}"
        self.state = STATE


@pytest.fixture(scope="session")
def target():
    server = ThreadingHTTPServer(("127.0.0.1", 0), TargetHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield Target(server)
    server.shutdown()


@pytest.fixture(autouse=True)
def clean_state():
    STATE.update(broken=False, delay_ms=0.0)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    ratelimit.reset()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def register(client: TestClient, email="dev@example.com", name="Dev User", password="correct-horse-1"):
    res = client.post("/api/v1/auth/register", json={"email": email, "password": password, "full_name": name})
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
def auth(client):
    return register(client)


@pytest.fixture
def project(client, auth, target):
    res = client.post("/api/v1/projects", headers=auth, json={"name": "Demo", "base_url": target.url})
    assert res.status_code == 201, res.text
    return res.json()


def add_case(client, auth, project, **overrides):
    body = {"name": "Get widget", "method": "GET", "path": "/ok", "expected_status": 200, **overrides}
    res = client.post(f"/api/v1/projects/{project['id']}/test-cases", headers=auth, json=body)
    assert res.status_code == 201, res.text
    return res.json()


def start_run(client, auth, project, **body):
    res = client.post(f"/api/v1/projects/{project['id']}/runs", headers=auth, json=body)
    assert res.status_code == 201, res.text
    return res.json()
