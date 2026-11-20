import pytest

from app.services.assertions import MISSING, compare, evaluate_assertions, resolve_json_path

DATA = {"id": 7, "tags": ["a", "b"], "nested": {"price": 9.5, "items": [{"sku": "x1"}]}, "flag": True, "none": None}


@pytest.mark.parametrize(
    "path,expected",
    [("$.id", 7), ("id", 7), ("$.tags[1]", "b"), ("$.nested.items[0].sku", "x1"), ("$['nested']['price']", 9.5), ("$.none", None)],
)
def test_json_path_resolution(path, expected):
    assert resolve_json_path(DATA, path) == expected


@pytest.mark.parametrize("path", ["$.missing", "$.tags[5]", "$.id.deeper", "$.nested.items[0].nope"])
def test_json_path_missing(path):
    assert resolve_json_path(DATA, path) is MISSING


def test_json_path_rejects_bad_syntax():
    with pytest.raises(ValueError):
        resolve_json_path(DATA, "$..id")


@pytest.mark.parametrize(
    "op,actual,expected,result",
    [
        ("eq", 7, 7, True), ("eq", 7, "7", True), ("eq", True, "true", True), ("eq", "a", "b", False),
        ("neq", 1, 2, True), ("contains", "hello world", "world", True), ("contains", ["a", "b"], "b", True),
        ("contains", {"k": 1}, "k", True), ("not_contains", "abc", "z", True),
        ("gt", 5, 3, True), ("gte", 3, 3, True), ("lt", 2, 3, True), ("lte", 4, 3, False), ("gt", "x", 1, False),
        ("regex", "order-123", r"^order-\d+$", True), ("regex", "nope", r"^\d+$", False),
        ("type", [1], "array", True), ("type", 3, "number", True), ("type", "s", "integer", False), ("type", None, "null", True),
        ("length", [1, 2, 3], 3, True), ("length", "ab", 3, False),
        ("exists", 0, None, True), ("exists", MISSING, None, False), ("not_exists", MISSING, None, True),
    ],
)  # fmt: skip
def test_operators(op, actual, expected, result):
    assert compare(op, actual, expected) is result


def test_regex_length_guard():
    with pytest.raises(ValueError):
        compare("regex", "x", "a" * 500)


def test_evaluate_collects_each_outcome():
    results = evaluate_assertions(
        expected_status=200,
        assertions=[
            {"type": "json_path", "path": "$.id", "operator": "eq", "value": 7},
            {"type": "json_path", "path": "$.nested.price", "operator": "gt", "value": 100},
            {"type": "header", "name": "x-version", "operator": "eq", "value": "1.2"},
            {"type": "body_contains", "value": "widget"},
            {"type": "response_time", "max_ms": 50},
            {"type": "json_path", "path": "$..bad", "operator": "eq", "value": 1},
        ],
        status_code=200,
        headers={"X-Version": "1.2"},
        body_text='{"name":"widget"}',
        json_body=DATA,
        elapsed_ms=120,
    )
    assert [r["passed"] for r in results] == [True, True, False, True, True, False, False]
    assert "Invalid assertion" in results[-1]["message"]


def test_json_assertion_on_non_json_body_fails_cleanly():
    results = evaluate_assertions(
        expected_status=200, assertions=[{"type": "json_path", "path": "$.a", "operator": "exists"}],
        status_code=200, headers={}, body_text="<html>", json_body=MISSING, elapsed_ms=1,
    )  # fmt: skip
    assert results[1]["passed"] is False and "not valid JSON" in results[1]["message"]
