"""Import an OpenAPI 3.x / Swagger 2.0 document as endpoints and starter test cases."""

import json
from dataclasses import dataclass, field
from typing import Any

import yaml

from app.errors import AppError

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")
MAX_OPERATIONS = 500


@dataclass
class ImportedOperation:
    name: str
    method: str
    path: str  # template path with {params} substituted by examples
    template_path: str
    description: str
    query_params: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None
    body_type: str = "none"
    expected_status: int = 200


def parse_spec(text: str) -> dict[str, Any]:
    try:
        spec = yaml.safe_load(text)  # YAML is a superset of JSON, so this handles both
    except yaml.YAMLError as exc:
        raise AppError(422, "invalid_spec", f"The document is not valid JSON or YAML: {exc}") from exc
    if not isinstance(spec, dict) or not isinstance(spec.get("paths"), dict):
        raise AppError(422, "invalid_spec", "Not an OpenAPI/Swagger document (missing 'paths')")
    if "openapi" not in spec and "swagger" not in spec:
        raise AppError(422, "invalid_spec", "Missing 'openapi' or 'swagger' version field")
    return spec


def _resolve(spec: dict, node: Any, depth: int = 0) -> Any:
    """Follow local $ref pointers (bounded, so recursive schemas cannot loop forever)."""
    while isinstance(node, dict) and "$ref" in node and depth < 8:
        ref = node["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/"):
            return {}
        target: Any = spec
        for part in ref[2:].split("/"):
            target = target.get(part.replace("~1", "/").replace("~0", "~"), {}) if isinstance(target, dict) else {}
        node, depth = target, depth + 1
    return node


def _example(spec: dict, schema: Any, depth: int = 0) -> Any:
    schema = _resolve(spec, schema)
    if not isinstance(schema, dict) or depth > 4:
        return None
    if "example" in schema:
        return schema["example"]
    if "default" in schema:
        return schema["default"]
    if schema.get("enum"):
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "object" or "properties" in schema:
        return {k: _example(spec, v, depth + 1) for k, v in (schema.get("properties") or {}).items()}
    if kind == "array":
        item = _example(spec, schema.get("items", {}), depth + 1)
        return [] if item is None else [item]
    return {"integer": 1, "number": 1.5, "boolean": True, "string": "string"}.get(kind)


def _param_value(spec: dict, param: dict) -> str:
    value = param.get("example")
    if value is None:
        value = _example(spec, param.get("schema") or param)
    return str(value if value is not None else "1")


def extract_operations(spec: dict[str, Any]) -> list[ImportedOperation]:
    operations: list[ImportedOperation] = []
    for raw_path, item in spec["paths"].items():
        item = _resolve(spec, item)
        if not isinstance(item, dict):
            continue
        shared = [_resolve(spec, p) for p in item.get("parameters", [])]
        for method in HTTP_METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            params = shared + [_resolve(spec, p) for p in op.get("parameters", [])]
            path, query, headers = raw_path, {}, {}
            body, body_type = None, "none"
            for p in params:
                if not isinstance(p, dict):
                    continue
                location, name = p.get("in"), p.get("name", "")
                if location == "path":
                    path = path.replace("{" + name + "}", _param_value(spec, p))
                elif location == "query" and p.get("required"):
                    query[name] = _param_value(spec, p)
                elif location == "header" and p.get("required"):
                    headers[name] = _param_value(spec, p)
                elif location == "body":  # Swagger 2.0
                    body, body_type = _example(spec, p.get("schema")), "json"

            request_body = _resolve(spec, op.get("requestBody") or {})
            content = request_body.get("content", {}) if isinstance(request_body, dict) else {}
            json_media = next((m for t, m in content.items() if "json" in t), None)
            if json_media is not None:
                body_type = "json"
                body = json_media.get("example")
                if body is None and json_media.get("examples"):
                    first = next(iter(json_media["examples"].values()), {})
                    body = _resolve(spec, first).get("value")
                if body is None:
                    body = _example(spec, json_media.get("schema"))

            success = sorted(int(code) for code in (op.get("responses") or {}) if str(code).isdigit() and 200 <= int(code) < 300)
            name = op.get("operationId") or op.get("summary") or f"{method.upper()} {raw_path}"
            operations.append(
                ImportedOperation(
                    name=str(name)[:200],
                    method=method.upper(),
                    path=path,
                    template_path=raw_path,
                    description=str(op.get("description") or op.get("summary") or "")[:2000],
                    query_params=query,
                    headers=headers,
                    body=body,
                    body_type=body_type,
                    expected_status=success[0] if success else 200,
                )
            )
            if len(operations) > MAX_OPERATIONS:
                raise AppError(422, "spec_too_large", f"The document has more than {MAX_OPERATIONS} operations")
    if not operations:
        raise AppError(422, "empty_spec", "The document contains no operations")
    return operations


def spec_title_and_servers(spec: dict[str, Any]) -> tuple[str, list[str]]:
    title = str((spec.get("info") or {}).get("title") or "Imported API")
    servers = [s.get("url", "") for s in spec.get("servers", []) if isinstance(s, dict)]
    if not servers and spec.get("host"):  # Swagger 2.0
        scheme = (spec.get("schemes") or ["https"])[0]
        servers = [f"{scheme}://{spec['host']}{spec.get('basePath', '')}"]
    return title, servers


def dumps(value: Any) -> str:  # tiny helper used by tests
    return json.dumps(value)
