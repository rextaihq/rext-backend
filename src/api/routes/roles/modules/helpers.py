from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.exceptions import RextAuthorizationException
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole


async def check_role_permission(db: AsyncSession, user_id: UUID, required_permission: str) -> bool:
    """
    Check if user has specific role permission or is admin.

    Args:
        db: Database session
        user_id: User UUID
        required_permission: Permission name required (e.g., "role.read")

    Returns:
        True if user has permission

    Raises:
        RextAuthorizationException if user lacks permission
    """
    # Check if admin
    result = await db.execute(
        select(UserRole)
        .join(Role)
        .where(UserRole.user_id == user_id, Role.name.in_(["admin", "super_admin"]))
    )
    is_user_admin = result.scalar_one_or_none() is not None

    if is_user_admin:
        return True

    # Check for specific permission
    result = await db.execute(
        select(Permission.name)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id, Permission.name == required_permission)
    )
    has_permission = result.scalar_one_or_none()

    if not has_permission:
        raise RextAuthorizationException(
            message=f"Insufficient permissions. Required: {required_permission} or admin role",
            required_permission=required_permission,
            context={"user_id": str(user_id)},
        )

    return True
