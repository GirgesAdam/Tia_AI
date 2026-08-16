from dataclasses import dataclass
from typing import Annotated, Callable
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import (
    WORKSPACE_ROLE_ADMIN,
    WORKSPACE_ROLE_MEMBER,
    WorkspaceMember,
)
from app.services.supabase_auth import SupabaseAuthError, VerifiedAuthIdentity, verify_access_token

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class WorkspaceAccess:
    user: User
    workspace: Workspace
    membership: WorkspaceMember


def _unauthorized(detail: str = "Authentication required.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_verified_identity(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> VerifiedAuthIdentity:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    try:
        return verify_access_token(credentials.credentials)
    except SupabaseAuthError as exc:
        raise _unauthorized("Invalid or expired access token.") from exc


def get_current_user(
    identity: Annotated[VerifiedAuthIdentity, Depends(get_verified_identity)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    user = db.scalar(select(User).where(User.auth_user_id == identity.auth_user_id))
    changed = False

    if user is None:
        user = db.scalar(select(User).where(User.email == identity.email))
        if user is None:
            user = User(
                auth_user_id=identity.auth_user_id,
                email=identity.email,
                full_name=identity.full_name,
            )
            db.add(user)
            changed = True
        elif user.auth_user_id is None:
            user.auth_user_id = identity.auth_user_id
            changed = True
        elif user.auth_user_id != identity.auth_user_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This email is already linked to another authentication identity.",
            )

    if user.email != identity.email:
        user.email = identity.email
        changed = True
    if identity.full_name and user.full_name != identity.full_name:
        user.full_name = identity.full_name
        changed = True

    if changed:
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Could not synchronize the authenticated user profile.",
            ) from exc
        db.refresh(user)

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive.",
        )
    return user


def get_workspace_access(
    x_workspace_id: Annotated[UUID, Header(alias="X-Workspace-ID")],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> WorkspaceAccess:
    membership = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == x_workspace_id,
            WorkspaceMember.user_id == user.id,
            WorkspaceMember.is_active.is_(True),
        )
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this workspace.",
        )

    workspace = db.scalar(
        select(Workspace).where(
            Workspace.id == x_workspace_id,
            Workspace.is_active.is_(True),
        )
    )
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found or inactive.",
        )

    return WorkspaceAccess(user=user, workspace=workspace, membership=membership)


def require_workspace_roles(*allowed_roles: str) -> Callable[..., WorkspaceAccess]:
    allowed = frozenset(allowed_roles)

    def dependency(
        access: Annotated[WorkspaceAccess, Depends(get_workspace_access)],
    ) -> WorkspaceAccess:
        if access.membership.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your workspace role does not allow this action.",
            )
        return access

    return dependency


get_workspace_reader = require_workspace_roles(
    WORKSPACE_ROLE_ADMIN,
    WORKSPACE_ROLE_MEMBER,
)
get_workspace_admin = require_workspace_roles(WORKSPACE_ROLE_ADMIN)


def get_current_workspace(
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
) -> Workspace:
    return access.workspace


def get_manageable_workspace(
    access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
) -> Workspace:
    return access.workspace
