"""
Unit tests for MemberService.

Tests cover:
- add_member: Adding members with validation
- remove_member: Member removal
- get_workspace_members: Member listing with filters
- get_user_workspaces: User's workspace memberships
- update_member_status: Status management
- set_default_workspace: Default workspace selection
- get_member_count: Member counting
- update_last_activity: Activity tracking
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from src.api.middleware.exceptions import (
    BusinessRuleViolationException,
    DuplicateResourceException,
    ResourceNotFoundException,
    RextValidationException,
)
from src.services.member_service import MemberService


@pytest.mark.unit
class TestMemberServiceAddMember:
    """Test add_member method"""

    async def test_add_member_success(self, db_session, setup_factories):
        """Should successfully add a member to workspace"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        service = MemberService(db_session)

        # Act
        result = await service.add_member(workspace_id=workspace.id, user_id=user.id)

        # Assert
        assert result.workspace_id == workspace.id
        assert result.user_id == user.id
        assert result.status == "active"
        assert result.joined_at is not None

    async def test_add_member_with_invitation(self, db_session, setup_factories):
        """Should add member with invitation_id as None"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        service = MemberService(db_session)

        # Act - invitation_id can be None
        result = await service.add_member(
            workspace_id=workspace.id, user_id=user.id, invitation_id=None
        )

        # Assert
        assert result.invitation_id is None

    async def test_add_member_with_pending_status(self, db_session, setup_factories):
        """Should add member with pending status"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        service = MemberService(db_session)

        # Act
        result = await service.add_member(
            workspace_id=workspace.id, user_id=user.id, status="pending"
        )

        # Assert
        assert result.status == "pending"

    async def test_add_member_workspace_not_found(self, db_session, setup_factories):
        """Should raise ResourceNotFoundException if workspace doesn't exist"""
        # Arrange
        user = await setup_factories["user"].create()
        service = MemberService(db_session)
        non_existent_workspace = uuid4()

        # Act & Assert
        with pytest.raises(ResourceNotFoundException) as exc_info:
            await service.add_member(workspace_id=non_existent_workspace, user_id=user.id)

        assert "Workspace" in exc_info.value.message

    async def test_add_member_duplicate(self, db_session, setup_factories):
        """Should raise DuplicateResourceException if user already a member"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        await setup_factories["workspace_member"].create(workspace_id=workspace.id, user_id=user.id)
        service = MemberService(db_session)

        # Act & Assert
        with pytest.raises(DuplicateResourceException) as exc_info:
            await service.add_member(workspace_id=workspace.id, user_id=user.id)

        assert "already exists" in exc_info.value.message
        assert exc_info.value.context.get("conflicting_field") == "user_id"


@pytest.mark.unit
class TestMemberServiceRemoveMember:
    """Test remove_member method"""

    async def test_remove_member_success(self, db_session, setup_factories):
        """Should successfully remove a member"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        await setup_factories["workspace_member"].create(workspace_id=workspace.id, user_id=user.id)
        service = MemberService(db_session)

        # Act
        result = await service.remove_member(workspace_id=workspace.id, user_id=user.id)

        # Assert
        assert result["user_id"] == str(user.id)
        assert result["workspace_id"] == str(workspace.id)
        assert "removed_at" in result

    async def test_remove_member_not_found(self, db_session, setup_factories):
        """Should raise ResourceNotFoundException if member doesn't exist"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        non_existent_user = uuid4()
        service = MemberService(db_session)

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.remove_member(workspace_id=workspace.id, user_id=non_existent_user)


@pytest.mark.unit
class TestMemberServiceGetWorkspaceMembers:
    """Test get_workspace_members method"""

    async def test_get_workspace_members_all(self, db_session, setup_factories):
        """Should return all workspace members"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user1 = await setup_factories["user"].create()
        user2 = await setup_factories["user"].create()
        await setup_factories["workspace_member"].create(
            workspace_id=workspace.id, user_id=user1.id, status="active"
        )
        await setup_factories["workspace_member"].create(
            workspace_id=workspace.id, user_id=user2.id, status="pending"
        )
        service = MemberService(db_session)

        # Act
        result = await service.get_workspace_members(workspace.id)

        # Assert
        assert len(result) == 2

    async def test_get_workspace_members_filtered_by_status(self, db_session, setup_factories):
        """Should filter members by status"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user1 = await setup_factories["user"].create()
        user2 = await setup_factories["user"].create()
        await setup_factories["workspace_member"].create(
            workspace_id=workspace.id, user_id=user1.id, status="active"
        )
        await setup_factories["workspace_member"].create(
            workspace_id=workspace.id, user_id=user2.id, status="pending"
        )
        service = MemberService(db_session)

        # Act
        result = await service.get_workspace_members(workspace.id, status="active")

        # Assert
        assert len(result) == 1
        assert result[0].status == "active"

    async def test_get_workspace_members_pagination(self, db_session, setup_factories):
        """Should support pagination"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        users = [await setup_factories["user"].create() for _ in range(5)]
        for user in users:
            await setup_factories["workspace_member"].create(
                workspace_id=workspace.id, user_id=user.id
            )
        service = MemberService(db_session)

        # Act
        result = await service.get_workspace_members(workspace.id, limit=2, offset=1)

        # Assert
        assert len(result) == 2


