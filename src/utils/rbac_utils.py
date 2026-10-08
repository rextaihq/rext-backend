"""
Role-Based Access Control (RBAC) Utilities

Provides permission checking and enforcement for workspace-scoped and global operations.
All functions are async-compatible for use with FastAPI AsyncSession.

Database Schema (Existing):
- roles: Role definitions (admin, editor, viewer, etc.)
- permissions: Permission definitions (content.create, content.delete, etc.)
- role_permissions: Many-to-many relationship between roles and permissions
- user_roles: User role assignments (can be workspace-scoped or global)

Permission Naming Convention:
    {resource}.{action}

    Resources: workspace, content, member, role, permission, etc.
    Actions: create, read, update, delete, publish, approve, invite, manage, etc.

    Examples:
    - workspace.delete (delete workspace)
    - content.publish (publish content)
    - member.invite (invite members)

Usage:
    from src.utils.rbac_utils import check_permission, require_permission

    # Check if user has permission
    has_perm = await check_permission(db, user_id, "content.delete", workspace_id)

    # Require permission (raises exception if denied)
    await require_permission(db, user_id, "content.delete", workspace_id)
"""

from typing import List, Optional, Tuple
from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Circular import fix: Move RextAuthorizationException to inside functions
from src.api.lib.logger import auto_logger
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole

logger = auto_logger()

ADMIN_HIERARCHY_THRESHOLD = 80
SUPER_ADMIN_HIERARCHY_THRESHOLD = 100


async def check_permission(
    db: AsyncSession, user_id: UUID, permission_name: str, workspace_id: Optional[UUID] = None
) -> bool:
    """
    Check if user has a specific permission (cached).

    Delegates to get_user_permissions() which is Redis-cached (5-minute TTL).
    This means all permission checks for the same user/workspace combo hit
    the cache after the first call, eliminating N+1 query patterns in
    check_any_permission() and check_all_permissions().

    Args:
        db: AsyncSession database session
        user_id: User UUID
        permission_name: Permission name (e.g., "content.delete", "workspace.update")
        workspace_id: Optional workspace UUID for workspace-scoped permissions.

    Returns:
        True if user has the permission, False otherwise

    Example:
        >>> has_perm = await check_permission(db, user_id, "content.delete", workspace_id)
        >>> if has_perm:
        >>>     # User can delete content
        >>>     pass
    """
    permissions = await get_user_permissions(db, user_id, workspace_id)
    has_permission = permission_name in permissions

    logger.debug(
        f"Permission check: user={user_id}, permission={permission_name}, "
        f"workspace={workspace_id}, result={has_permission} (cached)"
    )

    return has_permission


async def check_any_permission(
    db: AsyncSession,
    user_id: UUID,
    permission_names: List[str],
    workspace_id: Optional[UUID] = None,
) -> bool:
    """
    Check if user has ANY of the specified permissions (OR logic).

    Args:
        db: AsyncSession database session
        user_id: User UUID
        permission_names: List of permission names to check
        workspace_id: Optional workspace UUID for workspace-scoped checks

    Returns:
        True if user has at least ONE of the permissions, False otherwise

    Example:
        >>> has_any = await check_any_permission(
        >>>     db, user_id, ["content.update", "content.publish"], workspace_id
        >>> )
        >>> # Returns True if user has EITHER content.update OR content.publish
    """
    for permission_name in permission_names:
        if await check_permission(db, user_id, permission_name, workspace_id):
            return True
    return False


async def check_all_permissions(
    db: AsyncSession,
    user_id: UUID,
    permission_names: List[str],
    workspace_id: Optional[UUID] = None,
) -> bool:
    """
    Check if user has ALL of the specified permissions (AND logic).

    Args:
        db: AsyncSession database session
        user_id: User UUID
        permission_names: List of permission names to check
        workspace_id: Optional workspace UUID for workspace-scoped checks

    Returns:
        True if user has ALL of the permissions, False otherwise

    Example:
        >>> has_all = await check_all_permissions(
        >>>     db, user_id, ["content.update", "content.publish"], workspace_id
        >>> )
        >>> # Returns True only if user has BOTH content.update AND content.publish
    """
    for permission_name in permission_names:
        if not await check_permission(db, user_id, permission_name, workspace_id):
            return False
    return True


