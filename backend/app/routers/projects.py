from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import ProjectContext, editor_access, get_current_user, owner_access, viewer_access
from app.errors import AppError
from app.models import ApiEndpoint, Collection, Project, ProjectMember, Run, TestCase, User
from app.routers.common import merge_masked
from app.schemas import (
    MASK,
    MemberIn,
    MemberOut,
    MemberUpdate,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    RunBrief,
)

router = APIRouter(prefix="/projects", tags=["Projects"])


def project_out(db: Session, project: Project, role: str) -> ProjectOut:
    def count(model) -> int:
        return db.scalar(select(func.count()).select_from(model).where(model.project_id == project.id)) or 0

    last = db.scalar(select(Run).where(Run.project_id == project.id).order_by(Run.id.desc()).limit(1))
    variables = project.variables or {}
    if role == "viewer":  # viewers can see variable names but never their values
        variables = {k: MASK for k in variables}
    return ProjectOut(
        id=project.id,
        name=project.name,
        description=project.description,
        base_url=project.base_url,
        default_timeout_s=project.default_timeout_s,
        variables=variables,
        role=role,
        created_at=project.created_at,
        test_case_count=count(TestCase),
        endpoint_count=count(ApiEndpoint),
        collection_count=count(Collection),
        run_count=count(Run),
        last_run=RunBrief.model_validate(last) if last else None,
    )


@router.get("", response_model=list[ProjectOut], summary="List projects you belong to")
def list_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Project, ProjectMember.role)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.user_id == user.id)
        .order_by(Project.created_at.desc())
    ).all()
    return [project_out(db, p, role) for p, role in rows]


@router.post("", response_model=ProjectOut, status_code=201, summary="Create a project")
def create_project(body: ProjectCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = Project(owner_id=user.id, **body.model_dump())
    db.add(project)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "project_exists", "You already have a project with this name") from None
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role="owner"))
    db.commit()
    return project_out(db, project, "owner")


@router.get("/{project_id}", response_model=ProjectOut, summary="Get a project")
def get_project(ctx: ProjectContext = Depends(viewer_access), db: Session = Depends(get_db)):
    return project_out(db, ctx.project, ctx.role)


@router.patch("/{project_id}", response_model=ProjectOut, summary="Update a project")
def update_project(body: ProjectUpdate, ctx: ProjectContext = Depends(editor_access), db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    if "variables" in data and data["variables"] is not None:
        data["variables"] = merge_masked(data["variables"], ctx.project.variables)
    for key, value in data.items():
        if value is not None:
            setattr(ctx.project, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "project_exists", "You already have a project with this name") from None
    return project_out(db, ctx.project, ctx.role)


@router.delete("/{project_id}", status_code=204, summary="Delete a project and all of its data")
def delete_project(ctx: ProjectContext = Depends(owner_access), db: Session = Depends(get_db)):
    db.delete(ctx.project)
    db.commit()


# ---------------------------------------------------------------- members (project-level access control)
def _member_out(member: ProjectMember, user: User) -> MemberOut:
    return MemberOut(user_id=user.id, email=user.email, full_name=user.full_name, role=member.role)


@router.get("/{project_id}/members", response_model=list[MemberOut], summary="List project members")
def list_members(ctx: ProjectContext = Depends(viewer_access), db: Session = Depends(get_db)):
    rows = db.execute(
        select(ProjectMember, User)
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id == ctx.project.id)
        .order_by(ProjectMember.id)
    ).all()
    return [_member_out(m, u) for m, u in rows]


@router.post("/{project_id}/members", response_model=MemberOut, status_code=201, summary="Add a member by email")
def add_member(body: MemberIn, ctx: ProjectContext = Depends(owner_access), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email))
    if user is None:
        raise AppError(404, "user_not_found", "No registered user has that email address")
    if db.scalar(select(ProjectMember).where(ProjectMember.project_id == ctx.project.id, ProjectMember.user_id == user.id)):
        raise AppError(409, "already_member", "That user is already a member of this project")
    member = ProjectMember(project_id=ctx.project.id, user_id=user.id, role=body.role)
    db.add(member)
    db.commit()
    return _member_out(member, user)


def _get_member(db: Session, project_id: int, user_id: int) -> ProjectMember:
    member = db.scalar(select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id))
    if member is None:
        raise AppError(404, "member_not_found", "Member not found")
    if member.role == "owner":
        raise AppError(400, "owner_immutable", "The project owner cannot be changed or removed")
    return member


@router.patch("/{project_id}/members/{user_id}", response_model=MemberOut, summary="Change a member's role")
def update_member(user_id: int, body: MemberUpdate, ctx: ProjectContext = Depends(owner_access), db: Session = Depends(get_db)):
    member = _get_member(db, ctx.project.id, user_id)
    member.role = body.role
    db.commit()
    return _member_out(member, db.get(User, user_id))


@router.delete("/{project_id}/members/{user_id}", status_code=204, summary="Remove a member")
def remove_member(user_id: int, ctx: ProjectContext = Depends(owner_access), db: Session = Depends(get_db)):
    db.delete(_get_member(db, ctx.project.id, user_id))
    db.commit()