@pytest.mark.unit
class TestMemberServiceGetUserWorkspaces:
    """Test get_user_workspaces method"""

    async def test_get_user_workspaces_all(self, db_session, setup_factories):
        """Should return all user's workspace memberships"""
        # Arrange
        user = await setup_factories["user"].create()
        workspace1 = await setup_factories["workspace"].create()
        workspace2 = await setup_factories["workspace"].create()
        await setup_factories["workspace_member"].create(
            workspace_id=workspace1.id, user_id=user.id
        )
        await setup_factories["workspace_member"].create(
            workspace_id=workspace2.id, user_id=user.id
        )
        service = MemberService(db_session)

        # Act
        result = await service.get_user_workspaces(user.id)

        # Assert
        assert len(result) == 2

    async def test_get_user_workspaces_filtered(self, db_session, setup_factories):
        """Should filter by status"""
        # Arrange
        user = await setup_factories["user"].create()
        workspace1 = await setup_factories["workspace"].create()
        workspace2 = await setup_factories["workspace"].create()
        await setup_factories["workspace_member"].create(
            workspace_id=workspace1.id, user_id=user.id, status="active"
        )
        await setup_factories["workspace_member"].create(
            workspace_id=workspace2.id, user_id=user.id, status="inactive"
        )
        service = MemberService(db_session)

        # Act
        result = await service.get_user_workspaces(user.id, status="active")

        # Assert
        assert len(result) == 1
        assert result[0].status == "active"


