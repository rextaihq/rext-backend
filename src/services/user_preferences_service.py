"""
User Preferences Service - Business Logic for User Preference Operations

This service encapsulates all business logic related to user preferences,
including theme settings, display options, and UI preferences.

Responsibilities:
- Get or create user preferences
- Update user preferences
- Manage default preferences

Does NOT:
- Handle HTTP requests/responses (that's routes)
- Commit transactions (that's decorators/routes)
"""

from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.user_models.user_preferences import UserPreferences
from src.utils.logger import logger


class UserPreferencesService:
    """Service for user preferences business logic"""

    def __init__(self, db: AsyncSession):
        """
        Initialize service with database session.

        Args:
            db: Async database session
        """
        self.db = db

    async def get_or_create_preferences(
        self,
        user_id: UUID
    ) -> UserPreferences:
        """
        Get user preferences or create default ones if they don't exist.

        Args:
            user_id: User UUID

        Returns:
            UserPreferences object
        """
        # Try to get existing preferences
        query = select(UserPreferences).where(UserPreferences.user_id == user_id)
        result = await self.db.execute(query)
        preferences = result.scalar_one_or_none()

        if not preferences:
            # Create default preferences
            preferences = UserPreferences(
                user_id=user_id,
                theme="system",
                date_format="iso",
                time_format="24h",
                items_per_page=25,
                sidebar_collapsed=False
            )
            self.db.add(preferences)
            await self.db.flush()  # Flush to get ID but don't commit
            logger.info(f"Created default preferences for user {user_id}")
        else:
            logger.debug(f"Retrieved existing preferences for user {user_id}")

        return preferences

    async def update_preferences(
        self,
        user_id: UUID,
        theme: Optional[str] = None,
        date_format: Optional[str] = None,
        time_format: Optional[str] = None,
        items_per_page: Optional[int] = None,
        sidebar_collapsed: Optional[bool] = None
    ) -> UserPreferences:
        """
        Update user preferences. Creates preferences if they don't exist.

        Args:
            user_id: User UUID
            theme: UI theme (system, light, dark)
            date_format: Date format (iso, us, eu, relative)
            time_format: Time format (24h, 12h)
            items_per_page: Items per page (10-100)
            sidebar_collapsed: Sidebar state (boolean)

        Returns:
            Updated UserPreferences object
        """
        # Get or create preferences
        preferences = await self.get_or_create_preferences(user_id)

        # Update only provided fields
        updates = []
        if theme is not None:
            preferences.theme = theme
            updates.append(f"theme={theme}")
        if date_format is not None:
            preferences.date_format = date_format
            updates.append(f"date_format={date_format}")
        if time_format is not None:
            preferences.time_format = time_format
            updates.append(f"time_format={time_format}")
        if items_per_page is not None:
            preferences.items_per_page = items_per_page
            updates.append(f"items_per_page={items_per_page}")
        if sidebar_collapsed is not None:
            preferences.sidebar_collapsed = sidebar_collapsed
            updates.append(f"sidebar_collapsed={sidebar_collapsed}")

        if updates:
            preferences.updated_at = datetime.now(timezone.utc)
            await self.db.commit() 
            logger.info(f"Updated preferences for user {user_id}: {', '.join(updates)}")
        else:
            logger.debug(f"No preferences updated for user {user_id}")

        return preferences
