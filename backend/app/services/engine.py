"""The HTTP test engine: executes ONE test case and returns a plain dict.

The engine is deliberately free of database access so it is safe to run inside worker
threads and trivial to unit-test. The runner (runner.py) owns persistence.
"""

import base64
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import Settings
from app.services.assertions import MISSING, evaluate_assertions
from app.services.ssrf import InvalidURLError, Resolver, SSRFError, validate_url

REDIRECT_CODES = {301, 302, 303, 307, 308}
SENSITIVE_HEADERS = {"authorization", "proxy-authorization", "cookie", "set-cookie", "x-api-key", "x-auth-token"}
SENSITIVE_KEY = re.compile(r"(pass(word)?|secret|token|api[_-]?key|auth|credential|session)", re.I)
VARIABLE = re.compile(r"\{\{\s*([\w.\-]+)\s*\}\}")
REDACTED = "***REDACTED***"


@dataclass
class TestCaseSpec:
    """Immutable snapshot of a test case (so threads never touch ORM objects)."""

    __test__ = False

    id: int | None
    name: str
    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)
    query_params: dict[str, str] = field(default_factory=dict)
    body_type: str = "none"
    body: Any = None
    auth_type: str = "none"
    auth_config: dict[str, str] = field(default_factory=dict)
    expected_status: int = 200
    assertions: list[dict[str, Any]] = field(default_factory=list)
    timeout_s: float | None = None
    follow_redirects: bool = True


class ResponseTooLarge(Exception):
    pass


class TotalTimeout(Exception):
    pass


class MissingVariables(Exception):
    pass


# --------------------------------------------------------------------------- helpers
def substitute(value: Any, variables: dict[str, Any], missing: set[str]) -> Any:
    """Replace {{name}} placeholders recursively in strings, lists and dicts."""
    if isinstance(value, str):

        def repl(match: re.Match) -> str:
            name = match.group(1)
            if name in variables:
                return str(variables[name])
            missing.add(name)
            return match.group(0)

        return VARIABLE.sub(repl, value)
    if isinstance(value, list):
        return [substitute(v, variables, missing) for v in value]
    if isinstance(value, dict):
        return {substitute(k, variables, missing): substitute(v, variables, missing) for k, v in value.items()}
    return value


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    return {k: (REDACTED if k.lower() in SENSITIVE_HEADERS else v) for k, v in headers.items()}


def redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: (REDACTED if SENSITIVE_KEY.search(str(k)) else redact_value(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(v) for v in value]
    return value


def redact_url(url: str) -> str:
    try:
        parsed = httpx.URL(url)
    except httpx.InvalidURL:
        return url
    if not parsed.params:
        return url
    cleaned = {k: (REDACTED if SENSITIVE_KEY.search(k) else v) for k, v in parsed.params.multi_items()}
    return str(parsed.copy_with(params=cleaned))


def build_url(base_url: str, path: str, query: dict[str, str]) -> str:
    if re.match(r"^https?://", path, re.I):
        url = path
    else:
        if not base_url:
            raise InvalidURLError("The project has no base URL and the test path is relative")
        url = base_url.rstrip("/") + "/" + path.lstrip("/")
    try:
        parsed = httpx.URL(url)
        return str(parsed.copy_merge_params(query)) if query else str(parsed)
    except httpx.InvalidURL as exc:
        raise InvalidURLError(f"Malformed URL: {exc}") from exc


def _apply_auth(spec: TestCaseSpec, headers: dict[str, str], query: dict[str, str]) -> None:
    cfg, kind = spec.auth_config, spec.auth_type
    if kind == "bearer":
        headers["Authorization"] = f"Bearer {cfg.get('token', '')}"
    elif kind == "basic":
        raw = f"{cfg.get('username', '')}:{cfg.get('password', '')}".encode()
        headers["Authorization"] = "Basic " + base64.b64encode(raw).decode()
    elif kind == "api_key_header":
        headers[cfg.get("name") or "X-API-Key"] = cfg.get("value", "")
    elif kind == "api_key_query":
        query[cfg.get("name") or "api_key"] = cfg.get("value", "")


def _base_result(spec: TestCaseSpec) -> dict[str, Any]:
    return {
        "test_case_id": spec.id,
        "test_name": spec.name,
        "method": spec.method,
        "url": spec.path,
        "status": "error",
        "status_code": None,
        "response_time_ms": None,
        "response_size": None,
        "error_type": None,
        "error": None,
        "assertion_results": [],
        "request_snapshot": {},
        "response_headers": {},
        "response_body_preview": None,
    }


# --------------------------------------------------------------------------- main entry
def execute_test_case(
    spec: TestCaseSpec,
    *,
    base_url: str,
    variables: dict[str, Any],
    settings: Settings,
    default_timeout_s: float | None = None,
    resolver: Resolver | None = None,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    result = _base_result(spec)
    wall_start = time.perf_counter()
    http_time = 0.0
    timeout_s = min(spec.timeout_s or default_timeout_s or settings.default_timeout_s, settings.max_timeout_s)

    try:
        missing: set[str] = set()
        path = substitute(spec.path, variables, missing)
        headers = {str(k): str(v) for k, v in substitute(spec.headers, variables, missing).items()}
        query = {str(k): str(v) for k, v in substitute(spec.query_params, variables, missing).items()}
        body = substitute(spec.body, variables, missing)
        resolved_spec = TestCaseSpec(
            **{**spec.__dict__, "auth_config": substitute(spec.auth_config, variables, missing)}
        )
        resolved_base = substitute(base_url, variables, missing)
        if missing:
            raise MissingVariables(", ".join(sorted(missing)))

        _apply_auth(resolved_spec, headers, query)
        url = build_url(resolved_base, path, query)
        result["url"] = redact_url(url)

        method = spec.method.upper()
        body_kwargs: dict[str, Any] = {}
        if spec.body_type == "json" and body is not None:
            body_kwargs["json"] = body
        elif spec.body_type == "text" and body is not None:
            body_kwargs["content"] = str(body).encode()
            headers.setdefault("Content-Type", "text/plain")
        elif spec.body_type == "form" and isinstance(body, dict):
            body_kwargs["data"] = {k: str(v) for k, v in body.items()}

        snapshot_body = redact_value(body) if spec.body_type != "none" else None
        snapshot_text = json.dumps(snapshot_body, default=str)[:2000] if snapshot_body is not None else None
        result["request_snapshot"] = {
            "method": method,
            "url": result["url"],
            "headers": redact_headers(headers),
            "body": snapshot_text,
            "redirects": [],
        }

        allowed_hosts = settings.ssrf_allowed_host_set
        current_url, response = url, None
        with httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(timeout_s),
            follow_redirects=False,
            trust_env=False,  # never inherit proxy env vars: they would bypass IP pinning
        ) as client:
            for _hop in range(settings.max_redirects + 1):
                target = validate_url(current_url, allowed_hosts=allowed_hosts, resolver=resolver)
                send_headers = {**headers, "Host": target.host_header}
                extensions = {"sni_hostname": target.host} if target.scheme == "https" else {}
                request = client.build_request(
                    method, target.pinned_url, headers=send_headers, extensions=extensions, **body_kwargs
                )
                t0 = time.perf_counter()
                response = client.send(request, stream=True)

                if spec.follow_redirects and response.status_code in REDIRECT_CODES and response.headers.get("location"):
                    response.close()
                    http_time += time.perf_counter() - t0
                    next_url = str(httpx.URL(current_url).join(response.headers["location"]))
                    result["request_snapshot"]["redirects"].append(redact_url(next_url))
                    if httpx.URL(next_url).host != httpx.URL(current_url).host:
                        headers = {k: v for k, v in headers.items() if k.lower() not in SENSITIVE_HEADERS}
                    if response.status_code == 303 or (response.status_code in (301, 302) and method == "POST"):
                        method, body_kwargs = "GET", {}
                        headers = {k: v for k, v in headers.items() if k.lower() not in ("content-type", "content-length")}
                    current_url = next_url
                    response = None
                    if time.perf_counter() - wall_start > timeout_s:
                        raise TotalTimeout()
                    continue

                # Read the body with a hard size cap and an overall deadline.
                chunks: list[bytes] = []
                size = 0
                try:
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > settings.max_response_bytes:
                            raise ResponseTooLarge()
                        chunks.append(chunk)
                        if time.perf_counter() - wall_start > timeout_s:
                            raise TotalTimeout()
                finally:
                    response.close()
                http_time += time.perf_counter() - t0
                break
            else:
                raise InvalidURLError(f"Too many redirects (limit {settings.max_redirects})")

        elapsed_ms = round(http_time * 1000, 2)
        raw = b"".join(chunks)
        text = raw.decode(response.encoding or "utf-8", errors="replace")
        json_body: Any = MISSING
        if text.strip()[:1] in ("{", "[", '"') or "json" in response.headers.get("content-type", ""):
            try:
                json_body = json.loads(text)
            except ValueError:
                json_body = MISSING

        resp_headers = {k: v for k, v in response.headers.items()}
        outcomes = evaluate_assertions(
            expected_status=spec.expected_status,
            assertions=spec.assertions,
            status_code=response.status_code,
            headers=resp_headers,
            body_text=text,
            json_body=json_body,
            elapsed_ms=elapsed_ms,
        )
        preview = text[: settings.response_preview_bytes]
        result.update(
            status="passed" if all(o["passed"] for o in outcomes) else "failed",
            status_code=response.status_code,
            response_time_ms=elapsed_ms,
            response_size=size,
            assertion_results=outcomes,
            response_headers=redact_headers(resp_headers),
            response_body_preview=preview,
        )
        return result

    except MissingVariables as exc:
        return _error(result, "missing_variable", f"Undefined variable(s): {exc}")
    except SSRFError as exc:
        return _error(result, "ssrf_blocked", str(exc))
    except InvalidURLError as exc:
        return _error(result, "invalid_url", str(exc))
    except (httpx.InvalidURL, httpx.UnsupportedProtocol) as exc:
        return _error(result, "invalid_url", str(exc))
    except ResponseTooLarge:
        return _error(result, "response_too_large", f"Response exceeded {settings.max_response_bytes} bytes")
    except (TotalTimeout, httpx.TimeoutException):
        return _error(result, "timeout", f"Request exceeded the {timeout_s:g}s time limit")
    except httpx.ConnectError as exc:
        return _error(result, "connection_error", f"Could not connect: {exc}")
    except httpx.HTTPError as exc:
        return _error(result, "network_error", f"{type(exc).__name__}: {exc}")
    except Exception as exc:  # last-resort guard: one bad test must never kill the run
        return _error(result, "internal_error", f"{type(exc).__name__}: {exc}")


def _error(result: dict[str, Any], error_type: str, message: str) -> dict[str, Any]:
    result.update(status="error", error_type=error_type, error=message)
    return result