@pytest.mark.unit
class TestMemberServiceUpdateMemberStatus:
    """Test update_member_status method"""

    async def test_update_member_status_success(self, db_session, setup_factories):
        """Should update member status"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        await setup_factories["workspace_member"].create(
            workspace_id=workspace.id, user_id=user.id, status="pending"
        )
        service = MemberService(db_session)

        # Act
        result = await service.update_member_status(
            workspace_id=workspace.id, user_id=user.id, status="active"
        )

        # Assert
        assert result.status == "active"

    async def test_update_member_status_invalid(self, db_session, setup_factories):
        """Should raise RextValidationException for invalid status"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        await setup_factories["workspace_member"].create(workspace_id=workspace.id, user_id=user.id)
        service = MemberService(db_session)

        # Act & Assert
        with pytest.raises(RextValidationException) as exc_info:
            await service.update_member_status(
                workspace_id=workspace.id, user_id=user.id, status="invalid_status"
            )

        assert "Invalid status" in exc_info.value.message

    async def test_update_member_status_not_found(self, db_session, setup_factories):
        """Should raise ResourceNotFoundException if member doesn't exist"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        non_existent_user = uuid4()
        service = MemberService(db_session)

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.update_member_status(
                workspace_id=workspace.id, user_id=non_existent_user, status="active"
            )


@pytest.mark.unit
class TestMemberServiceSetDefaultWorkspace:
    """Test set_default_workspace method"""

    async def test_set_default_workspace_success(self, db_session, setup_factories):
        """Should set workspace as default"""
        # Arrange
        user = await setup_factories["user"].create()
        workspace = await setup_factories["workspace"].create()
        await setup_factories["workspace_member"].create(
            workspace_id=workspace.id, user_id=user.id, is_default=False
        )
        service = MemberService(db_session)

        # Act
        result = await service.set_default_workspace(user_id=user.id, workspace_id=workspace.id)

        # Assert
        assert result.is_default is True

    async def test_set_default_workspace_clears_previous(self, db_session, setup_factories):
        """Should clear previous default workspace"""
        # Arrange
        user = await setup_factories["user"].create()
        workspace1 = await setup_factories["workspace"].create()
        workspace2 = await setup_factories["workspace"].create()
        member1 = await setup_factories["workspace_member"].create(
            workspace_id=workspace1.id, user_id=user.id, is_default=True
        )
        await setup_factories["workspace_member"].create(
            workspace_id=workspace2.id, user_id=user.id, is_default=False
        )
        service = MemberService(db_session)

        # Act
        result = await service.set_default_workspace(user_id=user.id, workspace_id=workspace2.id)
        await db_session.flush()
        await db_session.refresh(member1)

        # Assert
        assert result.is_default is True
        assert member1.is_default is False

    async def test_set_default_workspace_not_found(self, db_session, setup_factories):
        """Should raise ResourceNotFoundException if member doesn't exist"""
        # Arrange
        user = await setup_factories["user"].create()
        workspace = await setup_factories["workspace"].create()
        service = MemberService(db_session)

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.set_default_workspace(user_id=user.id, workspace_id=workspace.id)


@pytest.mark.unit
class TestMemberServiceGetMemberCount:
    """Test get_member_count method"""

    async def test_get_member_count_all(self, db_session, setup_factories):
        """Should count all members"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        users = [await setup_factories["user"].create() for _ in range(3)]
        for user in users:
            await setup_factories["workspace_member"].create(
                workspace_id=workspace.id, user_id=user.id
            )
        service = MemberService(db_session)

        # Act
        result = await service.get_member_count(workspace.id)

        # Assert
        assert result == 3

    async def test_get_member_count_filtered(self, db_session, setup_factories):
        """Should count members by status"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user1 = await setup_factories["user"].create()
        user2 = await setup_factories["user"].create()
        await setup_factories["workspace_member"].create(
            workspace_id=workspace.id, user_id=user1.id, status="active"
        )
        await setup_factories["workspace_member"].create(
            workspace_id=workspace.id, user_id=user2.id, status="pending"
        )
        service = MemberService(db_session)

        # Act
        result = await service.get_member_count(workspace.id, status="active")

        # Assert
        assert result == 1


@pytest.mark.unit
class TestMemberServiceUpdateLastActivity:
    """Test update_last_activity method"""

    async def test_update_last_activity_success(self, db_session, setup_factories):
        """Should update last_activity_at timestamp"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        old_time = datetime.now(timezone.utc) - timedelta(hours=1)
        member = await setup_factories["workspace_member"].create(
            workspace_id=workspace.id, user_id=user.id, last_activity_at=old_time
        )
        service = MemberService(db_session)

        # Act
        await service.update_last_activity(workspace_id=workspace.id, user_id=user.id)
        await db_session.flush()
        await db_session.refresh(member)

        # Assert
        assert member.last_activity_at > old_time

    async def test_update_last_activity_not_found(self, db_session, setup_factories):
        """Should raise ResourceNotFoundException if member doesn't exist"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        non_existent_user = uuid4()
        service = MemberService(db_session)

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.update_last_activity(workspace_id=workspace.id, user_id=non_existent_user)


async def _get_or_create_role(db_session, setup_factories, role_name: str):
    from sqlalchemy import select

    from src.api.models.user_models.roles import Role

    res = await db_session.execute(select(Role).where(Role.name == role_name))
    role = res.scalar_one_or_none()
    if not role:
        role = await setup_factories["role"].create(name=role_name, is_workspace_role=True)
    return role


