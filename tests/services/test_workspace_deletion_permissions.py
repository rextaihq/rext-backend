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


@pytest.mark.asyncio
async def test_owner_can_delete_workspace(db_session):
    """Test that a workspace owner can successfully delete their workspace."""
    # Arrange
    user = Users(
        id=uuid4(),
        email="owner@example.com",
        username="owner",
        first_name="Owner",
        last_name="User",
        password="hashed_password",
        status="active",
        email_verified=True,
    )
    db_session.add(user)

    workspace = WorkspaceModel(
        id=uuid4(),
        slug="owner-workspace",
        title="Owner Workspace",
        name="Owner Workspace",  # Providing name as well since model has it
        timezone="UTC",
        user_id=user.id,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(workspace)
    await db_session.flush()

    # Add owner role
    role = Role(
        id=uuid4(), name="workspace_owner", display_name="Workspace Owner", is_workspace_role=True
    )
    db_session.add(role)
    await db_session.flush()

    # Assign role to user
    user_role = UserRole(
        user_id=user.id, role_id=role.id, workspace_id=workspace.id, is_primary=True
    )
    db_session.add(user_role)

    # Add membership (needed for _ensure_membership in higher levels, though delete calls generic get)
    membership = WorkspaceMembers(
        id=uuid4(), user_id=user.id, workspace_id=workspace.id, status="active"
    )
    db_session.add(membership)
    await db_session.commit()

    # Act
    service = WorkspaceService(db_session)
    await service.delete_workspace(workspace.id, user.id)

    # Assert
    # Verify soft delete
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
    owner = Users(
        id=uuid4(),
        email="realowner@example.com",
        username="realowner",
        first_name="Real",
        last_name="Owner",
    )
    editor = Users(
        id=uuid4(),
        email="editor@example.com",
        username="editor",
        first_name="Editor",
        last_name="User",
    )
    db_session.add_all([owner, editor])

    workspace = WorkspaceModel(
        id=uuid4(),
        slug="shared-workspace",
        title="Shared Workspace",
        name="Shared Workspace",
        timezone="UTC",
        user_id=owner.id,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(workspace)
    await db_session.flush()

    # Add non-owner role
    editor_role = Role(id=uuid4(), name="editor", display_name="Editor", is_workspace_role=True)
    db_session.add(editor_role)
    await db_session.flush()

    # Assign editor role to user
    user_role = UserRole(
        user_id=editor.id, role_id=editor_role.id, workspace_id=workspace.id, is_primary=True
    )
    db_session.add(user_role)

    membership = WorkspaceMembers(
        id=uuid4(), user_id=editor.id, workspace_id=workspace.id, status="active"
    )
    db_session.add(membership)
    await db_session.commit()

    # Act & Assert
    service = WorkspaceService(db_session)

    with pytest.raises(RextAuthorizationException) as exc:
        await service.delete_workspace(workspace.id, editor.id)

    assert "Only workspace owners can perform this action" in str(exc.value)

    # Verify NOT deleted
    result = await db_session.execute(
        select(WorkspaceModel).where(WorkspaceModel.id == workspace.id)
    )
    ws = result.scalar_one()
    assert ws.deleted_at is None


@pytest.mark.asyncio
async def test_non_member_cannot_delete_workspace(db_session):
    """Test that a non-member cannot delete the workspace."""
    # Arrange
    owner = Users(
        id=uuid4(),
        email="owner@example.com",
        username="owner",
        first_name="Owner",
        last_name="User",
    )
    stranger = Users(
        id=uuid4(),
        email="stranger@example.com",
        username="stranger",
        first_name="Stranger",
        last_name="User",
    )
    db_session.add_all([owner, stranger])

    workspace = WorkspaceModel(
        id=uuid4(),
        slug="target-workspace",
        title="Target Workspace",
        name="Target Workspace",
        timezone="UTC",
        user_id=owner.id,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(workspace)
    await db_session.commit()

    # Act & Assert
    service = WorkspaceService(db_session)

    # Depending on implementation details, this might raise Forbidden or some other error.
    # verify_user_is_workspace_owner checks UserRole which won't exist.

    with pytest.raises(RextAuthorizationException) as exc:
        await service.delete_workspace(workspace.id, stranger.id)

    assert "Only workspace owners can perform this action" in str(exc.value)

    # Verify NOT deleted
    result = await db_session.execute(
        select(WorkspaceModel).where(WorkspaceModel.id == workspace.id)
    )
    ws = result.scalar_one()
    assert ws.deleted_at is None
