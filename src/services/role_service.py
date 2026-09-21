"""
Role Service - Business Logic for Role and Permission Management

This service encapsulates all business logic related to role management,
including role CRUD operations, permission assignments, and user role assignments.

Responsibilities:
- Role creation, update, and deletion
- Permission management for roles
- User role assignments and revocations
- Role hierarchy validation
- System role protection

Does NOT:
- Handle HTTP requests/responses (that's routes)
- Commit transactions (that's decorators/routes)
- Check authentication (that's decorators)
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.cache.decorators import invalidate_cache
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    RextValidationException,
)
from src.api.models.user_models.invitations import UserInvitations
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.utils.logger import logger


class RoleService:
    """Service for role and permission management"""

    # Standard workspace roles that cannot be deleted or modified
    PROTECTED_WORKSPACE_ROLES = {"workspace_owner", "workspace_admin", "editor", "viewer"}

    # Role names the auth layer trusts as super admin straight from the JWT
    # (route_decorators.require_permissions), so no API caller may create them.
    RESERVED_ROLE_NAMES = {"super_admin", "superadmin"}

    def __init__(self, db: AsyncSession):
        """
        Initialize RoleService.

        Args:
            db: Async database session
        """
        self.db = db

    async def create_role(
        self,
        name: str,
        display_name: str,
        description: Optional[str] = None,
        workspace_id: Optional[UUID] = None,
        permission_ids: Optional[List[UUID]] = None,
        hierarchy_level: int = 1,
        is_system_role: bool = False,
        is_workspace_role: bool = False,
        acting_user_id: Optional[UUID] = None,
    ) -> Role:
        """
        Create role with permissions.

        Business Rules:
        - Role name must be unique (lowercase, no spaces)
        - Display name must be unique
        - Hierarchy level: 0-100
        - System roles cannot be created via API (unless explicitly allowed)
        - Permissions are validated before assignment

        Args:
            name: Role name (will be lowercased)
            display_name: Human-readable name
            description: Optional description
            workspace_id: Optional workspace UUID for workspace-scoped roles
            permission_ids: List of permission UUIDs to assign
            hierarchy_level: 0-100 (default: 1)
            is_system_role: Whether this is a platform role (default: False)
            is_workspace_role: Whether this can be assigned to workspaces (default: False)

        Returns:
            Role object

        Raises:
            DuplicateResourceException: If name or display_name exists
            ResourceNotFoundException: If permissions not found
        """
        # Ensure lowercase name
        name = name.lower()

        if name in self.RESERVED_ROLE_NAMES:
            raise RextValidationException(
                message=f"Role name '{name}' is reserved",
                field_errors={"name": ["This role name is reserved by the platform"]},
            )

        # acting_user_id is None only for internal/system callers (seeding,
        # OAuth bootstrap); API routes always pass the caller.
        if acting_user_id is not None:
            from src.utils.rbac_utils import assert_can_grant_role_level

            await assert_can_grant_role_level(
                self.db, acting_user_id, hierarchy_level, action="create"
            )

        # Check name uniqueness
        name_result = await self.db.execute(select(Role).where(Role.name == name))
        if name_result.scalar_one_or_none():
            raise DuplicateResourceException(
                message="Role with this name already exists",
                resource_type="role",
                conflicting_field="name",
                conflicting_value=name,
            )

        # Check display_name uniqueness
        display_result = await self.db.execute(
            select(Role).where(Role.display_name == display_name)
        )
        if display_result.scalar_one_or_none():
            raise DuplicateResourceException(
                message="Role with this display name already exists",
                resource_type="role",
                conflicting_field="display_name",
                conflicting_value=display_name,
            )

        # Create role
        new_role = Role(
            name=name,
            display_name=display_name,
            description=description,
            hierarchy_level=hierarchy_level,
            is_system_role=is_system_role,
            is_workspace_role=is_workspace_role,
            created_at=datetime.now(timezone.utc),
        )

        self.db.add(new_role)
        await self.db.flush()
        await self.db.refresh(new_role)

        # Assign permissions if provided
        if permission_ids:
            await self.update_role_permissions(new_role.id, permission_ids)

        logger.info(
            f"Role created: {new_role.name}",
            extra={"role_id": str(new_role.id), "hierarchy_level": hierarchy_level},
        )

        return new_role

    def _is_protected_role(self, role: Role) -> bool:
        """
        Check if a role is protected from modification/deletion.

        Protected roles include:
        - Platform/system roles (is_system_role=True)
        - Standard workspace roles (workspace_owner, workspace_admin, editor, viewer)

        Args:
            role: Role object to check

        Returns:
            True if role is protected, False otherwise
        """
        return role.is_system_role or role.name in self.PROTECTED_WORKSPACE_ROLES

    async def update_role(
        self,
        role_id: UUID,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        hierarchy_level: Optional[int] = None,
        acting_user_id: Optional[UUID] = None,
    ) -> Role:
        """
        Update role properties.

        Business Rules:
        - Cannot update system roles
        - Cannot change role name (immutable)
        - Display name must remain unique
        - Hierarchy level: 0-100

        Args:
            role_id: Role UUID
            display_name: New display name
            description: New description
            hierarchy_level: New hierarchy level (0-100)

        Returns:
            Updated Role object

        Raises:
            ResourceNotFoundException: If role not found
            RextAPIException: If trying to update system role
            DuplicateResourceException: If display_name already exists
        """
        role = await self.get_role_by_id(role_id)

        # Check if protected role (system roles or standard workspace roles)
        if self._is_protected_role(role):
            raise RextValidationException(
                message=f"Cannot update protected role '{role.name}'",
                field_errors={
                    "role_id": [
                        "Protected roles (platform roles and standard workspace roles) cannot be modified"
                    ]
                },
            )

        # Block escalation: callers may only edit roles below their own level,
        # and may not raise a role to (or above) their own level.
        if acting_user_id is not None:
            from src.utils.rbac_utils import assert_can_grant_role_level

            await assert_can_grant_role_level(
                self.db, acting_user_id, role.hierarchy_level, action="modify"
            )
            if hierarchy_level is not None:
                await assert_can_grant_role_level(
                    self.db, acting_user_id, hierarchy_level, action="set"
                )

        # Check display_name uniqueness if being updated
        if display_name and display_name != role.display_name:
            display_result = await self.db.execute(
                select(Role).where(Role.display_name == display_name, Role.id != role_id)
            )
            if display_result.scalar_one_or_none():
                raise DuplicateResourceException(
                    message="Role with this display name already exists",
                    resource_type="role",
                    conflicting_field="display_name",
                    conflicting_value=display_name,
                )

        # Update fields
        if display_name is not None:
            role.display_name = display_name

        if description is not None:
            role.description = description

        if hierarchy_level is not None:
            if hierarchy_level < 0 or hierarchy_level > 100:
                raise RextValidationException(
                    message="Hierarchy level must be between 0 and 100",
                    field_errors={"hierarchy_level": ["Must be 0-100"]},
                )
            role.hierarchy_level = hierarchy_level

        role.updated_at = datetime.now(timezone.utc)

        await self.db.flush()
        await self.db.refresh(role)

        logger.info(f"Role updated: {role.name}", extra={"role_id": str(role.id)})

        return role

    async def delete_role(
        self,
        role_id: UUID,
        reassign_to: Optional[UUID] = None,
        acting_user_id: Optional[UUID] = None,
    ) -> None:
        """
        Delete role with user reassignment.

        Business Rules:
        - Cannot delete system roles
        - Cannot delete roles assigned to users (unless reassignment provided)
        - If reassign_to provided, reassign all users to new role
        - Deletes all role-permission relationships

        Args:
            role_id: Role UUID
            reassign_to: Optional role UUID to reassign users to

        Raises:
            ResourceNotFoundException: If role not found
            RextAPIException: If system role
            RextValidationException: If role in use and no reassignment
        """
        role = await self.get_role_by_id(role_id)

        # Check if protected role (system roles or standard workspace roles)
        if self._is_protected_role(role):
            raise RextValidationException(
                message=f"Cannot delete protected role '{role.name}'",
                field_errors={
                    "role_id": [
                        "Protected roles (platform roles and standard workspace roles) cannot be deleted"
                    ]
                },
            )

        # Block deleting a role at or above the caller's own level.
        if acting_user_id is not None:
            from src.utils.rbac_utils import assert_can_grant_role_level

            await assert_can_grant_role_level(
                self.db, acting_user_id, role.hierarchy_level, action="delete"
            )

        # Check if role is assigned to users
        user_roles_result = await self.db.execute(
            select(UserRole).where(UserRole.role_id == role_id)
        )
        user_roles = user_roles_result.scalars().all()
        holder_ids = {user_role.user_id for user_role in user_roles}

        # Invitations also FK this role (ondelete=RESTRICT, role_id NOT NULL),
        # so they block the delete exactly like user_roles do and must be
        # reassigned too - including accepted ones, which are kept as history.
        invitation_count = await self.db.scalar(
            select(func.count())
            .select_from(UserInvitations)
            .where(UserInvitations.role_id == role_id)
        )

        if user_roles or invitation_count:
            if not reassign_to:
                raise RextValidationException(
                    message=(
                        f"Cannot delete role assigned to {len(user_roles)} user(s) "
                        f"and {invitation_count} invitation(s). Provide reassign_to role."
                    ),
                    field_errors={"role_id": ["Role in use, reassignment required"]},
                )

            # Validate reassignment role exists
            reassign_role = await self.get_role_by_id(reassign_to)

            # Reassignment grants reassign_role to every holder, so it is a
            # role assignment and must respect the caller's hierarchy level.
            if acting_user_id is not None:
                from src.utils.rbac_utils import assert_can_grant_role_level

                await assert_can_grant_role_level(
                    self.db,
                    acting_user_id,
                    reassign_role.hierarchy_level,
                    action="reassign users to",
                )

            # Reassign all users
            for user_role in user_roles:
                user_role.role_id = reassign_to
                user_role.assigned_at = datetime.now(timezone.utc)

            if invitation_count:
                await self.db.execute(
                    update(UserInvitations)
                    .where(UserInvitations.role_id == role_id)
                    .values(role_id=reassign_to)
                )

            await self.db.flush()

            logger.info(
                f"Reassigned {len(user_roles)} users and {invitation_count} invitations "
                f"from {role.name} to {reassign_role.name}",
                extra={"role_id": str(role_id), "reassign_to": str(reassign_to)},
            )

        # Bulk-delete role permissions
        await self.db.execute(delete(RolePermission).where(RolePermission.role_id == role_id))

        # Delete the role
        await self.db.delete(role)

        # Without this, everyone reassigned off the deleted role keeps its old
        # permission set until the TTL lapses - and reassignment is usually a
        # downgrade.
        for holder_id in holder_ids:
            await invalidate_cache(f"user:permissions:{holder_id}:*")

        logger.info(f"Role deleted: {role.name}", extra={"role_id": str(role_id)})

    async def assign_role(
        self,
        user_id: UUID,
        role_id: UUID,
        workspace_id: Optional[UUID] = None,
        is_primary: bool = False,
        assigned_by_user_id: Optional[UUID] = None,
    ) -> UserRole:
        """
        Assign role to user.

        Business Rules:
        - Role must exist
        - If workspace-scoped, user must be workspace member
        - Idempotent: Returns existing assignment if already assigned
        - Hierarchy validation (if assignee provided)

        Args:
            user_id: User UUID
            role_id: Role UUID
            workspace_id: Optional workspace UUID
            is_primary: Whether this is the primary role
            assigned_by_user_id: UUID of user making the assignment

        Returns:
            UserRole object

        Raises:
            ResourceNotFoundException: If role or user not found
            RextValidationException: If user not workspace member
        """
        # Validate role exists
        role = await self.get_role_by_id(role_id)

        # A workspace role with no workspace_id lands in the global bucket that
        # get_user_permissions unions into EVERY workspace, so it silently
        # grants that role everywhere. The admin role dialog used to send
        # workspace_id = null, which is how those rows appeared.
        # Same rule as MemberService: ownership is transferred, never assigned.
        if role.name.lower() == "workspace_owner":
            raise RextValidationException(
                message="Cannot assign workspace_owner role",
                field_errors={
                    "role_id": ["The workspace_owner role cannot be assigned to members"]
                },
            )

        if role.is_workspace_role and workspace_id is None:
            raise RextValidationException(
                message=f"Role '{role.name}' is workspace-scoped and requires a workspace",
                field_errors={"workspace_id": ["This role must be assigned within a workspace"]},
            )

        # Block escalation. Platform-wide grants must be strictly below the
        # assigner's global level (an admin cannot hand anyone, including
        # themselves, an admin- or super-admin-level role); workspace-scoped
        # grants may reach, never exceed, the assigner's level there.
        if assigned_by_user_id is not None:
            from src.utils.rbac_utils import assert_can_grant_role_level, is_user_super_admin

            # Hierarchy first: a caller can only grant a role below their level
            # (workspace grants may reach, never exceed, their level).
            await assert_can_grant_role_level(
                self.db,
                assigned_by_user_id,
                role.hierarchy_level,
                workspace_id=workspace_id,
                allow_equal=workspace_id is not None,
                action="assign",
            )

            # SEC-RBAC-05: even for a grantable level, block self-assignment so a
            # caller cannot hand themselves a role they just crafted. Super admins
            # are exempt (bootstrap / recovery).
            if assigned_by_user_id == user_id and not await is_user_super_admin(
                self.db, assigned_by_user_id
            ):
                raise RextValidationException(
                    message="You cannot assign a role to your own account.",
                    field_errors={"user_id": ["Self-assignment is not permitted"]},
                )

        # If workspace-scoped, validate workspace and membership
        if workspace_id:
            workspace_result = await self.db.execute(
                select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)
            )
            workspace = workspace_result.scalar_one_or_none()

            if not workspace:
                raise ResourceNotFoundException(
                    resource_type="Workspace", resource_id=str(workspace_id)
                )

            # Check if user is member
            member_result = await self.db.execute(
                select(WorkspaceMembers).where(
                    WorkspaceMembers.workspace_id == workspace_id,
                    WorkspaceMembers.user_id == user_id,
                )
            )
            if not member_result.scalar_one_or_none():
                raise RextValidationException(
                    message="User is not a member of this workspace",
                    field_errors={"workspace_id": ["User not a member"]},
                )

        # Check if already assigned (idempotent)
        existing_result = await self.db.execute(
            select(UserRole).where(
                UserRole.user_id == user_id,
                UserRole.role_id == role_id,
                UserRole.workspace_id == workspace_id,
            )
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            logger.info(
                f"Role {role.name} already assigned to user {user_id}",
                extra={"user_id": str(user_id), "role_id": str(role_id)},
            )
            return existing

        # One role per workspace: a second row would union both permission
        # sets, so an assignment replaces whatever the user holds there.
        if workspace_id:
            held_result = await self.db.execute(
                select(UserRole, Role)
                .join(Role, Role.id == UserRole.role_id)
                .where(UserRole.user_id == user_id, UserRole.workspace_id == workspace_id)
            )
            for held_user_role, held_role in held_result.all():
                # Same rule as MemberService.update_member_role.
                if held_role.name.lower() == "workspace_owner":
                    raise RextValidationException(
                        message="Cannot change role of workspace owner",
                        field_errors={"role_id": ["Workspace owner role is immutable"]},
                    )
                await self.db.delete(held_user_role)
            await self.db.flush()

        # Create assignment
        user_role = UserRole(
            user_id=user_id,
            role_id=role_id,
            workspace_id=workspace_id,
            assigned_by_user_id=assigned_by_user_id or user_id,
            is_primary=is_primary,
            assigned_at=datetime.now(timezone.utc),
        )

        self.db.add(user_role)
        await self.db.flush()
        await self.db.refresh(user_role)

        # Invalidate permissions cache for this user
        await invalidate_cache(f"user:permissions:{user_id}:*")

        logger.info(
            f"Role {role.name} assigned to user {user_id}",
            extra={
                "user_id": str(user_id),
                "role_id": str(role_id),
                "workspace_id": str(workspace_id) if workspace_id else None,
            },
        )

        return user_role

    async def revoke_role(
        self,
        user_id: UUID,
        role_id: UUID,
        workspace_id: Optional[UUID] = None,
        acting_user_id: Optional[UUID] = None,
    ) -> None:
        """
        Revoke role from user.

        Workspace-scoped roles are revoked outright: removing a member's last
        workspace role leaves them with none, and the Members table then shows
        "No role assigned". No fallback role is substituted - an admin who
        revokes a role means to remove that access, not to downgrade it.

        (The former platform-floor 'user' role no longer exists; every
        remaining global role - admin, support, super_admin - stays revocable,
        otherwise an admin could never be demoted.)

        Args:
            user_id: User UUID
            role_id: Role UUID
            workspace_id: Optional workspace UUID

        Raises:
            ResourceNotFoundException: If assignment not found
        """
        # Find the assignment
        query = select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role_id)

        if workspace_id:
            query = query.where(UserRole.workspace_id == workspace_id)
        else:
            query = query.where(UserRole.workspace_id.is_(None))

        result = await self.db.execute(query)
        user_role = result.scalar_one_or_none()

        if not user_role:
            raise ResourceNotFoundException(
                resource_type="UserRole",
                resource_id=f"user:{user_id},role:{role_id}",
                message="Role assignment not found",
            )

        # SEC-RBAC-08: revocation must respect hierarchy, exactly like assignment.
        # Otherwise an admin could strip a peer admin's role. Symmetric with
        # assign_role's assert_can_grant_role_level.
        if acting_user_id is not None:
            from src.utils.rbac_utils import assert_can_grant_role_level

            revoked_role = await self.get_role_by_id(role_id)
            await assert_can_grant_role_level(
                self.db,
                acting_user_id,
                revoked_role.hierarchy_level,
                workspace_id=workspace_id,
                allow_equal=workspace_id is not None,
                action="revoke",
            )

        role = await self.get_role_by_id(role_id)

        # Ownership lives in workspaces.user_id; this row only mirrors it and
        # MemberService.list_members re-creates it if missing.
        if role.name.lower() == "workspace_owner":
            raise RextValidationException(
                message=(
                    "The workspace owner role cannot be revoked. "
                    "Transfer workspace ownership instead."
                ),
                field_errors={"role_id": ["Workspace owner role is immutable"]},
            )

        # Delete the assignment
        await self.db.delete(user_role)
        await self.db.flush()

        # Invalidate permissions cache for this user
        await invalidate_cache(f"user:permissions:{user_id}:*")

        logger.info(
            f"Role revoked from user {user_id}",
            extra={
                "user_id": str(user_id),
                "role_id": str(role_id),
                "workspace_id": str(workspace_id) if workspace_id else None,
            },
        )

    # ------------------------------------------------------------------
    # Role permission mutations
    #
    # PUT (update_role_permissions), POST (add_permissions_to_role) and DELETE
    # (remove_permission_from_role) all go through the protected-role guard and
    # _write_role_permissions, resolving the approved technical dependency map
    # server-side. PermissionService delegates here, so there is no other
    # write path for role permissions.
    # ------------------------------------------------------------------

    def _ensure_permissions_mutable(self, role: Role) -> None:
        """Protected roles (system and standard workspace roles) keep fixed permissions."""
        if self._is_protected_role(role):
            raise RextValidationException(
                message=f"Cannot update permissions for protected role '{role.name}'",
                field_errors={
                    "role_id": [
                        "Protected roles (platform roles and standard workspace roles) permissions cannot be modified"
                    ]
                },
            )

    async def _ensure_caller_outranks(self, role: Role, acting_user_id: Optional[UUID]) -> None:
        """Only roles below the caller's own level may have their permissions changed."""
        if acting_user_id is None:
            return
        from src.utils.rbac_utils import assert_can_grant_role_level

        await assert_can_grant_role_level(
            self.db, acting_user_id, role.hierarchy_level, action="change permissions of"
        )

    async def _ensure_caller_can_grant(
        self, requested_names: set[str], acting_user_id: Optional[UUID]
    ) -> None:
        """
        A caller may only grant permissions they themselves hold (SEC-RBAC-05).

        Without this, an admin with role.manage_permissions could attach ANY
        permission (e.g. billing.manage) to a custom role and self-assign it,
        escalating past their own authority. Super admins are exempt.
        """
        if acting_user_id is None or not requested_names:
            return
        from src.utils.rbac_utils import get_user_permissions, is_user_super_admin

        if await is_user_super_admin(self.db, acting_user_id):
            return

        caller_perms = set(await get_user_permissions(self.db, acting_user_id, None))
        excess = {name for name in requested_names if name not in caller_perms}
        if excess:
            from src.api.middleware.exceptions import RextAuthorizationException

            raise RextAuthorizationException(
                message="You cannot grant permissions you do not hold yourself.",
                context={"excess_permissions": sorted(excess)},
            )

    async def _get_role_permission_map(self, role_id: UUID) -> Dict[str, UUID]:
        """Permission name -> id for everything currently granted to the role."""
        result = await self.db.execute(
            select(Permission.name, Permission.id)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
        )
        return {row[0]: row[1] for row in result.all()}

    async def _write_role_permissions(
        self, role: Role, target_names: set[str]
    ) -> tuple[list[str], list[str]]:
        """
        Make the role hold exactly ``target_names`` (already dependency-resolved).

        Adds/removes only the difference and invalidates the permission cache of
        the role's users. Names without a Permission row are skipped.

        Returns:
            (added_names, removed_names), both sorted
        """
        current = await self._get_role_permission_map(role.id)

        added: Dict[str, UUID] = {}
        missing = target_names - current.keys()
        if missing:
            rows = await self.db.execute(
                select(Permission.name, Permission.id).where(Permission.name.in_(list(missing)))
            )
            added = {row[0]: row[1] for row in rows.all()}

        removed = {name: pid for name, pid in current.items() if name not in target_names}

        if removed:
            await self.db.execute(
                delete(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id.in_(list(removed.values())),
                )
            )
        for perm_id in added.values():
            self.db.add(RolePermission(role_id=role.id, permission_id=perm_id))

        if added or removed:
            await self.db.flush()
            result = await self.db.execute(
                select(UserRole.user_id).where(UserRole.role_id == role.id)
            )
            for user_id in {row[0] for row in result.all()}:
                await invalidate_cache(f"user:permissions:{user_id}:*")

        return sorted(added), sorted(removed)

    async def update_role_permissions(
        self, role_id: UUID, permission_ids: List[UUID], acting_user_id: Optional[UUID] = None
    ) -> Role:
        """
        Replace a custom role's permissions (PUT).

        Business Rules:
        - Protected roles cannot be changed
        - All permission ids must exist
        - Technical prerequisites are resolved server-side and always granted,
          whatever the client sent

        Args:
            role_id: Role UUID
            permission_ids: List of permission UUIDs

        Returns:
            Updated Role object

        Raises:
            ResourceNotFoundException: If role or permissions not found
            RextValidationException: If the role is protected
        """
        from src.constants.permission_dependencies import resolve_permission_prerequisites

        role = await self.get_role_by_id(role_id)
        self._ensure_permissions_mutable(role)
        await self._ensure_caller_outranks(role, acting_user_id)

        requested_names: List[str] = []
        if permission_ids:
            perm_result = await self.db.execute(
                select(Permission.id, Permission.name).where(Permission.id.in_(permission_ids))
            )
            rows = perm_result.all()
            missing_ids = set(permission_ids) - {row[0] for row in rows}
            if missing_ids:
                raise ResourceNotFoundException(
                    resource_type="Permission", resource_id=str(next(iter(missing_ids)))
                )
            requested_names = [row[1] for row in rows]

        await self._ensure_caller_can_grant(set(requested_names), acting_user_id)

        added, removed = await self._write_role_permissions(
            role, set(resolve_permission_prerequisites(requested_names))
        )

        logger.info(
            f"Permissions updated for role {role.name}: +{len(added)} -{len(removed)}",
            extra={"role_id": str(role_id), "added": added, "removed": removed},
        )
        return role

    async def add_permissions_to_role(
        self, role_id: UUID, permission_ids: List[UUID], acting_user_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Grant permissions to a custom role (POST), keeping what it already holds.

        Unknown ids are counted as invalid instead of failing the request.
        Technical prerequisites of the resulting set are granted server-side.

        Returns:
            Dict with role_id, role_name, added_count, skipped_count,
            invalid_count and added_permissions (names actually granted,
            including auto-added prerequisites)
        """
        from src.constants.permission_dependencies import resolve_permission_prerequisites

        role = await self.get_role_by_id(role_id)
        self._ensure_permissions_mutable(role)
        await self._ensure_caller_outranks(role, acting_user_id)

        requested_ids = set(permission_ids)
        requested_names: set[str] = set()
        if requested_ids:
            result = await self.db.execute(
                select(Permission.id, Permission.name).where(Permission.id.in_(list(requested_ids)))
            )
            rows = result.all()
            requested_names = {row[1] for row in rows}
            invalid_count = len(requested_ids) - len(rows)
        else:
            invalid_count = 0

        await self._ensure_caller_can_grant(requested_names, acting_user_id)

        current = await self._get_role_permission_map(role.id)
        target = set(resolve_permission_prerequisites(sorted(current.keys() | requested_names)))
        added, _ = await self._write_role_permissions(role, target)

        logger.info(
            f"Permissions added to role {role.name}: {added}",
            extra={"role_id": str(role_id), "added": added, "invalid": invalid_count},
        )
        return {
            "role_id": str(role.id),
            "role_name": role.name,
            "added_count": len(added),
            "skipped_count": len(requested_names & current.keys()),
            "invalid_count": invalid_count,
            "added_permissions": added,
        }

    async def remove_permission_from_role(
        self, role_id: UUID, permission_id: UUID, acting_user_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Revoke a permission from a custom role (DELETE).

        Every held permission that technically depends on it is revoked too.
        Its own prerequisites are kept, so shared prerequisites survive
        (removing content.publish keeps content.read for content.create).

        Returns:
            Dict with role_id, role_name, permission_id, permission_name and
            removed_permissions (the permission plus cascaded dependents)

        Raises:
            ResourceNotFoundException: If the role or the assignment is not found
            RextValidationException: If the role is protected
        """
        from src.constants.permission_dependencies import remove_permission_with_dependents

        role = await self.get_role_by_id(role_id)
        self._ensure_permissions_mutable(role)
        await self._ensure_caller_outranks(role, acting_user_id)

        current = await self._get_role_permission_map(role.id)
        permission_name = next(
            (name for name, pid in current.items() if pid == permission_id), None
        )
        if permission_name is None:
            raise ResourceNotFoundException(
                message="Permission assignment not found",
                context={"role_id": str(role_id), "permission_id": str(permission_id)},
            )

        target = set(remove_permission_with_dependents(list(current), permission_name))
        _, removed = await self._write_role_permissions(role, target)

        logger.info(
            f"Permission {permission_name} revoked from role {role.name}: removed {removed}",
            extra={"role_id": str(role_id), "removed": removed},
        )
        return {
            "role_id": str(role.id),
            "role_name": role.name,
            "permission_id": str(permission_id),
            "permission_name": permission_name,
            "removed_permissions": removed,
        }

    async def get_role_hierarchy(
        self,
        workspace_id: Optional[UUID] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> Dict[str, Any]:
        """
        Get roles ordered by hierarchy level (descending) with pagination.

        Args:
            workspace_id: Optional workspace filter (future use)
            page: Page number (1-indexed)
            per_page: Items per page

        Returns:
            Dict with roles list and pagination metadata
        """
        base_query = select(Role).order_by(Role.hierarchy_level.desc())

        # Get total count
        count_result = await self.db.execute(select(func.count()).select_from(Role))
        total = count_result.scalar() or 0

        # Apply pagination
        offset = (page - 1) * per_page
        result = await self.db.execute(base_query.offset(offset).limit(per_page))
        roles = list(result.scalars().all())

        total_pages = (total + per_page - 1) // per_page if total > 0 else 0

        return {
            "roles": roles,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            },
        }

    async def get_user_roles(
        self, user_id: UUID, workspace_id: Optional[UUID] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all roles assigned to a user.

        Args:
            user_id: User UUID
            workspace_id: Optional workspace filter

        Returns:
            List of dicts with role and assignment details
        """
        query = (
            select(UserRole, Role, WorkspaceModel)
            .join(Role, UserRole.role_id == Role.id)
            .outerjoin(WorkspaceModel, UserRole.workspace_id == WorkspaceModel.id)
            .where(UserRole.user_id == user_id)
        )

        if workspace_id:
            query = query.where(UserRole.workspace_id == workspace_id)

        result = await self.db.execute(query)
        rows = result.all()

        roles_data = []
        for user_role, role, workspace in rows:
            if user_role.workspace_id is not None:
                if not workspace or getattr(workspace, "deleted_at", None) is not None:
                    continue
            roles_data.append(
                {
                    "id": str(user_role.id),
                    "role_id": str(role.id),
                    "role_name": role.name,
                    "role_display_name": role.display_name,
                    "hierarchy_level": role.hierarchy_level,
                    "is_workspace_role": role.is_workspace_role,
                    "workspace_id": str(user_role.workspace_id) if user_role.workspace_id else None,
                    "workspace_name": workspace.name if workspace else None,
                    "is_primary": user_role.is_primary,
                    "assigned_at": user_role.assigned_at.isoformat()
                    if user_role.assigned_at
                    else None,
                }
            )

        return roles_data

    async def get_role_with_permissions(self, role_id: UUID) -> Dict[str, Any]:
        """
        Get role with its permissions.

        Args:
            role_id: Role UUID

        Returns:
            Dict with role details and permissions list

        Raises:
            ResourceNotFoundException: If role not found
        """
        role = await self.get_role_by_id(role_id)

        # Get permissions
        permissions_result = await self.db.execute(
            select(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
        )
        permissions = permissions_result.scalars().all()

        role_data = role.to_dict()
        role_data["permissions"] = [
            {
                "id": str(perm.id),
                "name": perm.name,
                "display_name": perm.display_name,
                "resource": perm.resource,
                "action": perm.action,
            }
            for perm in permissions
        ]

        return role_data

    async def get_roles_by_ids(self, role_ids: list[UUID]) -> Dict[UUID, Role]:
        """
        Batch load roles by IDs.

        Args:
            role_ids: List of role UUIDs

        Returns:
            Dict mapping role_id -> Role object
        """
        if not role_ids:
            return {}

        result = await self.db.execute(select(Role).where(Role.id.in_(role_ids)))
        roles = result.scalars().all()

        return {role.id: role for role in roles}

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    async def get_role_by_id(self, role_id: UUID) -> Role:
        """
        Get role by ID or raise 404.

        Args:
            role_id: Role UUID

        Returns:
            Role object

        Raises:
            ResourceNotFoundException: If role not found
        """
        result = await self.db.execute(select(Role).where(Role.id == role_id))
        role = result.scalar_one_or_none()

        if not role:
            raise ResourceNotFoundException(resource_type="Role", resource_id=str(role_id))

        return role
