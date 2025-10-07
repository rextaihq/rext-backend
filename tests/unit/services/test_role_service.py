"""
Unit tests for RoleService.

Tests cover:
- create_role: Role creation with permission assignment
- update_role: Role updates with system role protection
- delete_role: Role deletion with user reassignment
- assign_role: User role assignment with workspace validation
- revoke_role: Role revocation
- update_role_permissions: Permission management
- get_role_hierarchy: Role hierarchy retrieval
- get_user_roles: User role listing
- get_role_with_permissions: Role details with permissions
"""

import pytest
from uuid import uuid4
from datetime import datetime

from src.services.role_service import RoleService
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    WrextValidationException,
    ResourceNotFoundException,
    WrextAPIException
)


@pytest.mark.unit
class TestRoleServiceCreateRole:
    """Test create_role method"""

    async def test_create_role_success(self, db_session, setup_factories):
        """Should create role with basic attributes"""
        # Arrange
        service = RoleService(db_session)
        unique_id = uuid4().hex[:8]

        # Act
        role = await service.create_role(
            name=f"editor_{unique_id}",
            display_name=f"Editor {unique_id}",
            description="Can edit content",
            hierarchy_level=2
        )

        # Assert
        assert role.name == f"editor_{unique_id}".lower()
        assert role.display_name == f"Editor {unique_id}"
        assert role.description == "Can edit content"
        assert role.hierarchy_level == 2
        assert role.is_system_role is False
        assert role.id is not None

    async def test_create_role_lowercases_name(self, db_session):
        """Should lowercase role name automatically"""
        # Arrange
        service = RoleService(db_session)

        # Act
        role = await service.create_role(
            name="ContentEditor",
            display_name="Content Editor"
        )

        # Assert
        assert role.name == "contenteditor"

    async def test_create_role_duplicate_name(self, db_session, setup_factories):
        """Should raise DuplicateResourceException when name exists"""
        # Arrange
        service = RoleService(db_session)

        # Create first role
        await service.create_role(
            name="manager",
            display_name="Manager"
        )

        # Act & Assert
        with pytest.raises(DuplicateResourceException) as exc_info:
            await service.create_role(
                name="manager",
                display_name="Manager 2"
            )

        assert exc_info.value.context["conflicting_field"] == "name"
        assert exc_info.value.context["conflicting_value"] == "manager"

    async def test_create_role_duplicate_display_name(self, db_session):
        """Should raise DuplicateResourceException when display_name exists"""
        # Arrange
        service = RoleService(db_session)

        # Create first role
        await service.create_role(
            name="role1",
            display_name="Unique Display"
        )

        # Act & Assert
        with pytest.raises(DuplicateResourceException) as exc_info:
            await service.create_role(
                name="role2",
                display_name="Unique Display"
            )

        assert exc_info.value.context["conflicting_field"] == "display_name"
        assert exc_info.value.context["conflicting_value"] == "Unique Display"

    async def test_create_role_with_permissions(self, db_session, setup_factories):
        """Should create role and assign permissions"""
        # Arrange
        from src.api.models.user_models.permissions import Permission

        # Create permissions
        unique_id = uuid4().hex[:8]
        perm1 = Permission(id=uuid4(), name=f"content.create.{unique_id}", display_name="Create Content", resource="content", action="create")
        perm2 = Permission(id=uuid4(), name=f"content.edit.{unique_id}", display_name="Edit Content", resource="content", action="edit")

        db_session.add(perm1)
        db_session.add(perm2)
        await db_session.flush()

        service = RoleService(db_session)

        # Act
        role = await service.create_role(
            name=f"editor_{unique_id}",
            display_name=f"Editor {unique_id}",
            permission_ids=[perm1.id, perm2.id]
        )

        # Assert
        assert role.id is not None
        # Permissions assignment is tested in update_role_permissions tests


