"""Authentication and user verification utilities."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.exceptions import RextAuthenticationException
from src.api.models.user_models.users import Users


async def verify_current_user(db: AsyncSession, user_id: UUID) -> Users:
    """
    Verify user exists and is not deleted.

    Args:
        db: Database session
        user_id: User ID to verify

    Returns:
        Users: The verified user object

    Raises:
        RextAuthenticationException: If user not found or deleted
    """
    result = await db.execute(select(Users).where(Users.id == user_id, Users.deleted_at.is_(None)))
    user = result.scalar_one_or_none()

    if not user:
        raise RextAuthenticationException(
            message="User not found or has been deleted", context={"user_id": str(user_id)}
        )

    return user
