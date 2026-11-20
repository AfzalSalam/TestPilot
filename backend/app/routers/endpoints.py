from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import ProjectContext, editor_access, viewer_access
from app.errors import AppError
from app.models import ApiEndpoint
from app.routers.common import get_in_project
from app.schemas import EndpointIn, EndpointOut, EndpointUpdate

router = APIRouter(prefix="/projects/{project_id}/endpoints", tags=["Endpoints"])


def _conflict() -> AppError:
    return AppError(409, "endpoint_exists", "An endpoint with this method and path already exists")


@router.get("", response_model=list[EndpointOut], summary="List registered endpoints")
def list_endpoints(ctx: ProjectContext = Depends(viewer_access), db: Session = Depends(get_db)):
    return db.scalars(select(ApiEndpoint).where(ApiEndpoint.project_id == ctx.project.id).order_by(ApiEndpoint.path, ApiEndpoint.method)).all()


@router.post("", response_model=EndpointOut, status_code=201, summary="Register an endpoint")
def create_endpoint(body: EndpointIn, ctx: ProjectContext = Depends(editor_access), db: Session = Depends(get_db)):
    endpoint = ApiEndpoint(project_id=ctx.project.id, **body.model_dump())
    db.add(endpoint)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _conflict() from None
    return endpoint


@router.get("/{endpoint_id}", response_model=EndpointOut, summary="Get an endpoint")
def get_endpoint(endpoint_id: int, ctx: ProjectContext = Depends(viewer_access), db: Session = Depends(get_db)):
    return get_in_project(db, ApiEndpoint, endpoint_id, ctx.project.id, "endpoint")


@router.patch("/{endpoint_id}", response_model=EndpointOut, summary="Update an endpoint")
def update_endpoint(endpoint_id: int, body: EndpointUpdate, ctx: ProjectContext = Depends(editor_access), db: Session = Depends(get_db)):
    endpoint = get_in_project(db, ApiEndpoint, endpoint_id, ctx.project.id, "endpoint")
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(endpoint, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _conflict() from None
    return endpoint


@router.delete("/{endpoint_id}", status_code=204, summary="Delete an endpoint")
def delete_endpoint(endpoint_id: int, ctx: ProjectContext = Depends(editor_access), db: Session = Depends(get_db)):
    db.delete(get_in_project(db, ApiEndpoint, endpoint_id, ctx.project.id, "endpoint"))
    db.commit()
