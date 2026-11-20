"""Pydantic models: request validation and response shapes."""

import re
from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.services.assertions import ASSERTION_TYPES, OPERATORS

MASK = "********"
HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
BodyType = Literal["none", "json", "text", "form"]
AuthType = Literal["none", "bearer", "basic", "api_key_header", "api_key_query"]
Role = Literal["owner", "editor", "viewer"]
VARIABLE_NAME = re.compile(r"^[A-Za-z_][\w.\-]*$")

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


# ------------------------------------------------------------------ auth
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)

    @field_validator("email")
    @classmethod
    def lower(cls, v: str) -> str:
        return v.lower()


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)

    @field_validator("email")
    @classmethod
    def lower(cls, v: str) -> str:
        return v.lower()


class UserOut(ORM):
    id: int
    email: EmailStr
    full_name: str
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ------------------------------------------------------------------ projects
def _check_base_url(v: str) -> str:
    v = v.strip().rstrip("/")
    if v and not re.match(r"^https?://[^\s/$.?#].[^\s]*$", v, re.I):
        raise ValueError("base_url must start with http:// or https://")
    return v


def _check_variables(v: dict[str, str]) -> dict[str, str]:
    if len(v) > 100:
        raise ValueError("At most 100 variables are allowed")
    for name in v:
        if not VARIABLE_NAME.match(name):
            raise ValueError(f"Invalid variable name '{name}'")
    return v


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    base_url: str = Field(default="", max_length=500)
    default_timeout_s: float = Field(default=10.0, ge=0.5, le=60)
    variables: dict[str, str] = Field(default_factory=dict)

    @field_validator("base_url")
    @classmethod
    def _url(cls, v: str) -> str:
        return _check_base_url(v)

    @field_validator("variables")
    @classmethod
    def _vars(cls, v: dict[str, str]) -> dict[str, str]:
        return _check_variables(v)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    base_url: str | None = Field(default=None, max_length=500)
    default_timeout_s: float | None = Field(default=None, ge=0.5, le=60)
    variables: dict[str, str] | None = None

    @field_validator("base_url")
    @classmethod
    def _url(cls, v):
        return None if v is None else _check_base_url(v)

    @field_validator("variables")
    @classmethod
    def _vars(cls, v):
        return None if v is None else _check_variables(v)


class RunBrief(ORM):
    id: int
    status: str
    total: int
    passed: int
    failed: int
    errored: int
    created_at: datetime
    finished_at: datetime | None
    regression_summary: dict[str, Any] | None


class ProjectOut(BaseModel):
    id: int
    name: str
    description: str
    base_url: str
    default_timeout_s: float
    variables: dict[str, str]
    role: Role
    created_at: datetime
    test_case_count: int = 0
    endpoint_count: int = 0
    collection_count: int = 0
    run_count: int = 0
    last_run: RunBrief | None = None


class MemberIn(BaseModel):
    email: EmailStr
    role: Literal["editor", "viewer"] = "viewer"

    @field_validator("email")
    @classmethod
    def lower(cls, v: str) -> str:
        return v.lower()


class MemberUpdate(BaseModel):
    role: Literal["editor", "viewer"]


class MemberOut(BaseModel):
    user_id: int
    email: EmailStr
    full_name: str
    role: Role


# ------------------------------------------------------------------ endpoints & collections
class EndpointIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    method: HttpMethod = "GET"
    path: str = Field(min_length=1, max_length=2000)
    description: str = Field(default="", max_length=2000)

    @field_validator("path")
    @classmethod
    def path_form(cls, v: str) -> str:
        v = v.strip()
        if not (v.startswith("/") or re.match(r"^https?://", v, re.I)):
            raise ValueError("path must start with '/' or be an absolute http(s) URL")
        return v


class EndpointUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    method: HttpMethod | None = None
    path: str | None = Field(default=None, min_length=1, max_length=2000)
    description: str | None = Field(default=None, max_length=2000)


