"""
Notification Preferences Service - Business Logic for Notification Preference Operations

This service encapsulates all business logic related to notification preferences,
including creation of defaults and retrieval.

Responsibilities:
- Get or create notification preferences
- Provide a single source of truth for default preference creation

Does NOT:
- Handle HTTP requests/responses (that's routes)
- Commit transactions (that's decorators/routes)
"""

from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any
from src.api.cache.decorators import cached
from src.api.models.user_models.notification_preferences import NotificationPreferences
from src.utils.logger import logger


class NotificationPreferencesService:
    """Service for notification preferences business logic."""

    def __init__(self, db: AsyncSession):
        """
        Initialize service with database session.

        Args:
            db: Async database session
        """
        self.db = db

    async def get_or_create(self, user_id: UUID) -> NotificationPreferences:
        """
        Get notification preferences or create default ones if they don't exist.

        Uses model-level column defaults for all boolean fields, ensuring
        a single source of truth for default values. Does NOT commit —
        the caller or a transaction decorator is responsible for committing.

        Args:
            user_id: User UUID

        Returns:
            NotificationPreferences object (existing or newly created)
        """
        query = select(NotificationPreferences).where(
            NotificationPreferences.user_id == user_id
        )
        result = await self.db.execute(query)
        preferences = result.scalar_one_or_none()

        if not preferences:
            # Rely on model column defaults — do NOT hardcode field values
            preferences = NotificationPreferences(user_id=user_id)
            self.db.add(preferences)
            await self.db.flush()  # Flush to get ID but don't commit
            logger.info(f"Created default notification preferences for user {user_id}")
        else:
            logger.debug(f"Retrieved existing notification preferences for user {user_id}")

        return preferences

    @cached(
        key_prefix="user:preferences",
        ttl=300,
        key_builder=lambda self, user_id: str(user_id)
    )
    async def get_cached_preferences(self, user_id: UUID) -> Dict[str, Any]:
        """
        Get cached notification preferences as a dictionary.
        Creates default preferences if they don't exist.
        """
        preferences = await self.get_or_create(user_id)
        # Assuming to_dict() returns the serialized version matching the response schema
        return preferences.to_dict()
