"""The HTTP engine against a real local server (see conftest.TargetHandler)."""

from app.config import Settings, get_settings
from app.services.engine import TestCaseSpec, execute_test_case, redact_url


def run(target, settings=None, variables=None, base=None, **spec):
    spec.setdefault("name", "t")
    spec.setdefault("method", "GET")
    spec.setdefault("path", "/ok")
    return execute_test_case(
        TestCaseSpec(id=1, **spec),
        base_url=base if base is not None else target.url,
        variables=variables or {},
        settings=settings or get_settings(),
    )


def test_passing_request_with_assertions(target):
    res = run(
        target,
        assertions=[
            {"type": "json_path", "path": "$.name", "operator": "eq", "value": "widget"},
            {"type": "json_path", "path": "$.tags", "operator": "length", "value": 2},
            {"type": "header", "name": "X-Version", "operator": "eq", "value": "1.2"},
        ],
    )
    assert res["status"] == "passed"
    assert res["status_code"] == 200 and res["response_time_ms"] > 0
    assert all(a["passed"] for a in res["assertion_results"])


def test_wrong_status_is_a_failure_not_an_error(target):
    res = run(target, path="/status/418", expected_status=200)
    assert res["status"] == "failed" and res["status_code"] == 418 and res["error"] is None


def test_expected_non_2xx_status_passes(target):
    assert run(target, path="/status/404", expected_status=404)["status"] == "passed"


def test_failed_assertion_marks_failed(target):
    res = run(target, assertions=[{"type": "json_path", "path": "$.id", "operator": "eq", "value": 999}])
    assert res["status"] == "failed"


def test_post_json_body_and_query_params(target):
    res = run(
        target, method="POST", path="/echo", body_type="json", body={"hello": "world"},
        query_params={"page": "2"}, expected_status=201,
        assertions=[{"type": "json_path", "path": "$.received.hello", "operator": "eq", "value": "world"},
                    {"type": "json_path", "path": "$.query", "operator": "contains", "value": "page=2"}],
    )  # fmt: skip
    assert res["status"] == "passed", res["assertion_results"]


def test_form_and_text_bodies(target):
    form = run(target, method="POST", path="/echo", body_type="form", body={"a": "1"}, expected_status=201)
    assert "x-www-form-urlencoded" in form["response_body_preview"]
    text = run(target, method="POST", path="/echo", body_type="text", body="plain", expected_status=201)
    assert "text/plain" in text["response_body_preview"]


def test_bearer_auth_and_redaction(target):
    res = run(target, path="/secure", auth_type="bearer", auth_config={"token": "s3cret"}, expected_status=200)
    assert res["status"] == "passed"
    assert res["request_snapshot"]["headers"]["Authorization"] == "***REDACTED***"
    assert "s3cret" not in str(res["request_snapshot"])


def test_api_key_query_is_redacted_in_stored_url(target):
    res = run(target, path="/ok", auth_type="api_key_query", auth_config={"name": "api_key", "value": "topsecret"})
    assert "topsecret" not in res["url"] and "REDACTED" in res["url"]


def test_basic_auth_header_is_built(target):
    res = run(target, path="/secure", auth_type="basic", auth_config={"username": "u", "password": "p"}, expected_status=401)
    assert res["status"] == "passed"


def test_variables_are_substituted(target):
    res = run(target, path="/secure", headers={"Authorization": "Bearer {{token}}"}, variables={"token": "s3cret"})
    assert res["status"] == "passed"
    assert "s3cret" not in str(res["request_snapshot"])


def test_undefined_variable_is_reported_not_sent(target):
    res = run(target, path="/ok", headers={"X": "{{nope}}"})
    assert res["status"] == "error" and res["error_type"] == "missing_variable"


def test_redirects_followed_and_recorded(target):
    res = run(target, path="/redirect")
    assert res["status"] == "passed" and res["request_snapshot"]["redirects"]


def test_redirects_can_be_disabled(target):
    res = run(target, path="/redirect", follow_redirects=False, expected_status=302)
    assert res["status"] == "passed"


def test_timeout_is_an_error(target):
    res = run(target, path="/hang", timeout_s=0.5)
    assert res["status"] == "error" and res["error_type"] == "timeout"


def test_connection_refused_is_an_error(target):
    res = run(target, base="http://127.0.0.1:1", path="/ok")
    assert res["status"] == "error" and res["error_type"] in ("connection_error", "network_error")


def test_oversized_response_is_cut_off(target):
    settings = Settings(ssrf_allowed_hosts="127.0.0.1", max_response_bytes=100_000)
    res = run(target, settings=settings, path="/big", expected_status=200)
    assert res["status"] == "error" and res["error_type"] == "response_too_large"


def test_relative_path_without_base_url_is_invalid(target):
    res = run(target, base="", path="/ok")
    assert res["status"] == "error" and res["error_type"] == "invalid_url"


def test_loopback_blocked_without_allowlist(target):
    strict = Settings(ssrf_allowed_hosts="")
    res = run(target, settings=strict, path="/ok")
    assert res["status"] == "error" and res["error_type"] == "ssrf_blocked"


def test_metadata_ip_literal_blocked():
    strict = Settings(ssrf_allowed_hosts="")
    res = execute_test_case(
        TestCaseSpec(id=1, name="x", method="GET", path="http://169.254.169.254/latest/meta-data/"),
        base_url="", variables={}, settings=strict,
    )  # fmt: skip
    assert res["error_type"] == "ssrf_blocked"


def test_redirect_to_metadata_is_blocked_on_each_hop(target):
    """The first hop is allow-listed (127.0.0.1) but the redirect target is not."""
    res = run(target, path="/redirect-metadata")
    assert res["status"] == "error" and res["error_type"] == "ssrf_blocked"


def test_file_scheme_blocked(target):
    res = run(target, base="", path="file:///etc/passwd")
    assert res["status"] == "error" and res["error_type"] == "invalid_url"


def test_redact_url_helper():
    assert "abc123" not in redact_url("http://x.test/p?token=abc123&page=1")
    assert "page=1" in redact_url("http://x.test/p?token=abc123&page=1")
