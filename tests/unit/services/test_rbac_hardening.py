"""
Authorization hardening tests for roles and role permissions (DB-backed).

Covers:
- hierarchy escalation through create / update / assign / reassign / workspace paths
- reserved and system roles
- the single dependency-aware permission mutation path (POST / PUT / DELETE)
- bulk add / bulk remove semantics
- protected role immutability
"""

from uuid import uuid4

import pytest
from sqlalchemy import select

from src.api.middleware.exceptions import RextAuthorizationException, RextValidationException
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.roles import Role
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.schema.role_schema import RoleCreate
from src.services.invitation_service import InvitationService
from src.services.member_service import MemberService
from src.services.permission_service import PermissionService
from src.services.role_service import RoleService
from src.utils.rbac_utils import is_user_super_admin


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


async def _create_role(db, level: int = 1, **kwargs) -> Role:
    name = _unique("role")
    return await RoleService(db).create_role(
        name=name, display_name=name.title(), hierarchy_level=level, **kwargs
    )


async def _user_at_level(db, factories, level: int):
    """A user holding one global role at the given hierarchy level."""
    user = await factories["user"].create()
    role = await _create_role(db, level)
    await RoleService(db).assign_role(user.id, role.id)
    return user


async def _permission(db, name: str) -> Permission:
    existing = await db.scalar(select(Permission).where(Permission.name == name))
    if existing:
        return existing
    resource, action = name.split(".", 1)
    permission = Permission(
        id=uuid4(), name=name, display_name=name, resource=resource, action=action
    )
    db.add(permission)
    await db.flush()
    return permission


async def _permission_ids(db, *names: str) -> list:
    return [(await _permission(db, name)).id for name in names]


async def _held(db, role_id) -> list[str]:
    rows = await db.execute(
        select(Permission.name)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role_id)
    )
    return sorted(row[0] for row in rows.all())


@pytest.mark.unit
class TestHierarchyEscalation:
    async def test_admin_cannot_create_role_at_or_above_own_level(self, db_session, setup_factories):
        admin = await _user_at_level(db_session, setup_factories, 80)

        for level in (100, 80):
            with pytest.raises(RextAuthorizationException):
                await _create_role(db_session, level, acting_user_id=admin.id)

        role = await _create_role(db_session, 79, acting_user_id=admin.id)
        assert role.hierarchy_level == 79

    async def test_admin_cannot_update_role_to_level_100(self, db_session, setup_factories):
        admin = await _user_at_level(db_session, setup_factories, 80)
        role = await _create_role(db_session, 10)
        service = RoleService(db_session)

        for level in (100, 80):
            with pytest.raises(RextAuthorizationException):
                await service.update_role(role.id, hierarchy_level=level, acting_user_id=admin.id)

        updated = await service.update_role(role.id, hierarchy_level=50, acting_user_id=admin.id)
        assert updated.hierarchy_level == 50

    async def test_admin_cannot_edit_role_above_own_level(self, db_session, setup_factories):
        admin = await _user_at_level(db_session, setup_factories, 80)
        higher_role = await _create_role(db_session, 90)

        with pytest.raises(RextAuthorizationException):
            await RoleService(db_session).update_role(
                higher_role.id, description="changed", acting_user_id=admin.id
            )

    async def test_admin_cannot_assign_level_100_role_to_self(self, db_session, setup_factories):
        admin = await _user_at_level(db_session, setup_factories, 80)
        service = RoleService(db_session)

        for level in (100, 80):
            role = await _create_role(db_session, level)
            with pytest.raises(RextAuthorizationException):
                await service.assign_role(admin.id, role.id, assigned_by_user_id=admin.id)

        assert await is_user_super_admin(db_session, admin.id) is False

    async def test_admin_cannot_escalate_via_delete_reassignment(self, db_session, setup_factories):
        admin = await _user_at_level(db_session, setup_factories, 80)
        service = RoleService(db_session)
        own_role = await _create_role(db_session, 5)
        await service.assign_role(admin.id, own_role.id)
        super_role = await _create_role(db_session, 100)

        with pytest.raises(RextAuthorizationException):
            await service.delete_role(
                own_role.id, reassign_to=super_role.id, acting_user_id=admin.id
            )

    async def test_admin_cannot_delete_role_at_or_above_own_level(self, db_session, setup_factories):
        admin = await _user_at_level(db_session, setup_factories, 80)
        service = RoleService(db_session)

        for level in (90, 80):
            role = await _create_role(db_session, level)
            with pytest.raises(RextAuthorizationException):
                await service.delete_role(role.id, acting_user_id=admin.id)

    async def test_admin_cannot_change_permissions_of_role_at_or_above_own_level(
        self, db_session, setup_factories
    ):
        admin = await _user_at_level(db_session, setup_factories, 80)
        service = RoleService(db_session)
        read = await _permission(db_session, "content.read")

        for level in (90, 80):
            role = await _create_role(db_session, level)
            with pytest.raises(RextAuthorizationException):
                await service.add_permissions_to_role(role.id, [read.id], acting_user_id=admin.id)
            with pytest.raises(RextAuthorizationException):
                await service.update_role_permissions(role.id, [read.id], acting_user_id=admin.id)
            with pytest.raises(RextAuthorizationException):
                await service.remove_permission_from_role(role.id, read.id, acting_user_id=admin.id)

        lower = await _create_role(db_session, 79)
        await service.add_permissions_to_role(lower.id, [read.id], acting_user_id=admin.id)
        assert await _held(db_session, lower.id) == ["content.read"]

    async def test_admin_cannot_escalate_via_workspace_member_role_change(
        self, db_session, setup_factories
    ):
        owner = await setup_factories["user"].create()
        workspace = await setup_factories["workspace"].create(user_id=owner.id)
        admin = await _user_at_level(db_session, setup_factories, 80)
        membership = WorkspaceMembers(
            id=uuid4(), workspace_id=workspace.id, user_id=admin.id, status="active"
        )
        db_session.add(membership)
        await db_session.flush()
        super_role = await _create_role(db_session, 100)

        with pytest.raises(RextAuthorizationException):
            await MemberService(db_session).update_member_role(
                workspace_id=workspace.id,
                member_id=membership.id,
                new_role_id=super_role.id,
                assigned_by_user_id=admin.id,
            )

    async def test_admin_cannot_escalate_via_workspace_invitation(self, db_session, setup_factories):
        owner = await setup_factories["user"].create()
        workspace = await setup_factories["workspace"].create(user_id=owner.id)
        admin = await _user_at_level(db_session, setup_factories, 80)
        super_role = await _create_role(db_session, 100)

        with pytest.raises(RextAuthorizationException):
            await InvitationService(db_session).create_invitation(
                email=f"{_unique('invitee')}@example.com",
                workspace_id=workspace.id,
                role_id=super_role.id,
                invited_by_user_id=admin.id,
            )

    async def test_super_admin_still_manages_lower_level_roles(self, db_session, setup_factories):
        super_admin = await _user_at_level(db_session, setup_factories, 100)
        target = await setup_factories["user"].create()

        role = await _create_role(db_session, 99, acting_user_id=super_admin.id)
        assignment = await RoleService(db_session).assign_role(
            target.id, role.id, assigned_by_user_id=super_admin.id
        )

        assert assignment.role_id == role.id