async def require_permission(
    db: AsyncSession,
    user_id: UUID,
    permission_name: str,
    workspace_id: Optional[UUID] = None,
    resource_name: Optional[str] = None,
) -> None:
    """
    Require user to have a permission, raise exception if not.

    This is a convenience function that checks permission and raises
    RextAuthorizationException if the user lacks the required permission.

    Args:
        db: AsyncSession database session
        user_id: User UUID
        permission_name: Required permission name
        workspace_id: Optional workspace UUID for workspace-scoped check
        resource_name: Optional resource name for better error messages (e.g., "content", "workspace")

    Raises:
        RextAuthorizationException: If user lacks the required permission

    Example:
        >>> await require_permission(db, user_id, "content.delete", workspace_id, "content")
        >>> # Raises exception if user doesn't have content.delete permission
        >>> # Otherwise, continues execution
    """
    has_permission = await check_permission(db, user_id, permission_name, workspace_id)

    if not has_permission:
        from src.api.middleware.exceptions import RextAuthorizationException

        logger.warning(
            f"Permission denied: user={user_id}, permission={permission_name}, "
            f"workspace={workspace_id}, resource={resource_name}"
        )

        raise RextAuthorizationException(
            message="You do not have permission to perform this action",
            context={
                "required_permission": permission_name,
                "resource": resource_name,
                "workspace_id": str(workspace_id) if workspace_id else None,
            },
        )


async def get_user_permissions(
    db: AsyncSession, user_id: UUID, workspace_id: Optional[UUID] = None
) -> List[str]:
    """
    Get all permissions for a user (cached).

    Returns a list of all permission names that the user has access to,
    either through workspace-scoped roles or global roles.

    This function is cached for 5 minutes to improve performance on permission checks.

    Args:
        db: AsyncSession database session
        user_id: User UUID
        workspace_id: Optional workspace UUID. If provided, returns permissions
                     from both workspace-scoped and global roles.
                     If None, returns only global permissions.

    Returns:
        List of permission names (e.g., ["content.create", "content.delete", "topic.read"])

    Example:
        >>> permissions = await get_user_permissions(db, user_id, workspace_id)
        >>> # ["content.create", "content.read", "content.update", "content.delete", ...]
    """
    # Import inside function: cache client initializes after app startup
    from src.api.cache.redis_client import cache

    cache_key = f"user:permissions:{user_id}:{workspace_id or 'global'}"

    if cache.is_enabled:
        cached_perms = await cache.get(cache_key)
        if cached_perms is not None:
            logger.debug(f"Cache hit for permissions: user={user_id}, workspace={workspace_id}")
            return cached_perms

    # Cache miss - query database
    query = (
        select(Permission.name)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id)
        .distinct()
    )

    if workspace_id:
        # Include both workspace-scoped and global permissions
        query = query.where(
            (UserRole.workspace_id == workspace_id) | (UserRole.workspace_id.is_(None))
        )
    else:
        # Only global permissions
        query = query.where(UserRole.workspace_id.is_(None))

    result = await db.execute(query)
    permissions = result.scalars().all()

    # Global Permission Bridge: Ensure both dot and colon notation are supported.
    # Backend uses 'resource.action', FE sometimes uses 'resource:action'.
    # We return the union of both to prevent desync issues.
    permissions_list = list(permissions)
    colon_perms = [p.replace(".", ":") for p in permissions_list if "." in p]
    if colon_perms:
        permissions_list.extend(colon_perms)

    # Ensure uniqueness and sort for stability
    permissions_list = sorted(list(set(permissions_list)))

    # WORKSPACE OWNER FALLBACK:
    # If a user is the primary owner of the workspace record, they must ALWAYS
    # have owner permissions, even if the user_roles table is missing the mapping.
    if workspace_id:
        from src.api.models.workspace_models.workspace_model import WorkspaceModel

        # Check if user is the record owner
        ws_query = select(WorkspaceModel.user_id).where(WorkspaceModel.id == workspace_id)
        ws_result = await db.execute(ws_query)
        owner_id = ws_result.scalar()

        if owner_id == user_id:
            logger.info(
                f"User {user_id} is record owner of workspace {workspace_id}; ensuring owner permissions."
            )
            # Fetch the permissions defined for the workspace_owner role
            # This ensures they get EXACTLY what an owner should have
            owner_perms_query = (
                select(Permission.name)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(Role, Role.id == RolePermission.role_id)
                .where(Role.name == "workspace_owner")
            )
            owner_perms_res = await db.execute(owner_perms_query)
            owner_perms = owner_perms_res.scalars().all()

            # Use set for union to avoid duplicates
            permissions_list = list(set(permissions_list) | set(owner_perms))

    logger.debug(
        f"Retrieved {len(permissions_list)} permissions for user={user_id}, workspace={workspace_id}"
    )

    # Cache the result for 5 minutes
    if cache.is_enabled:
        await cache.set(cache_key, permissions_list, ttl=300)

    return permissions_list


