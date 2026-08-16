import pytest
from pydantic import ValidationError

from app.schemas.auth import WorkspaceInvitationCreate, WorkspaceMemberRoleUpdate


def test_invitation_normalizes_email() -> None:
    payload = WorkspaceInvitationCreate(email="  ADMIN@EXAMPLE.COM  ", role="admin")
    assert payload.email == "admin@example.com"
    assert payload.role == "admin"


def test_invitation_accepts_member_role() -> None:
    payload = WorkspaceInvitationCreate(email="member@example.com", role="member")
    assert payload.role == "member"


def test_role_update_accepts_admin_and_member_only() -> None:
    assert WorkspaceMemberRoleUpdate(role="admin").role == "admin"
    assert WorkspaceMemberRoleUpdate(role="member").role == "member"

    with pytest.raises(ValidationError):
        WorkspaceMemberRoleUpdate(role="invalid")