@pytest.mark.unit
class TestSystemRoleCreation:
    def test_role_create_schema_does_not_accept_is_system_role(self):
        payload = RoleCreate(name="custom_role", display_name="Custom Role", is_system_role=True)
        assert "is_system_role" not in payload.model_dump()

    async def test_reserved_super_admin_names_are_rejected(self, db_session):
        for name in ("superadmin", "SuperAdmin", "super_admin"):
            with pytest.raises(RextValidationException):
                await RoleService(db_session).create_role(
                    name=name, display_name=_unique("Reserved")
                )


@pytest.mark.unit
@pytest.mark.unit
class TestRolePermissionDependencies:
    async def test_post_add_applies_prerequisites(self, db_session):
        role = await _create_role(db_session)
        (publish_id,) = await _permission_ids(db_session, "content.publish")
        await _permission(db_session, "content.read")

        result = await RoleService(db_session).add_permissions_to_role(role.id, [publish_id])

        assert await _held(db_session, role.id) == ["content.publish", "content.read"]
        assert result["added_permissions"] == ["content.publish", "content.read"]
        assert result["added_count"] == 2

    async def test_permission_service_assign_uses_the_same_path(self, db_session):
        role = await _create_role(db_session)
        (publish_id,) = await _permission_ids(db_session, "content.publish")
        await _permission(db_session, "content.read")

        await PermissionService(db_session).assign_permissions_to_role(
            role_id=role.id, permission_ids=[publish_id]
        )

        assert await _held(db_session, role.id) == ["content.publish", "content.read"]

    async def test_put_applies_prerequisites_without_workflow_permissions(self, db_session):
        role = await _create_role(db_session)
        await _permission_ids(db_session, "content.read", "content.update")
        (publish_id,) = await _permission_ids(db_session, "content.publish")

        await RoleService(db_session).update_role_permissions(role.id, [publish_id])

        assert await _held(db_session, role.id) == ["content.publish", "content.read"]

    async def test_put_resolves_transitive_prerequisites(self, db_session):
        role = await _create_role(db_session)
        await _permission_ids(db_session, "user.read", "role.read", "workspace.read")
        ids = await _permission_ids(db_session, "user.manage_roles", "workspace.update")

        await RoleService(db_session).update_role_permissions(role.id, ids)

        assert await _held(db_session, role.id) == [
            "role.read",
            "user.manage_roles",
            "user.read",
            "workspace.read",
            "workspace.update",
        ]

    async def test_delete_prerequisite_cascades_to_dependents(self, db_session):
        role = await _create_role(db_session)
        service = RoleService(db_session)
        read = await _permission(db_session, "content.read")
        ids = await _permission_ids(
            db_session, "content.create", "content.publish", "integration.create", "integration.read"
        )
        await service.add_permissions_to_role(role.id, ids)

        result = await service.remove_permission_from_role(role.id, read.id)

        assert await _held(db_session, role.id) == ["integration.create", "integration.read"]
        assert result["removed_permissions"] == [
            "content.create",
            "content.publish",
            "content.read",
        ]

    async def test_delete_keeps_shared_prerequisites(self, db_session):
        role = await _create_role(db_session)
        service = RoleService(db_session)
        await _permission(db_session, "content.read")
        publish = await _permission(db_session, "content.publish")
        ids = await _permission_ids(db_session, "content.create")
        await service.add_permissions_to_role(role.id, ids + [publish.id])

        result = await service.remove_permission_from_role(role.id, publish.id)

        assert await _held(db_session, role.id) == [
            "content.create",
            "content.read",
        ]
        assert result["removed_permissions"] == ["content.publish"]

    async def test_delete_cascades_to_dependents_only(self, db_session):
        role = await _create_role(db_session)
        service = RoleService(db_session)
        await _permission_ids(db_session, "user.read", "member.read")
        user_read = await _permission(db_session, "user.read")
        ids = await _permission_ids(db_session, "member.invite", "user.update")
        await service.add_permissions_to_role(role.id, ids)

        await service.remove_permission_from_role(role.id, user_read.id)

        assert await _held(db_session, role.id) == [
            "member.invite",
            "member.read",
        ]

    async def test_bulk_add_applies_prerequisites_to_every_role(self, db_session):
        roles = [await _create_role(db_session) for _ in range(2)]
        await _permission(db_session, "content.read")
        ids = await _permission_ids(db_session, "content.publish")

        for role in roles:
            await RoleService(db_session).add_permissions_to_role(role.id, ids)

        for role in roles:
            assert await _held(db_session, role.id) == [
                "content.publish",
                "content.read",
            ]

    async def test_bulk_remove_preserves_shared_prerequisites(self, db_session):
        roles = [await _create_role(db_session) for _ in range(2)]
        await _permission(db_session, "content.read")
        create, publish = await _permission_ids(
            db_session, "content.create", "content.publish"
        )
        for role in roles:
            await RoleService(db_session).add_permissions_to_role(role.id, [create, publish])

        for role in roles:
            await RoleService(db_session).remove_permission_from_role(role.id, publish)

        for role in roles:
            assert await _held(db_session, role.id) == ["content.create", "content.read"]