async def get_user_roles(
    db: AsyncSession, user_id: UUID, workspace_id: Optional[UUID] = None
) -> List[Tuple[Role, Optional[UUID]]]:
    """
    Get all roles assigned to user.

    Returns a list of tuples containing (Role object, workspace_id).
    The workspace_id in the tuple indicates where the role applies:
    - None = global role (applies everywhere)
    - UUID = workspace-scoped role (applies only in that workspace)

    Args:
        db: AsyncSession database session
        user_id: User UUID
        workspace_id: Optional workspace UUID to filter by.
                     If provided, returns both workspace-scoped and global roles.
                     If None, returns only global roles.

    Returns:
        List of (Role, Optional[UUID]) tuples

    Example:
        >>> roles = await get_user_roles(db, user_id, workspace_id)
        >>> # [(Role(name="editor"), UUID("...")), (Role(name="admin"), None)]
        >>> for role, ws_id in roles:
        >>>     if ws_id:
        >>>         print(f"{role.name} in workspace {ws_id}")
        >>>     else:
        >>>         print(f"{role.name} (global)")
    """
    query = (
        select(Role, UserRole.workspace_id)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
    )

    if workspace_id:
        # Include both workspace-scoped and global roles
        query = query.where(
            (UserRole.workspace_id == workspace_id) | (UserRole.workspace_id.is_(None))
        )
    else:
        # Only global roles
        query = query.where(UserRole.workspace_id.is_(None))

    result = await db.execute(query)
    rows = result.all()

    roles = [(row[0], row[1]) for row in rows]

    # WORKSPACE OWNER FALLBACK:
    # Ensure the workspace_owner role is present if the user is the record owner
    if workspace_id:
        from src.api.models.workspace_models.workspace_model import WorkspaceModel

        # Check if they are already assigned via UserRole
        has_owner_role = any(
            r.name == "workspace_owner" and ws_id == workspace_id for r, ws_id in roles
        )

        if not has_owner_role:
            ws_query = select(WorkspaceModel.user_id).where(WorkspaceModel.id == workspace_id)
            ws_res = await db.execute(ws_query)
            owner_id = ws_res.scalar()

            if owner_id == user_id:
                # User is owner but role mapping is missing - fetch the role object and add it
                logger.warning(
                    f"User {user_id} is owner of {workspace_id} but missing workspace_owner role mapping. Fixing in response."
                )
                role_query = select(Role).where(Role.name == "workspace_owner")
                role_res = await db.execute(role_query)
                wo_role = role_res.scalar_one_or_none()
                if wo_role:
                    roles.append((wo_role, workspace_id))

    logger.debug(f"Retrieved {len(roles)} roles for user={user_id}, workspace={workspace_id}")

    return roles