class EndpointOut(ORM):
    id: int
    project_id: int
    name: str
    method: str
    path: str
    description: str
    source: str
    created_at: datetime


class CollectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)


class CollectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class CollectionOut(ORM):
    id: int
    project_id: int
    name: str
    description: str
    created_at: datetime
    test_case_count: int = 0


# ------------------------------------------------------------------ test cases
class AssertionIn(BaseModel):
    type: Literal["json_path", "header", "body_contains", "response_time"]
    path: str | None = Field(default=None, max_length=300)
    name: str | None = Field(default=None, max_length=200)
    operator: str = "eq"
    value: Any = None
    max_ms: float | None = Field(default=None, gt=0, le=600_000)

    @model_validator(mode="after")
    def check(self):
        if self.type not in ASSERTION_TYPES:  # pragma: no cover - Literal already guards this
            raise ValueError("Unknown assertion type")
        if self.type in ("json_path", "header") and self.operator not in OPERATORS:
            raise ValueError(f"Unknown operator '{self.operator}'")
        if self.type == "json_path" and not self.path:
            raise ValueError("json_path assertions need a 'path'")
        if self.type == "header" and not self.name:
            raise ValueError("header assertions need a header 'name'")
        if self.type == "response_time" and self.max_ms is None:
            raise ValueError("response_time assertions need 'max_ms'")
        if self.type == "body_contains" and self.value in (None, ""):
            raise ValueError("body_contains assertions need a 'value'")
        return self


def _check_kv(v: dict[str, str]) -> dict[str, str]:
    if len(v) > 50:
        raise ValueError("At most 50 entries are allowed")
    return {str(k).strip(): str(val) for k, val in v.items() if str(k).strip()}


class TestCaseIn(BaseModel):
    __test__ = False

    name: str = Field(min_length=1, max_length=200)
    method: HttpMethod = "GET"
    path: str = Field(min_length=1, max_length=2000)
    collection_id: int | None = None
    endpoint_id: int | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    query_params: dict[str, str] = Field(default_factory=dict)
    body_type: BodyType = "none"
    body: Any = None
    auth_type: AuthType = "none"
    auth_config: dict[str, str] = Field(default_factory=dict)
    expected_status: int = Field(default=200, ge=100, le=599)
    assertions: list[AssertionIn] = Field(default_factory=list, max_length=50)
    timeout_s: float | None = Field(default=None, ge=0.5, le=60)
    follow_redirects: bool = True
    enabled: bool = True

    @field_validator("headers", "query_params")
    @classmethod
    def _kv(cls, v: dict[str, str]) -> dict[str, str]:
        return _check_kv(v)

    @model_validator(mode="after")
    def check_body(self):
        if self.body_type == "form" and not isinstance(self.body, dict):
            raise ValueError("form bodies must be an object of fields")
        if self.body_type == "none":
            self.body = None
        return self


class TestCaseUpdate(BaseModel):
    __test__ = False

    name: str | None = Field(default=None, min_length=1, max_length=200)
    method: HttpMethod | None = None
    path: str | None = Field(default=None, min_length=1, max_length=2000)
    collection_id: int | None = None
    endpoint_id: int | None = None
    headers: dict[str, str] | None = None
    query_params: dict[str, str] | None = None
    body_type: BodyType | None = None
    body: Any = None
    auth_type: AuthType | None = None
    auth_config: dict[str, str] | None = None
    expected_status: int | None = Field(default=None, ge=100, le=599)
    assertions: list[AssertionIn] | None = Field(default=None, max_length=50)
    timeout_s: float | None = Field(default=None, ge=0.5, le=60)
    follow_redirects: bool | None = None
    enabled: bool | None = None