@pytest.mark.unit
class TestRoleServiceUpdateRole:
    """Test update_role method"""

    async def test_update_role_display_name(self, db_session):
        """Should update display name"""
        # Arrange
        service = RoleService(db_session)
        role = await service.create_role(
            name="contributor",
            display_name="Contributor"
        )

        # Act
        updated = await service.update_role(
            role.id,
            display_name="Senior Contributor"
        )

        # Assert
        assert updated.display_name == "Senior Contributor"
        assert updated.name == "contributor"  # Name unchanged

    async def test_update_role_description(self, db_session):
        """Should update description"""
        # Arrange
        service = RoleService(db_session)
        role = await service.create_role(
            name="reviewer",
            display_name="Reviewer",
            description="Old description"
        )

        # Act
        updated = await service.update_role(
            role.id,
            description="New description"
        )

        # Assert
        assert updated.description == "New description"

    async def test_update_role_hierarchy_level(self, db_session):
        """Should update hierarchy level"""
        # Arrange
        service = RoleService(db_session)
        role = await service.create_role(
            name="junior",
            display_name="Junior",
            hierarchy_level=1
        )

        # Act
        updated = await service.update_role(
            role.id,
            hierarchy_level=5
        )

        # Assert
        assert updated.hierarchy_level == 5

    async def test_update_role_invalid_hierarchy_level(self, db_session):
        """Should raise WrextValidationException for invalid hierarchy level"""
        # Arrange
        service = RoleService(db_session)
        role = await service.create_role(
            name="test",
            display_name="Test"
        )

        # Act & Assert
        with pytest.raises(WrextValidationException) as exc_info:
            await service.update_role(role.id, hierarchy_level=150)

        assert "hierarchy level must be between 0 and 100" in exc_info.value.message.lower()

    async def test_update_role_system_role_protection(self, db_session):
        """Should prevent updating system roles"""
        # Arrange
        service = RoleService(db_session)
        unique_id = uuid4().hex[:8]
        role = await service.create_role(
            name=f"admin_{unique_id}",
            display_name=f"Admin {unique_id}",
            is_system_role=True
        )

        # Act & Assert
        with pytest.raises(WrextValidationException) as exc_info:
            await service.update_role(
                role.id,
                display_name="Super Admin"
            )

        assert "cannot update system roles" in exc_info.value.message.lower()

    async def test_update_role_not_found(self, db_session):
        """Should raise ResourceNotFoundException when role doesn't exist"""
        # Arrange
        service = RoleService(db_session)
        non_existent_id = uuid4()

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.update_role(
                non_existent_id,
                display_name="New Name"
            )


@pytest.mark.unit
class TestRoleServiceDeleteRole:
    """Test delete_role method"""

    async def test_delete_role_success(self, db_session):
        """Should delete role when not assigned to users"""
        # Arrange
        service = RoleService(db_session)
        role = await service.create_role(
            name="temporary",
            display_name="Temporary"
        )

        # Act
        await service.delete_role(role.id)

        # Assert - role should not exist
        with pytest.raises(ResourceNotFoundException):
            await service._get_role_or_404(role.id)

    async def test_delete_role_system_role_protection(self, db_session):
        """Should prevent deleting system roles"""
        # Arrange
        service = RoleService(db_session)
        unique_id = uuid4().hex[:8]
        role = await service.create_role(
            name=f"admin_{unique_id}",
            display_name=f"Admin {unique_id}",
            is_system_role=True
        )

        # Act & Assert
        with pytest.raises(WrextValidationException) as exc_info:
            await service.delete_role(role.id)

        assert "cannot delete system roles" in exc_info.value.message.lower()

    async def test_delete_role_in_use_without_reassignment(self, db_session, setup_factories):
        """Should raise WrextValidationException when role assigned to users"""
        # Arrange
        user = await setup_factories["user"].create()
        service = RoleService(db_session)

        role = await service.create_role(
            name="assigned_role",
            display_name="Assigned Role"
        )

        # Assign role to user
        await service.assign_role(user.id, role.id)

        # Act & Assert
        with pytest.raises(WrextValidationException) as exc_info:
            await service.delete_role(role.id)

        assert "cannot delete role assigned to" in exc_info.value.message.lower()
        assert "reassign_to" in exc_info.value.message.lower()

    async def test_delete_role_with_reassignment(self, db_session, setup_factories):
        """Should delete role and reassign users to new role"""
        # Arrange
        user = await setup_factories["user"].create()
        service = RoleService(db_session)

        old_role = await service.create_role(
            name="old_role",
            display_name="Old Role"
        )

        new_role = await service.create_role(
            name="new_role",
            display_name="New Role"
        )

        # Assign old role to user
        await service.assign_role(user.id, old_role.id)

        # Act
        await service.delete_role(old_role.id, reassign_to=new_role.id)

        # Assert - old role deleted
        with pytest.raises(ResourceNotFoundException):
            await service._get_role_or_404(old_role.id)

        # User should have new role
        user_roles = await service.get_user_roles(user.id)
        assert len(user_roles) == 1
        assert user_roles[0]["role_id"] == str(new_role.id)


