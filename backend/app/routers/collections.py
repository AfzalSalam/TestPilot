from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import ProjectContext, editor_access, viewer_access
from app.errors import AppError
from app.models import Collection, TestCase
from app.routers.common import get_in_project
from app.schemas import CollectionIn, CollectionOut, CollectionUpdate

router = APIRouter(prefix="/projects/{project_id}/collections", tags=["Collections"])


def _out(db: Session, collection: Collection) -> CollectionOut:
    out = CollectionOut.model_validate(collection)
    out.test_case_count = db.scalar(select(func.count()).select_from(TestCase).where(TestCase.collection_id == collection.id)) or 0
    return out


@router.get("", response_model=list[CollectionOut], summary="List collections")
def list_collections(ctx: ProjectContext = Depends(viewer_access), db: Session = Depends(get_db)):
    rows = db.scalars(select(Collection).where(Collection.project_id == ctx.project.id).order_by(Collection.name)).all()
    return [_out(db, c) for c in rows]


@router.post("", response_model=CollectionOut, status_code=201, summary="Create a collection")
def create_collection(body: CollectionIn, ctx: ProjectContext = Depends(editor_access), db: Session = Depends(get_db)):
    collection = Collection(project_id=ctx.project.id, **body.model_dump())
    db.add(collection)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "collection_exists", "A collection with this name already exists") from None
    return _out(db, collection)


@router.get("/{collection_id}", response_model=CollectionOut, summary="Get a collection")
def get_collection(collection_id: int, ctx: ProjectContext = Depends(viewer_access), db: Session = Depends(get_db)):
    return _out(db, get_in_project(db, Collection, collection_id, ctx.project.id, "collection"))


@router.patch("/{collection_id}", response_model=CollectionOut, summary="Update a collection")
def update_collection(collection_id: int, body: CollectionUpdate, ctx: ProjectContext = Depends(editor_access), db: Session = Depends(get_db)):
    collection = get_in_project(db, Collection, collection_id, ctx.project.id, "collection")
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(collection, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "collection_exists", "A collection with this name already exists") from None
    return _out(db, collection)


@router.delete("/{collection_id}", status_code=204, summary="Delete a collection (its tests are kept, uncategorised)")
def delete_collection(collection_id: int, ctx: ProjectContext = Depends(editor_access), db: Session = Depends(get_db)):
    db.delete(get_in_project(db, Collection, collection_id, ctx.project.id, "collection"))
    db.commit()