async def _standard_workspace_role(db, name: str = "editor") -> Role:
    existing = await db.scalar(select(Role).where(Role.name == name))
    if existing:
        return existing
    role = Role(
        id=uuid4(),
        name=name,
        display_name=_unique("Editor"),
        hierarchy_level=30,
        is_system_role=False,
        is_workspace_role=True,
    )
    db.add(role)
    await db.flush()
    return role


@pytest.mark.unit
class TestProtectedRoles:
    async def test_standard_workspace_role_cannot_be_edited(self, db_session):
        role = await _standard_workspace_role(db_session)
        with pytest.raises(RextValidationException):
            await RoleService(db_session).update_role(role.id, description="changed")

    async def test_standard_workspace_role_cannot_be_deleted(self, db_session):
        role = await _standard_workspace_role(db_session)
        with pytest.raises(RextValidationException):
            await RoleService(db_session).delete_role(role.id)

    async def test_protected_role_permissions_cannot_be_mutated(self, db_session):
        read = await _permission(db_session, "content.read")
        service = RoleService(db_session)
        permission_service = PermissionService(db_session)

        for role in (
            await _standard_workspace_role(db_session),
            await _create_role(db_session, 1, is_system_role=True),
        ):
            with pytest.raises(RextValidationException):
                await service.update_role_permissions(role.id, [read.id])
            with pytest.raises(RextValidationException):
                await service.add_permissions_to_role(role.id, [read.id])
            with pytest.raises(RextValidationException):
                await service.remove_permission_from_role(role.id, read.id)
            with pytest.raises(RextValidationException):
                await permission_service.assign_permissions_to_role(
                    role_id=role.id, permission_ids=[read.id]
                )
            with pytest.raises(RextValidationException):
                await permission_service.revoke_permission_from_role(
                    role_id=role.id, permission_id=read.id
                )

    async def test_system_role_cannot_be_edited_or_deleted(self, db_session):
        role = await _create_role(db_session, 1, is_system_role=True)
        service = RoleService(db_session)

        with pytest.raises(RextValidationException):
            await service.update_role(role.id, description="changed")
        with pytest.raises(RextValidationException):
            await service.delete_role(role.id)