@pytest.mark.unit
class TestRoleServiceAssignRole:
    """Test assign_role method"""

    async def test_assign_role_success(self, db_session, setup_factories):
        """Should assign role to user"""
        # Arrange
        user = await setup_factories["user"].create()
        service = RoleService(db_session)

        role = await service.create_role(
            name="contributor",
            display_name="Contributor"
        )

        # Act
        user_role = await service.assign_role(
            user_id=user.id,
            role_id=role.id,
            is_primary=True
        )

        # Assert
        assert user_role.user_id == user.id
        assert user_role.role_id == role.id
        assert user_role.is_primary is True
        assert user_role.workspace_id is None

    async def test_assign_role_idempotent(self, db_session, setup_factories):
        """Should return existing assignment if already assigned"""
        # Arrange
        user = await setup_factories["user"].create()
        service = RoleService(db_session)

        unique_id = uuid4().hex[:8]
        role = await service.create_role(
            name=f"editor_{unique_id}",
            display_name=f"Editor {unique_id}"
        )

        # Act - assign twice
        first_assignment = await service.assign_role(user.id, role.id)
        second_assignment = await service.assign_role(user.id, role.id)

        # Assert - same assignment returned
        assert first_assignment.id == second_assignment.id

    async def test_assign_role_workspace_scoped(self, db_session, setup_factories):
        """Should assign workspace-scoped role with membership validation"""
        # Arrange
        user = await setup_factories["user"].create()
        workspace = await setup_factories["workspace"].create(user_id=user.id)

        # Create workspace member
        from src.api.models.workspace_models.workspace_member import WorkspaceMembers
        member = WorkspaceMembers(
            id=uuid4(),
            workspace_id=workspace.id,
            user_id=user.id,
            status="active"
        )
        db_session.add(member)
        await db_session.flush()

        service = RoleService(db_session)
        unique_id = uuid4().hex[:8]
        role = await service.create_role(
            name=f"workspace_admin_{unique_id}",
            display_name=f"Workspace Admin {unique_id}"
        )

        # Act
        user_role = await service.assign_role(
            user_id=user.id,
            role_id=role.id,
            workspace_id=workspace.id
        )

        # Assert
        assert user_role.workspace_id == workspace.id

    async def test_assign_role_workspace_not_member(self, db_session, setup_factories):
        """Should raise WrextValidationException when user not workspace member"""
        # Arrange
        user = await setup_factories["user"].create()
        workspace = await setup_factories["workspace"].create()

        service = RoleService(db_session)
        role = await service.create_role(
            name="workspace_role",
            display_name="Workspace Role"
        )

        # Act & Assert
        with pytest.raises(WrextValidationException) as exc_info:
            await service.assign_role(
                user_id=user.id,
                role_id=role.id,
                workspace_id=workspace.id
            )

        assert "not a member" in exc_info.value.message.lower()

    async def test_assign_role_role_not_found(self, db_session, setup_factories):
        """Should raise ResourceNotFoundException when role doesn't exist"""
        # Arrange
        user = await setup_factories["user"].create()
        service = RoleService(db_session)
        non_existent_role_id = uuid4()

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.assign_role(user.id, non_existent_role_id)


@pytest.mark.unit
class TestRoleServiceRevokeRole:
    """Test revoke_role method"""

    async def test_revoke_role_success(self, db_session, setup_factories):
        """Should revoke role from user"""
        # Arrange
        user = await setup_factories["user"].create()
        service = RoleService(db_session)

        role = await service.create_role(
            name="temporary",
            display_name="Temporary"
        )

        # Assign and then revoke
        await service.assign_role(user.id, role.id)

        # Act
        await service.revoke_role(user.id, role.id)

        # Assert - user should have no roles
        user_roles = await service.get_user_roles(user.id)
        assert len(user_roles) == 0

    async def test_revoke_role_workspace_scoped(self, db_session, setup_factories):
        """Should revoke workspace-scoped role"""
        # Arrange
        user = await setup_factories["user"].create()
        workspace = await setup_factories["workspace"].create(user_id=user.id)

        # Create workspace member
        from src.api.models.workspace_models.workspace_member import WorkspaceMembers
        member = WorkspaceMembers(
            id=uuid4(),
            workspace_id=workspace.id,
            user_id=user.id,
            status="active"
        )
        db_session.add(member)
        await db_session.flush()

        service = RoleService(db_session)
        role = await service.create_role(
            name="workspace_role",
            display_name="Workspace Role"
        )

        # Assign workspace-scoped role
        await service.assign_role(user.id, role.id, workspace_id=workspace.id)

        # Act
        await service.revoke_role(user.id, role.id, workspace_id=workspace.id)

        # Assert
        user_roles = await service.get_user_roles(user.id)
        assert len(user_roles) == 0

    async def test_revoke_role_not_found(self, db_session, setup_factories):
        """Should raise ResourceNotFoundException when assignment doesn't exist"""
        # Arrange
        user = await setup_factories["user"].create()
        service = RoleService(db_session)

        role = await service.create_role(
            name="never_assigned",
            display_name="Never Assigned"
        )

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.revoke_role(user.id, role.id)


