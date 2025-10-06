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
from src.api.middleware.exceptions import WrextAuthorizationException
from src.api.lib.logger import auto_logger

logger = auto_logger()


async def check_permission(
    db: AsyncSession,
    user_id: UUID,
    permission_name: str,
    workspace_id: Optional[UUID] = None
) -> bool:
    """
    Check if user has a specific permission.

    Queries the database to determine if the user has the required permission
    through any of their assigned roles (either workspace-scoped or global).

    Args:
        db: AsyncSession database session
        user_id: User UUID
        permission_name: Permission name (e.g., "content.delete", "workspace.update")
        workspace_id: Optional workspace UUID for workspace-scoped permissions.
                     If provided, checks both workspace-scoped roles and global roles.
                     If None, checks only global roles.

    Returns:
        True if user has the permission, False otherwise

    Algorithm:
        1. Find all roles assigned to user (in specified workspace or globally)
        2. Find all permissions attached to those roles via role_permissions
        3. Check if the requested permission_name matches any permission

    Example:
        >>> has_perm = await check_permission(db, user_id, "content.delete", workspace_id)
        >>> if has_perm:
        >>>     # User can delete content
        >>>     pass
    """
    query = (
        select(Permission)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id)
        .where(Permission.name == permission_name)
    )

    # Workspace-scoped permissions: Check both workspace-specific roles AND global roles
    if workspace_id:
        query = query.where(
            (UserRole.workspace_id == workspace_id) | (UserRole.workspace_id.is_(None))
        )
    else:
        # Global permissions only: User must have global role (workspace_id = NULL)
        query = query.where(UserRole.workspace_id.is_(None))

    result = await db.execute(query)
    permission = result.scalar_one_or_none()

    has_permission = permission is not None

    logger.debug(
        f"Permission check: user={user_id}, permission={permission_name}, "
        f"workspace={workspace_id}, result={has_permission}"
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
    WrextAuthorizationException if the user lacks the required permission.

    Args:
        db: AsyncSession database session
        user_id: User UUID
        permission_name: Required permission name
        workspace_id: Optional workspace UUID for workspace-scoped check
        resource_name: Optional resource name for better error messages (e.g., "content", "workspace")

    Raises:
        WrextAuthorizationException: If user lacks the required permission

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

        raise WrextAuthorizationException(
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
    Get all permissions for a user.

    Returns a list of all permission names that the user has access to,
    either through workspace-scoped roles or global roles.

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

    logger.debug(
        f"Retrieved {len(permissions)} permissions for user={user_id}, workspace={workspace_id}"
    )

    return list(permissions)


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
