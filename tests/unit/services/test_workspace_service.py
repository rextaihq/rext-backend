"""
Unit tests for WorkspaceService.

Tests cover:
- Get user workspaces with analytics
- Workspace creation with slug generation
- Workspace analytics
"""

import pytest
from uuid import uuid4
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