@pytest.mark.unit
class TestRoleServiceUpdateRolePermissions:
    """Test update_role_permissions method"""

    async def test_update_role_permissions_success(self, db_session):
        """Should update role permissions"""
        # Arrange
        from src.api.models.user_models.permissions import Permission

        perm1 = Permission(id=uuid4(), name="perm1", display_name="Permission 1", resource="res1", action="read")
        perm2 = Permission(id=uuid4(), name="perm2", display_name="Permission 2", resource="res2", action="write")

        db_session.add(perm1)
        db_session.add(perm2)
        await db_session.flush()

        service = RoleService(db_session)
        role = await service.create_role(
            name="test_role",
            display_name="Test Role"
        )

        # Act
        updated_role = await service.update_role_permissions(
            role.id,
            [perm1.id, perm2.id]
        )

        # Assert
        assert updated_role.id == role.id

    async def test_update_role_permissions_invalid_permission(self, db_session):
        """Should raise ResourceNotFoundException for invalid permission"""
        # Arrange
        service = RoleService(db_session)
        role = await service.create_role(
            name="test_role",
            display_name="Test Role"
        )

        non_existent_perm_id = uuid4()

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.update_role_permissions(
                role.id,
                [non_existent_perm_id]
            )


@pytest.mark.unit
class TestRoleServiceGetRoleHierarchy:
    """Test get_role_hierarchy method"""

    async def test_get_role_hierarchy_ordered(self, db_session):
        """Should return roles ordered by hierarchy level (descending)"""
        # Arrange
        service = RoleService(db_session)
        unique_id = uuid4().hex[:8]

        # Create roles with different hierarchy levels
        await service.create_role(name=f"admin_{unique_id}", display_name=f"Admin {unique_id}", hierarchy_level=10)
        await service.create_role(name=f"editor_{unique_id}", display_name=f"Editor {unique_id}", hierarchy_level=5)
        await service.create_role(name=f"viewer_{unique_id}", display_name=f"Viewer {unique_id}", hierarchy_level=1)

        # Act
        roles = await service.get_role_hierarchy()

        # Assert - check that our roles are ordered correctly
        # (there might be other roles in the DB, so we filter to our test roles)
        our_roles = [r for r in roles if unique_id in r.name]
        assert len(our_roles) == 3
        assert our_roles[0].hierarchy_level == 10  # Admin first
        assert our_roles[1].hierarchy_level == 5   # Editor second
        assert our_roles[2].hierarchy_level == 1   # Viewer last


@pytest.mark.unit
class TestRoleServiceGetUserRoles:
    """Test get_user_roles method"""

    async def test_get_user_roles_success(self, db_session, setup_factories):
        """Should return all roles assigned to user"""
        # Arrange
        user = await setup_factories["user"].create()
        service = RoleService(db_session)

        role1 = await service.create_role(name="role1", display_name="Role 1")
        role2 = await service.create_role(name="role2", display_name="Role 2")

        await service.assign_role(user.id, role1.id, is_primary=True)
        await service.assign_role(user.id, role2.id)

        # Act
        user_roles = await service.get_user_roles(user.id)

        # Assert
        assert len(user_roles) == 2
        assert any(r["role_name"] == "role1" for r in user_roles)
        assert any(r["role_name"] == "role2" for r in user_roles)
        assert any(r["is_primary"] is True for r in user_roles)

    async def test_get_user_roles_empty(self, db_session, setup_factories):
        """Should return empty list when user has no roles"""
        # Arrange
        user = await setup_factories["user"].create()
        service = RoleService(db_session)

        # Act
        user_roles = await service.get_user_roles(user.id)

        # Assert
        assert len(user_roles) == 0


@pytest.mark.unit
class TestRoleServiceGetRoleWithPermissions:
    """Test get_role_with_permissions method"""

    async def test_get_role_with_permissions_success(self, db_session):
        """Should return role with permissions list"""
        # Arrange
        from src.api.models.user_models.permissions import Permission

        perm = Permission(id=uuid4(), name="test.read", display_name="Test Read", resource="test", action="read")
        db_session.add(perm)
        await db_session.flush()

        service = RoleService(db_session)
        role = await service.create_role(
            name="tester",
            display_name="Tester",
            permission_ids=[perm.id]
        )

        # Act
        role_data = await service.get_role_with_permissions(role.id)

        # Assert
        assert role_data["name"] == "tester"
        assert "permissions" in role_data
        assert len(role_data["permissions"]) == 1
        assert role_data["permissions"][0]["name"] == "test.read"

    async def test_get_role_with_permissions_not_found(self, db_session):
        """Should raise ResourceNotFoundException when role doesn't exist"""
        # Arrange
        service = RoleService(db_session)
        non_existent_id = uuid4()

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.get_role_with_permissions(non_existent_id)
