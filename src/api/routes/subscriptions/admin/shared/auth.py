"""
Shared authentication helpers for admin subscription routes.

This module provides authentication and authorization utilities
for super admin operations.
"""

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole


async def check_super_admin(db: AsyncSession, user_id: str) -> bool:
    """Check if user is a super admin."""
    from uuid import UUID
    from src.utils.rbac_utils import is_user_super_admin
    return await is_user_super_admin(db, UUID(user_id))


async def require_super_admin(db: AsyncSession, user_id: str):
    """Raise exception if user is not super admin."""
    if not await check_super_admin(db, user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin role required for this operation"
        )
