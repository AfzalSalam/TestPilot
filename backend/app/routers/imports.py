from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import ProjectContext, editor_access
from app.models import ApiEndpoint, Collection, TestCase
from app.routers.common import check_related
from app.schemas import ImportIn, ImportOut
from app.services.openapi_import import extract_operations, parse_spec, spec_title_and_servers

router = APIRouter(prefix="/projects/{project_id}/import", tags=["OpenAPI import"])


@router.post("/openapi", response_model=ImportOut, summary="Import endpoints and starter tests from an OpenAPI/Swagger document")
def import_openapi(body: ImportIn, ctx: ProjectContext = Depends(editor_access), db: Session = Depends(get_db)):
    spec = parse_spec(body.spec_text)
    operations = extract_operations(spec)
    title, servers = spec_title_and_servers(spec)

    collection_id = body.collection_id
    check_related(db, ctx.project.id, collection_id)
    if body.create_test_cases and body.create_collection and collection_id is None:
        existing = db.scalar(select(Collection).where(Collection.project_id == ctx.project.id, Collection.name == title[:120]))
        if existing is None:
            existing = Collection(project_id=ctx.project.id, name=title[:120], description="Imported from OpenAPI")
            db.add(existing)
            db.flush()
        collection_id = existing.id

    known_endpoints = {
        (e.method, e.path): e for e in db.scalars(select(ApiEndpoint).where(ApiEndpoint.project_id == ctx.project.id)).all()
    }
    known_tests = {
        (t.method, t.path) for t in db.scalars(select(TestCase).where(TestCase.project_id == ctx.project.id)).all()
    }
    ep_created = ep_skipped = tc_created = tc_skipped = 0
    for op in operations:
        endpoint = known_endpoints.get((op.method, op.template_path))
        if endpoint is None:
            endpoint = ApiEndpoint(
                project_id=ctx.project.id, name=op.name, method=op.method, path=op.template_path,
                description=op.description, source="openapi",
            )  # fmt: skip
            db.add(endpoint)
            db.flush()
            known_endpoints[(op.method, op.template_path)] = endpoint
            ep_created += 1
        else:
            ep_skipped += 1
        if not body.create_test_cases:
            continue
        if (op.method, op.path) in known_tests:
            tc_skipped += 1
            continue
        db.add(
            TestCase(
                project_id=ctx.project.id, collection_id=collection_id, endpoint_id=endpoint.id,
                name=op.name, method=op.method, path=op.path, headers=op.headers,
                query_params=op.query_params, body_type=op.body_type, body=op.body,
                expected_status=op.expected_status,
                assertions=[{"type": "response_time", "max_ms": 2000}],
            )
        )  # fmt: skip
        known_tests.add((op.method, op.path))
        tc_created += 1

    base_url_updated = False
    if body.set_base_url and servers and servers[0].startswith(("http://", "https://")):
        ctx.project.base_url = servers[0].rstrip("/")
        base_url_updated = True
    db.commit()
    return ImportOut(
        title=title, servers=servers, endpoints_created=ep_created, endpoints_skipped=ep_skipped,
        test_cases_created=tc_created, test_cases_skipped=tc_skipped, collection_id=collection_id,
        base_url_updated=base_url_updated,
    )  # fmt: skip
