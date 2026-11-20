from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import ProjectContext, editor_access, viewer_access
from app.models import TestCase
from app.ratelimit import check_rate
from app.routers.common import check_related, get_in_project, latest_results, merge_masked, test_case_out
from app.schemas import ExecuteOut, TestCaseIn, TestCaseOut, TestCaseUpdate
from app.services.engine import TestCaseSpec, execute_test_case
from app.services.runner import spec_from_model

router = APIRouter(prefix="/projects/{project_id}/test-cases", tags=["Test cases"])


def _run_now(ctx: ProjectContext, spec: TestCaseSpec) -> ExecuteOut:
    settings = get_settings()
    check_rate("execute", str(ctx.user.id), settings.rate_limit_execute_per_minute)
    result = execute_test_case(
        spec,
        base_url=ctx.project.base_url,
        variables=dict(ctx.project.variables or {}),
        settings=settings,
        default_timeout_s=ctx.project.default_timeout_s,
    )
    return ExecuteOut(**{k: result[k] for k in ExecuteOut.model_fields})


@router.get("", response_model=list[TestCaseOut], summary="List test cases")
def list_test_cases(
    collection_id: int | None = None,
    q: str | None = Query(default=None, max_length=100, description="Search in name and path"),
    enabled: bool | None = None,
    ctx: ProjectContext = Depends(viewer_access),
    db: Session = Depends(get_db),
):
    stmt = select(TestCase).where(TestCase.project_id == ctx.project.id)
    if collection_id is not None:
        stmt = stmt.where(TestCase.collection_id == collection_id)
    if enabled is not None:
        stmt = stmt.where(TestCase.enabled.is_(enabled))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(TestCase.name.ilike(like) | TestCase.path.ilike(like))
    cases = db.scalars(stmt.order_by(TestCase.id)).all()
    latest = latest_results(db, [c.id for c in cases])
    return [test_case_out(c, latest.get(c.id)) for c in cases]


@router.post("", response_model=TestCaseOut, status_code=201, summary="Create a test case")
def create_test_case(body: TestCaseIn, ctx: ProjectContext = Depends(editor_access), db: Session = Depends(get_db)):
    check_related(db, ctx.project.id, body.collection_id, body.endpoint_id)
    data = body.model_dump()
    data["assertions"] = [a for a in body.model_dump(exclude_none=True)["assertions"]]
    tc = TestCase(project_id=ctx.project.id, **data)
    db.add(tc)
    db.commit()
    return test_case_out(tc)


@router.post("/execute", response_model=ExecuteOut, summary="Try an unsaved test case (nothing is stored)")
def execute_unsaved(body: TestCaseIn, ctx: ProjectContext = Depends(editor_access), db: Session = Depends(get_db)):
    data = body.model_dump(exclude_none=True)
    spec = TestCaseSpec(
        id=None,
        name=body.name,
        method=body.method,
        path=body.path,
        headers=body.headers,
        query_params=body.query_params,
        body_type=body.body_type,
        body=body.body,
        auth_type=body.auth_type,
        auth_config=body.auth_config,
        expected_status=body.expected_status,
        assertions=data.get("assertions", []),
        timeout_s=body.timeout_s,
        follow_redirects=body.follow_redirects,
    )
    return _run_now(ctx, spec)


@router.get("/{test_case_id}", response_model=TestCaseOut, summary="Get a test case")
def get_test_case(test_case_id: int, ctx: ProjectContext = Depends(viewer_access), db: Session = Depends(get_db)):
    tc = get_in_project(db, TestCase, test_case_id, ctx.project.id, "test_case")
    return test_case_out(tc, latest_results(db, [tc.id]).get(tc.id))


@router.patch("/{test_case_id}", response_model=TestCaseOut, summary="Update a test case")
def update_test_case(test_case_id: int, body: TestCaseUpdate, ctx: ProjectContext = Depends(editor_access), db: Session = Depends(get_db)):
    tc = get_in_project(db, TestCase, test_case_id, ctx.project.id, "test_case")
    changes = body.model_dump(exclude_unset=True)
    check_related(db, ctx.project.id, changes.get("collection_id"), changes.get("endpoint_id"))
    if changes.get("auth_config") is not None:
        changes["auth_config"] = merge_masked(changes["auth_config"], tc.auth_config)
    if "assertions" in changes and changes["assertions"] is not None:
        changes["assertions"] = body.model_dump(exclude_unset=True, exclude_none=True)["assertions"]
    for key, value in changes.items():
        if value is None and key not in ("collection_id", "endpoint_id", "body", "timeout_s"):
            continue  # null on a non-nullable field means "leave unchanged"
        setattr(tc, key, value)
    if tc.body_type == "none":
        tc.body = None
    db.commit()
    return test_case_out(tc, latest_results(db, [tc.id]).get(tc.id))


@router.delete("/{test_case_id}", status_code=204, summary="Delete a test case")
def delete_test_case(test_case_id: int, ctx: ProjectContext = Depends(editor_access), db: Session = Depends(get_db)):
    db.delete(get_in_project(db, TestCase, test_case_id, ctx.project.id, "test_case"))
    db.commit()


@router.post("/{test_case_id}/duplicate", response_model=TestCaseOut, status_code=201, summary="Duplicate a test case")
def duplicate_test_case(test_case_id: int, ctx: ProjectContext = Depends(editor_access), db: Session = Depends(get_db)):
    src = get_in_project(db, TestCase, test_case_id, ctx.project.id, "test_case")
    clone = TestCase(
        **{c.name: getattr(src, c.name) for c in TestCase.__table__.columns if c.name not in ("id", "created_at", "updated_at")}
    )
    clone.name = f"{src.name} (copy)"[:200]
    db.add(clone)
    db.commit()
    return test_case_out(clone)


@router.post("/{test_case_id}/execute", response_model=ExecuteOut, summary="Execute a saved test case once (result is not stored)")
def execute_saved(test_case_id: int, ctx: ProjectContext = Depends(editor_access), db: Session = Depends(get_db)):
    tc = get_in_project(db, TestCase, test_case_id, ctx.project.id, "test_case")
    return _run_now(ctx, spec_from_model(tc))
