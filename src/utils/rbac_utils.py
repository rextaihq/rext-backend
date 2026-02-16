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

    Resources: workspace, content, topic, knowledge, member, role, permission, etc.
    Actions: create, read, update, delete, publish, approve, invite, manage, etc.

    Examples:
    - workspace.delete (delete workspace)
    - content.publish (publish content)
    - topic.approve (approve topics)
    - member.invite (invite members)
    - knowledge.delete (delete knowledge)

Usage:
    from src.utils.rbac_utils import check_permission, require_permission

    # Check if user has permission
    has_perm = await check_permission(db, user_id, "content.delete", workspace_id)

    # Require permission (raises exception if denied)
    await require_permission(db, user_id, "content.delete", workspace_id)
"""

from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.user_models.roles import Role
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.user_roles import UserRole
from src.api.middleware.exceptions import RextAuthorizationException
from src.api.lib.logger import auto_logger

logger = auto_logger()

ADMIN_HIERARCHY_THRESHOLD = 90
SUPER_ADMIN_HIERARCHY_THRESHOLD = 100

async def check_permission(
    db: AsyncSession,
    user_id: UUID,
    permission_name: str,
    workspace_id: Optional[UUID] = None
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
    workspace_id: Optional[UUID] = None
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
    workspace_id: Optional[UUID] = None
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
    resource_name: Optional[str] = None
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
        logger.warning(
            f"Permission denied: user={user_id}, permission={permission_name}, "
            f"workspace={workspace_id}, resource={resource_name}"
        )

        raise RextAuthorizationException(
            message=f"You do not have permission to perform this action",
            context={
                "required_permission": permission_name,
                "resource": resource_name,
                "workspace_id": str(workspace_id) if workspace_id else None
            }
        )


async def get_user_permissions(
    db: AsyncSession,
    user_id: UUID,
    workspace_id: Optional[UUID] = None
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
    # Try cache first
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
    permissions_list = list(permissions)

    logger.debug(
        f"Retrieved {len(permissions_list)} permissions for user={user_id}, workspace={workspace_id}"
    )

    # Cache the result for 5 minutes
    if cache.is_enabled:
        await cache.set(cache_key, permissions_list, ttl=300)

    return permissions_list


async def get_user_roles(
    db: AsyncSession,
    user_id: UUID,
    workspace_id: Optional[UUID] = None
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

    logger.debug(
        f"Retrieved {len(roles)} roles for user={user_id}, workspace={workspace_id}"
    )

    return roles


async def get_user_role_names(
    db: AsyncSession,
    user_id: UUID,
    workspace_id: Optional[UUID] = None
) -> List[str]:
    """
    Get all role names assigned to user (cached).

    This function is cached for 5 minutes to improve performance.

    Args:
        db: AsyncSession database session
        user_id: User UUID
        workspace_id: Optional workspace UUID. If provided, returns roles
                     from both workspace-scoped and global assignments.

    Returns:
        List of role names (e.g., ["admin", "editor"])
    """
    # Try cache first
    from src.api.cache.redis_client import cache
    cache_key = f"user:roles:{user_id}:{workspace_id or 'global'}"

    if cache.is_enabled:
        cached_roles = await cache.get(cache_key)
        if cached_roles is not None:
            logger.debug(f"Cache hit for roles: user={user_id}, workspace={workspace_id}")
            return cached_roles

    # Cache miss - query database
    query = (
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
    )

    if workspace_id:
        query = query.where(
            (UserRole.workspace_id == workspace_id) | (UserRole.workspace_id.is_(None))
        )
    else:
        query = query.where(UserRole.workspace_id.is_(None))

    result = await db.execute(query)
    role_names = list(result.scalars().all())

    # Cache result for 5 minutes
    if cache.is_enabled:
        await cache.set(cache_key, role_names, ttl=300)

    return role_names
from fastapi import HTTPException, status as http_status


async def is_user_admin(
    db: AsyncSession,
    user_id: UUID,
    workspace_id: UUID | None = None
) -> bool:
    """
    Check if a user has an admin-level role based on hierarchy_level.

    A user is considered an admin if they have any role with
    hierarchy_level >= ADMIN_HIERARCHY_THRESHOLD (90).

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
        .where(
            UserRole.user_id == user_id,
            Role.hierarchy_level >= ADMIN_HIERARCHY_THRESHOLD
        )
    )

    if workspace_id is None:
        # Only check global roles
        query = query.where(UserRole.workspace_id.is_(None))
    else:
        # Check global roles OR specifically this workspace
        from sqlalchemy import or_
        query = query.where(
            or_(
                UserRole.workspace_id.is_(None),
                UserRole.workspace_id == workspace_id
            )
        )

    result = await db.execute(query)
    return result.scalar_one_or_none() is not None


async def is_user_super_admin(
    db: AsyncSession,
    user_id: UUID
) -> bool:
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
            UserRole.workspace_id.is_(None)
        )
    )

    result = await db.execute(query)
    return result.scalar_one_or_none() is not None


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

    # Check for specific permission
    perm_result = await db.execute(
        select(Permission.name)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(
            UserRole.user_id == user_id,
            Permission.name == permission_name,
        )
    )
    if perm_result.scalar_one_or_none() is not None:
        return True

    if not raise_on_deny:
        return False

    if use_http_exception:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. Required: {permission_name} or admin role",
        )
    else:
        raise RextAuthorizationException(
            message="You do not have permission to perform this action",
            context={"required_permission": permission_name, "user_id": str(user_id)},
        )
