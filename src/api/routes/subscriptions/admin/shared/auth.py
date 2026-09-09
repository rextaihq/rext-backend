"""
Shared authentication helpers for admin subscription routes.

This module provides authentication and authorization utilities
for super admin operations.
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user


async def require_super_admin_user(
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Dependency that ensures the caller is super admin and returns current_user."""
    user_id = current_user.get("identity")
    if not user_id or not await check_super_admin(db, str(user_id)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin role required for this operation",
        )
    return current_user


async def check_super_admin(db: AsyncSession, user_id) -> bool:
    """Check if user is a super admin."""
    from uuid import UUID

    from src.utils.rbac_utils import is_user_super_admin

    uuid_val = user_id if isinstance(user_id, UUID) else UUID(str(user_id))
    return await is_user_super_admin(db, uuid_val)


async def require_super_admin(db: AsyncSession, user_id: str):
    """Raise exception if user is not super admin."""
    if not await check_super_admin(db, user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin role required for this operation",
        )
