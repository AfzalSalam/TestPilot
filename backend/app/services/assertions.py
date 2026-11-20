"""Assertion evaluation: compares an HTTP response with a test case's expectations."""

import json
import re
from typing import Any

OPERATORS = {
    "eq", "neq", "contains", "not_contains", "exists", "not_exists",
    "gt", "gte", "lt", "lte", "regex", "type", "length",
}  # fmt: skip
ASSERTION_TYPES = {"json_path", "header", "body_contains", "response_time"}
MAX_REGEX_LEN = 200
MAX_REGEX_INPUT = 100_000  # bound the work a user-supplied regex can do

_TOKEN = re.compile(r"""\.([A-Za-z_][\w-]*)|\[(\d+)\]|\['([^']*)'\]|\["([^"]*)"\]""")
_MISSING = object()


def resolve_json_path(data: Any, path: str) -> Any:
    """Tiny JSONPath subset: ``$.a.b[0]['key']``. Returns _MISSING when absent."""
    path = path.strip()
    if not path.startswith("$"):
        path = "$." + path.lstrip(".")
    pos, current = 1, data
    while pos < len(path):
        match = _TOKEN.match(path, pos)
        if not match:
            raise ValueError(f"Unsupported JSON path syntax near '{path[pos:]}'")
        pos = match.end()
        key, index, sq, dq = match.groups()
        name = key or sq or dq
        if index is not None:
            if not isinstance(current, list) or int(index) >= len(current):
                return _MISSING
            current = current[int(index)]
        else:
            if not isinstance(current, dict) or name not in current:
                return _MISSING
            current = current[name]
    return current


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def _as_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return value if isinstance(value, str) else json.dumps(value, sort_keys=True)


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compare(operator: str, actual: Any, expected: Any) -> bool:
    if operator == "exists":
        return actual is not _MISSING
    if operator == "not_exists":
        return actual is _MISSING
    if actual is _MISSING:
        return operator in ("neq", "not_contains")
    if operator == "eq":
        return actual == expected or (not isinstance(actual, (dict, list)) and _as_text(actual) == _as_text(expected))
    if operator == "neq":
        return not compare("eq", actual, expected)
    if operator == "contains":
        if isinstance(actual, dict):
            return _as_text(expected) in actual
        if isinstance(actual, list):
            return any(compare("eq", item, expected) for item in actual)
        return _as_text(expected) in _as_text(actual)
    if operator == "not_contains":
        return not compare("contains", actual, expected)
    if operator in ("gt", "gte", "lt", "lte"):
        a, b = _num(actual), _num(expected)
        if a is None or b is None:
            return False
        return {"gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b}[operator]
    if operator == "regex":
        pattern = str(expected)
        if len(pattern) > MAX_REGEX_LEN:
            raise ValueError("Regex pattern too long")
        return re.search(pattern, _as_text(actual)[:MAX_REGEX_INPUT]) is not None
    if operator == "type":
        return _type_name(actual) == str(expected) or (str(expected) == "number" and _type_name(actual) == "integer")
    if operator == "length":
        return isinstance(actual, (str, list, dict)) and len(actual) == _num(expected)
    raise ValueError(f"Unknown operator '{operator}'")


def _preview(value: Any) -> Any:
    if value is _MISSING:
        return "<missing>"
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= 200 else text[:200] + "…"


def _outcome(kind: str, description: str, passed: bool, expected: Any, actual: Any, message: str = "") -> dict:
    return {
        "type": kind,
        "description": description,
        "passed": passed,
        "expected": _preview(expected),
        "actual": _preview(actual),
        "message": message,
    }


def evaluate_assertions(
    *,
    expected_status: int,
    assertions: list[dict[str, Any]],
    status_code: int,
    headers: dict[str, str],
    body_text: str,
    json_body: Any,
    elapsed_ms: float,
) -> list[dict[str, Any]]:
    results = [
        _outcome(
            "status_code",
            f"Status code is {expected_status}",
            status_code == expected_status,
            expected_status,
            status_code,
        )
    ]
    lowered = {k.lower(): v for k, v in headers.items()}

    for assertion in assertions:
        kind = assertion.get("type")
        operator = assertion.get("operator", "eq")
        expected = assertion.get("value")
        try:
            if kind == "json_path":
                path = assertion["path"]
                description = f"JSON {path} {operator} {_preview(expected)}".rstrip()
                if json_body is _MISSING:
                    results.append(_outcome(kind, description, False, expected, _MISSING, "Response is not valid JSON"))
                    continue
                actual = resolve_json_path(json_body, path)
                results.append(_outcome(kind, description, compare(operator, actual, expected), expected, actual))
            elif kind == "header":
                name = assertion["name"]
                description = f"Header {name} {operator} {_preview(expected)}".rstrip()
                actual = lowered.get(name.lower(), _MISSING)
                results.append(_outcome(kind, description, compare(operator, actual, expected), expected, actual))
            elif kind == "body_contains":
                description = f"Body contains {_preview(expected)}"
                results.append(_outcome(kind, description, _as_text(expected) in body_text, expected, "(body)"))
            elif kind == "response_time":
                limit = float(assertion["max_ms"])
                results.append(
                    _outcome(kind, f"Response time under {limit:g} ms", elapsed_ms <= limit, f"≤ {limit:g} ms", f"{elapsed_ms:.0f} ms")
                )
            else:
                results.append(_outcome(str(kind), "Unknown assertion", False, expected, None, f"Unknown assertion type '{kind}'"))
        except (KeyError, ValueError, TypeError) as exc:
            results.append(_outcome(str(kind), f"Assertion {kind}", False, expected, None, f"Invalid assertion: {exc}"))
    return results


MISSING = _MISSING