async def is_user_admin(db: AsyncSession, user_id: UUID, workspace_id: UUID | None = None) -> bool:
    """
    Check if a user has an admin-level role based on hierarchy_level.

    A user is considered an admin if they have any role with
    hierarchy_level >= ADMIN_HIERARCHY_THRESHOLD (80).

    Args:
        db: Async database session
        user_id: UUID of the user to check
        workspace_id: Optional workspace UUID. If provided, checks for
                      global admins OR admins specifically within that workspace.
                      If None, only checks global (non-workspace) roles.

    Returns:
        True if the user has an admin-level role, False otherwise.
    """
    query = (
        select(UserRole)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id == user_id, Role.hierarchy_level >= ADMIN_HIERARCHY_THRESHOLD)
    )

    if workspace_id is None:
        # Only check global roles
        query = query.where(UserRole.workspace_id.is_(None))
    else:
        # Check global roles OR specifically this workspace
        from sqlalchemy import or_

        query = query.where(
            or_(UserRole.workspace_id.is_(None), UserRole.workspace_id == workspace_id)
        )

    # Any one such role is enough. An account can hold more than one (admin beside
    # super admin, or the same role in two rows: nothing in the table stops a second
    # row outside a workspace), and asking for "the one row" raised on those accounts.
    result = await db.execute(query.limit(1))
    return result.first() is not None


async def is_user_super_admin(db: AsyncSession, user_id: UUID) -> bool:
    """
    Check if a user has a super-admin level role (hierarchy_level >= 100).
    Super admin roles are always global (workspace_id IS NULL).
    """
    query = (
        select(UserRole)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            UserRole.user_id == user_id,
            Role.hierarchy_level >= SUPER_ADMIN_HIERARCHY_THRESHOLD,
            UserRole.workspace_id.is_(None),
        )
        .limit(1)
    )

    # One row is enough; see is_user_admin for why "the one row" can't be asked for.
    result = await db.execute(query)
    return result.first() is not None


async def holds_global_role(db: AsyncSession, user_id: UUID, role_names: tuple[str, ...]) -> bool:
    """
    Check if a user holds one of the named roles outside any workspace.

    Asked of the database on every call, like the checks above: a role given or
    taken away counts from that moment, whatever the caller's token was issued with.
    A workspace role of the same name never matches.
    """
    if not role_names:
        return False

    query = (
        select(UserRole)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            UserRole.user_id == user_id,
            Role.name.in_(role_names),
            UserRole.workspace_id.is_(None),
        )
        .limit(1)
    )

    result = await db.execute(query)
    return result.first() is not None


async def get_user_max_hierarchy_level(
    db: AsyncSession, user_id: UUID, workspace_id: Optional[UUID] = None
) -> int:
    """
    Highest hierarchy_level among a user's roles (0 when they have none).

    With workspace_id None only global roles count. With a workspace_id, global
    roles plus roles scoped to that workspace count, and the workspace record
    owner counts at least as workspace_owner (mirrors the owner fallback in
    get_user_permissions).
    """
    from sqlalchemy import func, or_

    scope = UserRole.workspace_id.is_(None)
    if workspace_id is not None:
        scope = or_(scope, UserRole.workspace_id == workspace_id)

    level = (
        await db.scalar(
            select(func.max(Role.hierarchy_level))
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id, scope)
        )
        or 0
    )

    if workspace_id is not None:
        from src.api.models.workspace_models.workspace_model import WorkspaceModel

        owner_id = await db.scalar(
            select(WorkspaceModel.user_id).where(WorkspaceModel.id == workspace_id)
        )
        if owner_id == user_id:
            owner_level = (
                await db.scalar(select(Role.hierarchy_level).where(Role.name == "workspace_owner"))
                or 0
            )
            level = max(level, owner_level)

    return level


