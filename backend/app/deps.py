"""Reusable FastAPI dependencies: authentication and project-level authorization."""

from dataclasses import dataclass

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import AppError
from app.models import ApiKey, Project, ProjectMember, User
from app.security import decode_access_token, hash_api_key
from app.utils import utcnow

bearer_scheme = HTTPBearer(auto_error=False)

ROLE_RANK = {"viewer": 1, "editor": 2, "owner": 3}


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise AppError(401, "not_authenticated", "Authentication required")
    payload = decode_access_token(credentials.credentials)
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise AppError(401, "invalid_token", "Invalid authentication token")
    return user


@dataclass
class ProjectContext:
    project: Project
    role: str
    user: User


def project_access(min_role: str):
    """Build a dependency that loads the project and enforces a minimum role.

    Non-members get 404 (not 403) so project existence is not leaked.
    """

    def dependency(
        project_id: int,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> ProjectContext:
        member = db.scalar(
            select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id)
        )
        project = db.get(Project, project_id) if member else None
        if member is None or project is None:
            raise AppError(404, "project_not_found", "Project not found")
        if ROLE_RANK[member.role] < ROLE_RANK[min_role]:
            raise AppError(403, "forbidden", f"This action requires the '{min_role}' role")
        return ProjectContext(project=project, role=member.role, user=user)

    return dependency


viewer_access = project_access("viewer")
editor_access = project_access("editor")
owner_access = project_access("owner")


def get_api_key_project(
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Project:
    """Authenticate CI requests via the X-API-Key header."""
    if not x_api_key:
        raise AppError(401, "missing_api_key", "X-API-Key header is required")
    key = db.scalar(select(ApiKey).where(ApiKey.key_hash == hash_api_key(x_api_key)))
    if key is None or key.revoked:
        raise AppError(401, "invalid_api_key", "Invalid or revoked API key")
    key.last_used_at = utcnow()
    db.commit()
    project = db.get(Project, key.project_id)
    if project is None:  # pragma: no cover - FK cascade makes this unreachable
        raise AppError(401, "invalid_api_key", "Invalid or revoked API key")
    return project