class TestCaseOut(BaseModel):
    __test__ = False

    id: int
    project_id: int
    collection_id: int | None
    endpoint_id: int | None
    name: str
    method: str
    path: str
    headers: dict[str, str]
    query_params: dict[str, str]
    body_type: str
    body: Any
    auth_type: str
    auth_config: dict[str, str]  # values masked: credentials are write-only
    expected_status: int
    assertions: list[dict[str, Any]]
    timeout_s: float | None
    follow_redirects: bool
    enabled: bool
    created_at: datetime
    updated_at: datetime
    last_status: str | None = None
    last_response_time_ms: float | None = None


class ExecuteOut(BaseModel):
    status: str
    status_code: int | None
    response_time_ms: float | None
    response_size: int | None
    error_type: str | None
    error: str | None
    url: str
    assertion_results: list[dict[str, Any]]
    request_snapshot: dict[str, Any]
    response_headers: dict[str, str]
    response_body_preview: str | None


# ------------------------------------------------------------------ runs
class RunCreate(BaseModel):
    collection_id: int | None = None
    test_case_ids: list[int] | None = Field(default=None, max_length=500)
    concurrency: int | None = Field(default=None, ge=1, le=50)
    label: str = Field(default="", max_length=200)


class RunOut(BaseModel):
    id: int
    project_id: int
    project_name: str | None = None
    collection_id: int | None
    collection_name: str | None = None
    schedule_id: int | None
    trigger: str
    label: str
    status: str
    concurrency: int
    total: int
    passed: int
    failed: int
    errored: int
    progress: int
    error_message: str | None
    baseline_run_id: int | None
    regression_summary: dict[str, Any] | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: float | None


class ResultOut(ORM):
    id: int
    run_id: int
    test_case_id: int | None
    test_name: str
    method: str
    url: str
    status: str
    status_code: int | None
    response_time_ms: float | None
    response_size: int | None
    error_type: str | None
    error: str | None
    assertion_results: list[dict[str, Any]]
    request_snapshot: dict[str, Any]
    response_headers: dict[str, str]
    response_body_preview: str | None
    created_at: datetime


# ------------------------------------------------------------------ schedules, keys, import
class ScheduleIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    cron: str = Field(min_length=9, max_length=100)
    collection_id: int | None = None
    concurrency: int = Field(default=5, ge=1, le=50)
    enabled: bool = True


class ScheduleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    cron: str | None = Field(default=None, min_length=9, max_length=100)
    collection_id: int | None = None
    concurrency: int | None = Field(default=None, ge=1, le=50)
    enabled: bool | None = None


class ScheduleOut(BaseModel):
    id: int
    project_id: int
    collection_id: int | None
    collection_name: str | None = None
    name: str
    cron: str
    enabled: bool
    concurrency: int
    last_run_at: datetime | None
    next_run_at: datetime | None
    upcoming: list[datetime] = []
    created_at: datetime


class CronPreviewOut(BaseModel):
    valid: bool
    message: str | None = None
    upcoming: list[datetime] = []


class ApiKeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ApiKeyOut(ORM):
    id: int
    name: str
    prefix: str
    revoked: bool
    created_at: datetime
    last_used_at: datetime | None


class ApiKeyCreated(ApiKeyOut):
    key: str  # plaintext, returned exactly once


class ImportIn(BaseModel):
    spec_text: str = Field(min_length=2, max_length=2_000_000)
    create_test_cases: bool = True
    create_collection: bool = False
    collection_id: int | None = None
    set_base_url: bool = False


class ImportOut(BaseModel):
    title: str
    servers: list[str]
    endpoints_created: int
    endpoints_skipped: int
    test_cases_created: int
    test_cases_skipped: int
    collection_id: int | None
    base_url_updated: bool


class CIRunIn(BaseModel):
    collection_id: int | None = None
    concurrency: int | None = Field(default=None, ge=1, le=50)
    label: str = Field(default="", max_length=200)


class CIRunOut(BaseModel):
    id: int
    status: str
    finished: bool
    conclusion: Literal["pending", "success", "failure"]
    total: int
    passed: int
    failed: int
    errored: int
    regression: dict[str, Any] | None
    error_message: str | None
    url_path: str