async def assert_can_grant_role_level(
    db: AsyncSession,
    caller_user_id: UUID,
    role_level: int,
    *,
    workspace_id: Optional[UUID] = None,
    allow_equal: bool = False,
    action: str = "assign",
) -> None:
    """
    Block hierarchy escalation when creating, editing or granting a role.

    The role's level must be strictly below the caller's highest level
    (an admin at 80 may grant 79, never 80 or 100). ``allow_equal`` relaxes
    this to "not above" for peer grants such as workspace invitations.
    Super admin is detected as hierarchy_level >= 100, so no caller can mint
    or hand out a super-admin-level role through this rule.

    Raises:
        RextAuthorizationException: If the role level is not grantable.
    """
    caller_level = await get_user_max_hierarchy_level(db, caller_user_id, workspace_id)
    allowed = role_level <= caller_level if allow_equal else role_level < caller_level
    if allowed:
        return

    from src.api.middleware.exceptions import RextAuthorizationException

    logger.warning(
        f"Blocked hierarchy escalation: user {caller_user_id} (level {caller_level}) "
        f"tried to {action} a level-{role_level} role"
    )
    raise RextAuthorizationException(
        message=(
            f"You cannot {action} a role at hierarchy level {role_level}; "
            f"your highest level is {caller_level}."
        ),
        context={
            "role_level": role_level,
            "caller_level": caller_level,
            "action": action,
            "workspace_id": str(workspace_id) if workspace_id else None,
        },
    )


async def assert_target_manageable_by(
    db: AsyncSession,
    caller_user_id: UUID,
    target_user_id: UUID,
    action: str = "modify",
) -> None:
    """
    Protect Super Admin accounts from every User Management action.

    A Super Admin stays visible in the Users list, but impersonation, suspend,
    ban, delete, edit and role changes against one are always refused here —
    regardless of who is asking, including another Super Admin. Super Admin
    accounts are managed out of band (seed / DB / CLI), not from this screen.

    ``caller_user_id`` is kept for the audit log line and future policy tweaks.

    Args:
        db: Async database session
        caller_user_id: The admin performing the action
        target_user_id: The user being acted on
        action: Verb used in the error message (e.g. "delete", "suspend")

    Raises:
        RextAuthorizationException: If the target is a Super Admin.
    """
    if not await is_user_super_admin(db, target_user_id):
        return

    from src.api.middleware.exceptions import RextAuthorizationException

    logger.warning(
        f"Blocked '{action}' on Super Admin {target_user_id} (requested by {caller_user_id})"
    )
    raise RextAuthorizationException(
        message=f"Super Admin accounts are protected. You cannot {action} a Super Admin account.",
        context={"target_user_id": str(target_user_id), "action": action},
    )


async def check_permission_or_admin(
    db: AsyncSession,
    user_id: UUID,
    permission_name: str,
    raise_on_deny: bool = True,
    use_http_exception: bool = True,
) -> bool:
    """
    Check if user has a specific permission or is an admin/super_admin.

    This is the single source of truth for the "check permission or admin bypass"
    pattern used across route helpers and services.

    Args:
        db: AsyncSession database session
        user_id: User UUID
        permission_name: Required permission name (e.g., "role.read", "permission.create")
        raise_on_deny: If True, raises an exception when the user lacks permission.
            If False, returns False silently.
        use_http_exception: If True and raise_on_deny is True, raises HTTPException(403).
            If False and raise_on_deny is True, raises RextAuthorizationException.
            This parameter is ignored when raise_on_deny is False.

    Returns:
        True if user has the permission or is admin.

    Raises:
        HTTPException(403): If raise_on_deny=True and use_http_exception=True and user lacks permission.
        RextAuthorizationException: If raise_on_deny=True and use_http_exception=False and user lacks permission.
    """
    # Check if user has admin or super_admin role (using hierarchy)
    if await is_user_admin(db, user_id):
        return True

    # Check for the specific permission on a GLOBAL role only. This helper backs
    # global (platform) checks; counting workspace-scoped grants here would let a
    # permission held in one workspace satisfy a platform check (SEC-RBAC-12).
    perm_result = await db.execute(
        select(Permission.name)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(
            UserRole.user_id == user_id,
            Permission.name == permission_name,
            UserRole.workspace_id.is_(None),
        )
        .limit(1)
    )
    # Two of the account's roles can carry the same permission.
    if perm_result.first() is not None:
        return True

    if not raise_on_deny:
        return False

    if use_http_exception:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. Required: {permission_name} or admin role",
        )
    else:
        from src.api.middleware.exceptions import RextAuthorizationException

        raise RextAuthorizationException(
            message="You do not have permission to perform this action",
            context={"required_permission": permission_name, "user_id": str(user_id)},
        )
