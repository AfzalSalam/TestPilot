from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import ProjectContext, owner_access
from app.models import ApiKey
from app.routers.common import get_in_project
from app.schemas import ApiKeyCreated, ApiKeyIn, ApiKeyOut
from app.security import generate_api_key

router = APIRouter(prefix="/projects/{project_id}/api-keys", tags=["CI integration"])


@router.get("", response_model=list[ApiKeyOut], summary="List CI API keys (hashes are never returned)")
def list_keys(ctx: ProjectContext = Depends(owner_access), db: Session = Depends(get_db)):
    return db.scalars(select(ApiKey).where(ApiKey.project_id == ctx.project.id).order_by(ApiKey.id.desc())).all()


@router.post("", response_model=ApiKeyCreated, status_code=201, summary="Create a CI API key (shown once)")
def create_key(body: ApiKeyIn, ctx: ProjectContext = Depends(owner_access), db: Session = Depends(get_db)):
    plaintext, prefix, key_hash = generate_api_key()
    key = ApiKey(project_id=ctx.project.id, name=body.name, prefix=prefix, key_hash=key_hash)
    db.add(key)
    db.commit()
    return ApiKeyCreated(**ApiKeyOut.model_validate(key).model_dump(), key=plaintext)


@router.delete("/{key_id}", status_code=204, summary="Revoke a CI API key")
def revoke_key(key_id: int, ctx: ProjectContext = Depends(owner_access), db: Session = Depends(get_db)):
    key = get_in_project(db, ApiKey, key_id, ctx.project.id, "api_key")
    key.revoked = True
    db.commit()
