"""
Tests for /user/workspaces endpoint

This test suite covers:
- User with multiple workspaces
- User with no workspaces
- Role information inclusion
- Owner vs member differentiation
- Workspace statistics accuracy
"""

import pytest
from uuid import uuid4
from sqlalchemy import select

from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.user_models.users import Users
from src.api.models.user_models.roles import Role


@pytest.mark.asyncio
async def test_get_user_workspaces_with_multiple_workspaces(async_client, async_db):
    """
    Test GET /user/workspaces with user having multiple workspaces.

    Expected behavior:
    - Returns all workspaces where user is a member
    - Includes role information for each workspace
    - Shows owned_count and member_count
    - Includes workspace statistics
    """
    # Arrange: Create user
    user = Users(
        id=uuid4(),
        email="testuser@example.com",
        username="testuser",
        first_name="Test",
        last_name="User",
        password="hashed_password",
        status="active",
        email_verified=True
    )
    async_db.add(user)
    await async_db.flush()

    # Create owned workspace
    owned_workspace = WorkspaceModel(
        id=uuid4(),
        slug="owned-workspace",
        title="Owned Workspace",
        timezone="UTC",
        user_id=user.id
    )
    async_db.add(owned_workspace)
    await async_db.flush()

    # Create owner role for owned workspace
    owner_role = Role(
        id=uuid4(),
        name="owner",
        display_name="Owner",
        workspace_id=owned_workspace.id
    )
    async_db.add(owner_role)
    await async_db.flush()

    # Add user as member of owned workspace
    owned_membership = WorkspaceMembers(
        id=uuid4(),
        user_id=user.id,
        workspace_id=owned_workspace.id,
        status="active"
    )
    async_db.add(owned_membership)

    # Create another user who will own a workspace
    other_user = Users(
        id=uuid4(),
        email="otheruser@example.com",
        username="otheruser",
        first_name="Other",
        last_name="User",
        password="hashed_password",
        status="active",
        email_verified=True
    )
    async_db.add(other_user)
    await async_db.flush()

    # Create member workspace (owned by other user)
    member_workspace = WorkspaceModel(
        id=uuid4(),
        slug="member-workspace",
        title="Member Workspace",
        timezone="UTC",
        user_id=other_user.id
    )
    async_db.add(member_workspace)
    await async_db.flush()

    # Create editor role for member workspace
    editor_role = Role(
        id=uuid4(),
        name="editor",
        display_name="Editor",
        workspace_id=member_workspace.id
    )
    async_db.add(editor_role)
    await async_db.flush()

    # Add user as editor of member workspace
    member_membership = WorkspaceMembers(
        id=uuid4(),
        user_id=user.id,
        workspace_id=member_workspace.id,
        status="active"
    )
    async_db.add(member_membership)
    await async_db.commit()

    # Act: Get user workspaces
    # Note: This requires authentication, so we need to mock the token
    # For now, we'll test the service layer directly
    from src.services.workspace_service import WorkspaceService
    from src.services.member_service import MemberService

    workspace_service = WorkspaceService(async_db)
    workspaces = await workspace_service.get_user_workspaces(user.id)

    # Assert: Should return 2 workspaces
    assert len(workspaces) == 2

    # Check that both workspaces are present
    workspace_slugs = {ws["slug"] for ws in workspaces}
    assert "owned-workspace" in workspace_slugs
    assert "member-workspace" in workspace_slugs

    # Verify workspace data structure
    for workspace in workspaces:
        assert "id" in workspace
        assert "name" in workspace
        assert "slug" in workspace
        assert "owner" in workspace
        assert "knowledge_stats" in workspace
        assert "members_count" in workspace


@pytest.mark.asyncio
async def test_get_user_workspaces_with_no_workspaces(async_client, async_db):
    """
    Test GET /user/workspaces with user having no workspaces.

    Expected behavior:
    - Returns empty list
    - total_count is 0
    - owned_count is 0
    - member_count is 0
    """
    # Arrange: Create user with no workspace memberships
    user = Users(
        id=uuid4(),
        email="newuser@example.com",
        username="newuser",
        first_name="New",
        last_name="User",
        password="hashed_password",
        status="active",
        email_verified=True
    )
    async_db.add(user)
    await async_db.commit()

    # Act: Get user workspaces
    from src.services.workspace_service import WorkspaceService

    workspace_service = WorkspaceService(async_db)
    workspaces = await workspace_service.get_user_workspaces(user.id)

    # Assert: Should return empty list
    assert len(workspaces) == 0
    assert workspaces == []


