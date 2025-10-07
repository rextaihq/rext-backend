"""
Unit tests for WorkspaceService.

Tests cover:
- Get user workspaces with analytics
- Workspace creation with slug generation
- Workspace analytics
"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.workspace_service import WorkspaceService
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.workspace_models.workspace_member import WorkspaceMembers


@pytest.mark.asyncio
class TestWorkspaceServiceGetUserWorkspaces:
    """Test suite for get_user_workspaces() method"""

    async def test_get_user_workspaces_returns_list(self, db_session, setup_factories):
        """Test getting user workspaces returns list"""
        # Arrange
        user = await setup_factories["user"].create()
        workspace = await setup_factories["workspace"].create(user_id=user.id)

        # Create membership
        member = WorkspaceMembers(
            workspace_id=workspace.id,
            user_id=user.id,
            status="active"
        )
        db_session.add(member)
        await db_session.flush()

        service = WorkspaceService(db_session)

        # Act
        workspaces = await service.get_user_workspaces(user_id=user.id)

        # Assert
        assert isinstance(workspaces, list)
        assert len(workspaces) >= 1


@pytest.mark.asyncio
class TestWorkspaceServiceCreateWorkspace:
    """Test suite for create_workspace() method"""

    async def test_create_workspace_basic(self, db_session, setup_factories):
        """Test creating workspace with basic info"""
        # Arrange
        user = await setup_factories["user"].create()
        service = WorkspaceService(db_session)

        # Act
        workspace = await service.create_workspace(
            user_id=user.id,
            name="Test Workspace",
            description="Test Description",
            url="https://test.com"
        )

        # Assert
        assert workspace.user_id == user.id
        assert workspace.name == "Test Workspace"
        assert workspace.slug is not None

    async def test_create_workspace_generates_slug(self, db_session, setup_factories):
        """Test workspace creation generates slug from name"""
        # Arrange
        user = await setup_factories["user"].create()
        service = WorkspaceService(db_session)

        # Act
        workspace = await service.create_workspace(
            user_id=user.id,
            name="My Test Workspace",
            description=None,
            url=None
        )

        # Assert
        assert "test" in workspace.slug.lower()
        assert "workspace" in workspace.slug.lower()


@pytest.mark.asyncio
class TestWorkspaceServiceGetWorkspace:
    """Test suite for get_workspace() method"""

    async def test_get_workspace_success(self, db_session, setup_factories):
        """Test getting workspace by ID"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        service = WorkspaceService(db_session)

        # Act
        result = await service.get_workspace(workspace_id=workspace.id)

        # Assert
        assert result.id == workspace.id
        assert result.name == workspace.name


@pytest.mark.asyncio
class TestWorkspaceServiceAnalytics:
    """Test suite for get_workspace_analytics() method"""

    async def test_get_workspace_analytics_returns_counts(self, db_session, setup_factories):
        """Test workspace analytics returns knowledge and member counts"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        service = WorkspaceService(db_session)

        # Act
        analytics = await service.get_workspace_analytics(workspace_id=workspace.id)

        # Assert
        assert isinstance(analytics, dict)
        assert "knowledge_stats" in analytics or "members_count" in analytics


@pytest.mark.asyncio
class TestWorkspaceServiceNewFlows:
    async def test_create_workspace_for_user_invokes_setup(self):
        mock_db = AsyncMock()
        mock_workspace = WorkspaceModel(
            user_id=uuid4(),
            name="Example",
            slug="example",
            description="",
            url="https://example.com",
        )

        service = WorkspaceService(mock_db)

        service._ensure_active_user = AsyncMock()
        service.create_workspace = AsyncMock(return_value=mock_workspace)
        service.create_workspace_member = AsyncMock()
        service._ensure_workspace_admin_role = AsyncMock(return_value=AsyncMock(id=uuid4()))
        service._assign_permissions_to_role = AsyncMock()
        service._assign_role_to_user = AsyncMock()
        service._populate_brand_voice_and_vectors = AsyncMock()
        service._serialize_workspace = AsyncMock(return_value={"id": "workspace-id"})
        mock_db.refresh = AsyncMock()

        result = await service.create_workspace_for_user(
            user_id=uuid4(),
            name="Example",
            description="Desc",
            url="https://example.com",
        )

        assert result == {"id": "workspace-id"}
        service.create_workspace.assert_awaited_once()
        service.create_workspace_member.assert_awaited_once()
        service._populate_brand_voice_and_vectors.assert_awaited_once()

    async def test_delete_workspace_for_user_performs_cleanup(self):
        mock_db = AsyncMock()
        service = WorkspaceService(mock_db)

        workspace = WorkspaceModel(
            user_id=uuid4(),
            name="Example",
            slug="example",
        )
        workspace.id = uuid4()

        service._ensure_active_user = AsyncMock()
        service._ensure_membership = AsyncMock(return_value=workspace)
        service._delete_vectors_safe = AsyncMock()
        service.delete_workspace = AsyncMock()

        await service.delete_workspace_for_user(workspace.id, uuid4())

        service._ensure_membership.assert_awaited_once()
        service._delete_vectors_safe.assert_called_once()
        service.delete_workspace.assert_awaited_once_with(workspace.id)

    async def test_update_workspace_for_user_checks_name_uniqueness(self):
        mock_db = AsyncMock()
        mock_db.refresh = AsyncMock()
        service = WorkspaceService(mock_db)

        workspace = WorkspaceModel(
            user_id=uuid4(),
            name="Old Name",
            slug="old-name",
        )
        workspace.id = uuid4()

        service._ensure_active_user = AsyncMock()
        service._ensure_membership = AsyncMock(return_value=workspace)
        service._ensure_unique_workspace_name = AsyncMock()
        updated_workspace = WorkspaceModel(
            user_id=workspace.user_id,
            name="New Name",
            slug="new-name",
        )
        updated_workspace.id = workspace.id
        service.update_workspace = AsyncMock(return_value=updated_workspace)
        service._serialize_workspace = AsyncMock(return_value={"id": str(workspace.id), "name": "New Name"})

        result = await service.update_workspace_for_user(
            workspace_id=workspace.id,
            user_id=uuid4(),
            name="New Name",
            description="Updated",
            url="https://updated.example",
        )

        service._ensure_unique_workspace_name.assert_awaited_once()
        service.update_workspace.assert_awaited_once()
        assert result["name"] == "New Name"