@pytest.mark.unit
class TestMemberServiceOwnerProtection:
    """Tests ensuring workspace owner cannot be removed or have their role changed"""

    async def test_remove_member_owner_forbidden(self, db_session, setup_factories):
        """Should raise BusinessRuleViolationException when attempting to remove the workspace owner"""
        # Arrange
        owner = await setup_factories["user"].create()
        workspace = await setup_factories["workspace"].create(user_id=owner.id)
        await setup_factories["workspace_member"].create(
            workspace_id=workspace.id, user_id=owner.id, status="active"
        )
        service = MemberService(db_session)

        # Act & Assert
        with pytest.raises(BusinessRuleViolationException) as exc_info:
            await service.remove_member(workspace_id=workspace.id, user_id=owner.id)

        assert "owner" in exc_info.value.message.lower()

    async def test_update_member_role_owner_forbidden(self, db_session, setup_factories):
        """Should raise RextValidationException when attempting to change the owner's role"""
        # Arrange
        owner = await setup_factories["user"].create()
        workspace = await setup_factories["workspace"].create(user_id=owner.id)
        member = await setup_factories["workspace_member"].create(
            workspace_id=workspace.id, user_id=owner.id, status="active"
        )
        editor_role = await _get_or_create_role(db_session, setup_factories, "editor")
        service = MemberService(db_session)

        # Act & Assert
        with pytest.raises(RextValidationException) as exc_info:
            await service.update_member_role(
                workspace_id=workspace.id,
                member_id=member.id,
                new_role_id=editor_role.id,
                assigned_by_user_id=owner.id,
            )

        assert "owner" in exc_info.value.message.lower()


@pytest.mark.unit
class TestMemberServiceRoleAssignment:
    """Tests ensuring workspace_owner role cannot be assigned, but valid roles can"""

    async def test_add_member_owner_role_forbidden(self, db_session, setup_factories):
        """Should raise BusinessRuleViolationException when trying to add member with workspace_owner role"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        owner_role = await _get_or_create_role(db_session, setup_factories, "workspace_owner")
        service = MemberService(db_session)

        # Act & Assert
        with pytest.raises(BusinessRuleViolationException) as exc_info:
            await service.add_member(
                workspace_id=workspace.id, user_id=user.id, role_id=owner_role.id
            )

        assert "workspace_owner" in exc_info.value.message.lower()

    async def test_update_member_role_to_owner_forbidden(self, db_session, setup_factories):
        """Should raise RextValidationException when updating member to workspace_owner role"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        member_user = await setup_factories["user"].create()
        member = await setup_factories["workspace_member"].create(
            workspace_id=workspace.id, user_id=member_user.id, status="active"
        )
        owner_role = await _get_or_create_role(db_session, setup_factories, "workspace_owner")
        service = MemberService(db_session)

        # Act & Assert
        with pytest.raises(RextValidationException) as exc_info:
            await service.update_member_role(
                workspace_id=workspace.id,
                member_id=member.id,
                new_role_id=owner_role.id,
                assigned_by_user_id=workspace.user_id,
            )

        assert "workspace_owner" in exc_info.value.message.lower()

    @pytest.mark.parametrize("role_name", ["editor", "viewer", "workspace_admin", "custom_role"])
    async def test_update_member_role_allowed_roles(self, db_session, setup_factories, role_name):
        """Should allow updating member to other valid workspace roles (editor, viewer, admin, custom)"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        member_user = await setup_factories["user"].create()
        member = await setup_factories["workspace_member"].create(
            workspace_id=workspace.id, user_id=member_user.id, status="active"
        )
        target_role = await _get_or_create_role(db_session, setup_factories, role_name)
        service = MemberService(db_session)

        # Act
        ret_member, ret_user, new_role, old_role = await service.update_member_role(
            workspace_id=workspace.id,
            member_id=member.id,
            new_role_id=target_role.id,
            assigned_by_user_id=workspace.user_id,
        )

        # Assert
        assert ret_member is not None
        assert ret_member.user_id == member_user.id
        assert new_role.id == target_role.id

