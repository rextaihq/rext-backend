from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.api.middleware.exceptions import ResourceNotFoundException, RextAuthorizationException
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.services.workspace_service import WorkspaceService

# The seeded workspace roles (scripts/seed_permissions.py): the owner at level 60, the
# level delete_workspace requires; an editor below it. An empty database gets them here.
ROLE_LEVELS = {"workspace_owner": 60, "editor": 30}


async def _role(db, name: str) -> Role:
    role = (await db.execute(select(Role).where(Role.name == name))).scalar_one_or_none()
    if role is None:
        role = Role(
            name=name,
            display_name=name.replace("_", " ").title(),
            hierarchy_level=ROLE_LEVELS[name],
            is_workspace_role=True,
        )
        db.add(role)
        await db.flush()
    return role


def _user(name: str) -> Users:
    return Users(
        id=uuid4(),
        email=f"{name.lower().replace(' ', '-')}-{uuid4().hex[:8]}@example.com",
        full_name=name,
        status="active",
        email_verified=True,
    )


def _workspace(owner: Users, name: str) -> WorkspaceModel:
    return WorkspaceModel(
        id=uuid4(),
        slug=f"{name.lower().replace(' ', '-')}-{uuid4().hex[:8]}",
        name=name,
        timezone="UTC",
        user_id=owner.id,
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_owner_can_delete_workspace(db_session):
    """Test that a workspace owner can successfully delete their workspace."""
    # Arrange
    user = _user("Owner User")
    db_session.add(user)
    workspace = _workspace(user, "Owner Workspace")
    db_session.add(workspace)
    await db_session.flush()

    role = await _role(db_session, "workspace_owner")
    db_session.add(
        UserRole(user_id=user.id, role_id=role.id, workspace_id=workspace.id, is_primary=True)
    )
    db_session.add(
        WorkspaceMembers(id=uuid4(), user_id=user.id, workspace_id=workspace.id, status="active")
    )
    await db_session.flush()

    # Act
    service = WorkspaceService(db_session)
    await service.delete_workspace(workspace.id, user.id)
    await db_session.flush()

    # Assert: soft deleted, by the owner
    result = await db_session.execute(
        select(WorkspaceModel).where(WorkspaceModel.id == workspace.id)
    )
    deleted_workspace = result.scalar_one()
    assert deleted_workspace.deleted_at is not None
    assert deleted_workspace.deleted_by == user.id


@pytest.mark.asyncio
async def test_non_owner_cannot_delete_workspace(db_session):
    """Test that a non-owner (e.g. editor) cannot delete the workspace."""
    # Arrange
    owner = _user("Real Owner")
    editor = _user("Editor User")
    db_session.add_all([owner, editor])
    workspace = _workspace(owner, "Shared Workspace")
    db_session.add(workspace)
    await db_session.flush()

    editor_role = await _role(db_session, "editor")
    db_session.add(
        UserRole(
            user_id=editor.id, role_id=editor_role.id, workspace_id=workspace.id, is_primary=True
        )
    )
    db_session.add(
        WorkspaceMembers(id=uuid4(), user_id=editor.id, workspace_id=workspace.id, status="active")
    )
    await db_session.flush()

    # Act & Assert
    service = WorkspaceService(db_session)
    with pytest.raises(RextAuthorizationException) as exc:
        await service.delete_workspace(workspace.id, editor.id)
    assert "Only workspace owners can perform this action" in str(exc.value)

    # Verify NOT deleted
    result = await db_session.execute(
        select(WorkspaceModel).where(WorkspaceModel.id == workspace.id)
    )
    assert result.scalar_one().deleted_at is None


@pytest.mark.asyncio
async def test_non_member_cannot_delete_workspace(db_session):
    """Test that a non-member cannot delete the workspace."""
    # Arrange
    owner = _user("Owner User")
    stranger = _user("Stranger User")
    db_session.add_all([owner, stranger])
    workspace = _workspace(owner, "Target Workspace")
    db_session.add(workspace)
    await db_session.flush()

    # Act & Assert: no role in the workspace at all
    service = WorkspaceService(db_session)
    with pytest.raises(RextAuthorizationException) as exc:
        await service.delete_workspace(workspace.id, stranger.id)
    assert "Only workspace owners can perform this action" in str(exc.value)

    # Verify NOT deleted
    result = await db_session.execute(
        select(WorkspaceModel).where(WorkspaceModel.id == workspace.id)
    )
    assert result.scalar_one().deleted_at is None
