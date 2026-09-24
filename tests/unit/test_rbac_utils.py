"""
Unit tests for RBAC utilities.

Tests permission checking logic with AsyncSession mocking.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.exceptions import RextAuthorizationException
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.roles import Role
from src.utils.rbac_utils import (
    check_all_permissions,
    check_any_permission,
    check_permission,
    get_user_permissions,
    get_user_roles,
    require_permission,
)


class TestCheckPermission:
    """Tests for check_permission function."""

    @pytest.mark.asyncio
    async def test_check_permission_user_has_permission(self):
        """Test that check_permission returns True when user has the permission."""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)
        user_id = uuid4()
        permission_name = "content.create"
        workspace_id = uuid4()

        # Mock permission found
        Permission(
            id=uuid4(),
            name=permission_name,
            display_name="Create Content",
            description="Create new content",
            resource="content",
            action="create",
        )
        # Mock permissions found in get_user_permissions
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [permission_name]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        has_permission = await check_permission(mock_db, user_id, permission_name, workspace_id)

        # Assert
        assert has_permission is True
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_permission_user_lacks_permission(self):
        """Test that check_permission returns False when user lacks the permission."""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)
        user_id = uuid4()
        permission_name = "content.delete"
        workspace_id = uuid4()

        # Mock permission not found
        # Mock no permissions found in get_user_permissions
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        has_permission = await check_permission(mock_db, user_id, permission_name, workspace_id)

        # Assert
        assert has_permission is False
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_permission_global_scope(self):
        """Test check_permission with global scope (no workspace_id)."""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)
        user_id = uuid4()
        permission_name = "user.manage_roles"

        # Mock permission found
        Permission(
            id=uuid4(),
            name=permission_name,
            display_name="Manage User Roles",
            description="Assign/revoke roles",
            resource="user",
            action="manage_roles",
        )
        # Mock permissions found in get_user_permissions
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [permission_name]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        has_permission = await check_permission(
            mock_db, user_id, permission_name, workspace_id=None
        )

        # Assert
        assert has_permission is True


class TestCheckAnyPermission:
    """Tests for check_any_permission function (OR logic)."""

    @pytest.mark.asyncio
    async def test_check_any_permission_has_one(self):
        """Test that user with ONE of the permissions returns True."""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)
        user_id = uuid4()
        permission_names = ["content.update", "content.publish"]
        workspace_id = uuid4()

        # Mock get_user_permissions results
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = ["content.publish"]  # Only has second one

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        has_any = await check_any_permission(mock_db, user_id, permission_names, workspace_id)

        # Assert
        assert has_any is True

    @pytest.mark.asyncio
    async def test_check_any_permission_has_none(self):
        """Test that user with NONE of the permissions returns False."""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)
        user_id = uuid4()
        permission_names = ["content.delete", "workspace.delete"]
        workspace_id = uuid4()

        # Mock: Both permissions fail
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        has_any = await check_any_permission(mock_db, user_id, permission_names, workspace_id)

        # Assert
        assert has_any is False


class TestCheckAllPermissions:
    """Tests for check_all_permissions function (AND logic)."""

    @pytest.mark.asyncio
    async def test_check_all_permissions_has_all(self):
        """Test that user with ALL permissions returns True."""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)
        user_id = uuid4()
        permission_names = ["content.read", "content.create"]
        workspace_id = uuid4()

        # Mock: Both permissions succeed
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = permission_names
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        has_all = await check_all_permissions(mock_db, user_id, permission_names, workspace_id)

        # Assert
        assert has_all is True

    @pytest.mark.asyncio
    async def test_check_all_permissions_missing_one(self):
        """Test that user missing ONE permission returns False."""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)
        user_id = uuid4()
        permission_names = ["content.read", "content.delete"]
        workspace_id = uuid4()

        # Mock: First succeeds, second fails (delegated via get_user_permissions)
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = ["content.read"]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        has_all = await check_all_permissions(mock_db, user_id, permission_names, workspace_id)

        # Assert
        assert has_all is False


class TestRequirePermission:
    """Tests for require_permission function."""

    @pytest.mark.asyncio
    async def test_require_permission_success(self):
        """Test that require_permission passes when user has permission."""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)
        user_id = uuid4()
        permission_name = "content.create"
        workspace_id = uuid4()

        # Mock permission found
        Permission(
            id=uuid4(),
            name=permission_name,
            display_name="Create",
            description="Create",
            resource="content",
            action="create",
        )
        # Mock permission found (delegated via get_user_permissions)
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [permission_name]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Act - should not raise exception
        await require_permission(mock_db, user_id, permission_name, workspace_id)

        # Assert - no exception raised

    @pytest.mark.asyncio
    async def test_require_permission_raises_exception(self):
        """Test that require_permission raises RextAuthorizationException when permission denied."""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)
        user_id = uuid4()
        permission_name = "content.delete"
        workspace_id = uuid4()

        # Mock permission not found (delegated via get_user_permissions)
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Act & Assert
        with pytest.raises(RextAuthorizationException) as exc_info:
            await require_permission(
                mock_db, user_id, permission_name, workspace_id, resource_name="content"
            )

        assert "You do not have permission" in exc_info.value.message
        assert exc_info.value.context["required_permission"] == permission_name


class TestGetUserPermissions:
    """Tests for get_user_permissions function."""

    @pytest.mark.asyncio
    async def test_get_user_permissions_returns_list(self):
        """Test that get_user_permissions returns list of permission names."""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)
        user_id = uuid4()
        workspace_id = uuid4()

        # Mock permission names
        permission_names = ["content.create", "content.read", "content.update"]
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = permission_names
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        permissions = await get_user_permissions(mock_db, user_id, workspace_id)

        # Assert
        assert permissions == permission_names
        assert len(permissions) == 3

    @pytest.mark.asyncio
    async def test_get_user_permissions_empty(self):
        """Test that get_user_permissions returns empty list when no permissions."""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)
        user_id = uuid4()

        # Mock no permissions
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        permissions = await get_user_permissions(mock_db, user_id)

        # Assert
        assert permissions == []


class TestGetUserRoles:
    """Tests for get_user_roles function."""

    @pytest.mark.asyncio
    async def test_get_user_roles_returns_tuples(self):
        """Test that get_user_roles returns list of (Role, workspace_id) tuples."""
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)
        user_id = uuid4()
        workspace_id = uuid4()

        # Mock roles
        role1 = Role(
            id=uuid4(),
            name="editor",
            display_name="Editor",
            description="Edit content",
            hierarchy_level=50,
            is_system_role=True,
        )
        role2 = Role(
            id=uuid4(),
            name="admin",
            display_name="Admin",
            description="Administer workspace",
            hierarchy_level=80,
            is_system_role=True,
        )

        mock_result = MagicMock()
        mock_result.all.return_value = [
            (role1, workspace_id),  # Workspace-scoped role
            (role2, None),  # Global role
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        roles = await get_user_roles(mock_db, user_id, workspace_id)

        # Assert
        assert len(roles) == 2
        assert roles[0][0].name == "editor"
        assert roles[0][1] == workspace_id
        assert roles[1][0].name == "admin"
        assert roles[1][1] is None