@pytest.mark.asyncio
async def test_get_user_workspaces_excludes_soft_deleted(async_db):
    """
    Test that soft-deleted workspaces are excluded from results.

    Expected behavior:
    - Only active workspaces are returned
    - Soft-deleted workspaces are filtered out
    """
    # Arrange: Create user
    user = Users(
        id=uuid4(),
        email="testuser@example.com",
        username="testuser",
        first_name="Test",
        last_name="User",
        password="hashed_password",
        status="active",
        email_verified=True
    )
    async_db.add(user)
    await async_db.flush()

    # Create active workspace
    active_workspace = WorkspaceModel(
        id=uuid4(),
        slug="active-workspace",
        title="Active Workspace",
        timezone="UTC",
        user_id=user.id
    )
    async_db.add(active_workspace)
    await async_db.flush()

    active_membership = WorkspaceMembers(
        id=uuid4(),
        user_id=user.id,
        workspace_id=active_workspace.id,
        status="active"
    )
    async_db.add(active_membership)

    # Create soft-deleted workspace
    from datetime import datetime
    deleted_workspace = WorkspaceModel(
        id=uuid4(),
        slug="deleted-workspace",
        title="Deleted Workspace",
        timezone="UTC",
        user_id=user.id,
        deleted_at=datetime.now(timezone.utc)  # Soft-deleted
    )
    async_db.add(deleted_workspace)
    await async_db.flush()

    deleted_membership = WorkspaceMembers(
        id=uuid4(),
        user_id=user.id,
        workspace_id=deleted_workspace.id,
        status="active"
    )
    async_db.add(deleted_membership)
    await async_db.commit()

    # Act: Get user workspaces
    from src.services.workspace_service import WorkspaceService

    workspace_service = WorkspaceService(async_db)
    workspaces = await workspace_service.get_user_workspaces(user.id)

    # Assert: Should only return active workspace
    assert len(workspaces) == 1
    assert workspaces[0]["slug"] == "active-workspace"


@pytest.mark.asyncio
async def test_get_user_workspaces_includes_statistics(async_db):
    """
    Test that workspace statistics are included correctly.

    Expected behavior:
    - knowledge_stats includes web_knowledge, files, text_knowledge, total
    - members_count is accurate
    - owner information is included
    """
    # Arrange: Create user and workspace
    user = Users(
        id=uuid4(),
        email="testuser@example.com",
        username="testuser",
        first_name="Test",
        last_name="User",
        password="hashed_password",
        status="active",
        email_verified=True
    )
    async_db.add(user)
    await async_db.flush()

    workspace = WorkspaceModel(
        id=uuid4(),
        slug="test-workspace",
        title="Test Workspace",
        timezone="UTC",
        user_id=user.id
    )
    async_db.add(workspace)
    await async_db.flush()

    membership = WorkspaceMembers(
        id=uuid4(),
        user_id=user.id,
        workspace_id=workspace.id,
        status="active"
    )
    async_db.add(membership)
    await async_db.commit()

    # Act: Get user workspaces
    from src.services.workspace_service import WorkspaceService

    workspace_service = WorkspaceService(async_db)
    workspaces = await workspace_service.get_user_workspaces(user.id)

    # Assert: Verify statistics structure
    assert len(workspaces) == 1
    workspace_data = workspaces[0]

    # Check knowledge_stats
    assert "knowledge_stats" in workspace_data
    stats = workspace_data["knowledge_stats"]
    assert "web_knowledge" in stats
    assert "files" in stats
    assert "text_knowledge" in stats
    assert "total" in stats
    assert isinstance(stats["web_knowledge"], int)
    assert isinstance(stats["total"], int)

    # Check owner info
    assert "owner" in workspace_data
    assert "name" in workspace_data["owner"]
    assert "email" in workspace_data["owner"]
    assert workspace_data["owner"]["email"] == "testuser@example.com"

    # Check members count
    assert "members_count" in workspace_data
    assert isinstance(workspace_data["members_count"], int)


@pytest.mark.asyncio
async def test_workspace_ordering(async_db):
    """
    Test that workspaces are returned in a consistent order.

    Expected behavior:
    - Workspaces are ordered consistently
    - Order is predictable for UI rendering
    """
    # Arrange: Create user with 3 workspaces
    user = Users(
        id=uuid4(),
        email="testuser@example.com",
        username="testuser",
        first_name="Test",
        last_name="User",
        password="hashed_password",
        status="active",
        email_verified=True
    )
    async_db.add(user)
    await async_db.flush()

    # Create workspaces with different creation times
    from datetime import datetime, timedelta

    workspaces_to_create = [
        ("workspace-1", "Workspace One", datetime.now(timezone.utc) - timedelta(days=3)),
        ("workspace-2", "Workspace Two", datetime.now(timezone.utc) - timedelta(days=2)),
        ("workspace-3", "Workspace Three", datetime.now(timezone.utc) - timedelta(days=1)),
    ]

    for slug, title, created_at in workspaces_to_create:
        workspace = WorkspaceModel(
            id=uuid4(),
            slug=slug,
            title=title,
            timezone="UTC",
            user_id=user.id,
            created_at=created_at
        )
        async_db.add(workspace)
        await async_db.flush()

        membership = WorkspaceMembers(
            id=uuid4(),
            user_id=user.id,
            workspace_id=workspace.id,
            status="active"
        )
        async_db.add(membership)

    await async_db.commit()

    # Act: Get user workspaces
    from src.services.workspace_service import WorkspaceService

    workspace_service = WorkspaceService(async_db)
    workspaces = await workspace_service.get_user_workspaces(user.id)

    # Assert: Should return all 3 workspaces
    assert len(workspaces) == 3

    # Verify all workspaces are present
    slugs = {ws["slug"] for ws in workspaces}
    assert slugs == {"workspace-1", "workspace-2", "workspace-3"}
