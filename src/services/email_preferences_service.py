"""
Email Preferences Service

Manages user email notification preferences and unsubscribe functionality.
"""
from typing import Optional, List, Dict
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import secrets

from src.api.models.user_models.email_preferences import EmailPreferences
from src.api.lib.logger import auto_logger
from src.api.models.user_models.notification_preferences import NotificationPreferences

logger = auto_logger()


class EmailPreferencesService:
    """Service for managing email preferences."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_preferences(self, user_id: UUID, db: AsyncSession) -> NotificationPreferences:
        """Get user preferences or create default if not exists."""
        result = await db.execute(
            select(NotificationPreferences).where(NotificationPreferences.user_id == user_id)
        )
        prefs = result.scalar_one_or_none()

        if not prefs:
            prefs = NotificationPreferences(
                user_id=user_id,
                unsubscribe_token=secrets.token_urlsafe(32)
            )
            db.add(prefs)
            await db.flush()
            await db.refresh(prefs)
            logger.info(f"Created default notification preferences for user {user_id}")

        return prefs

    async def check_can_send(self, user_id: UUID, email_type: str, db: AsyncSession) -> bool:
        """Check if user allows this email type."""
        prefs = await self.get_or_create_preferences(user_id, db)

        # Check master email toggle first
        if not prefs.email_notifications:
            return False

        # Map email types to NotificationPreferences columns
        type_mapping = {
            "workspace_invitation": prefs.ws_invite_received,
            "invitation": prefs.ws_invite_received,
            "invitation_accepted": prefs.ws_invite_accepted,
            "role_changed": prefs.ws_role_changed,
            "member_removed": prefs.ws_member_removed,
            "marketing": prefs.marketing_updates,
        }

        return type_mapping.get(email_type, True)

    async def update_preferences(
        self,
        user_id: UUID,
        preferences: Dict[str, bool],
        db: AsyncSession
    ) -> EmailPreferences:
        """Update user email preferences."""
        prefs = await self.get_or_create_preferences(user_id, db)

        # Update allowed fields
        allowed_fields = [
            "workspace_invitation",
            "invitation_accepted",
            "role_changed",
            "member_removed",
            "marketing"
        ]

        for field, value in preferences.items():
            if field in allowed_fields:
                setattr(prefs, field, value)

        await db.flush()
        await db.refresh(prefs)

        logger.info(f"Updated email preferences for user {user_id}")
        return prefs

    async def unsubscribe(
        self,
        token: str,
        email_types: List[str],
        db: AsyncSession
    ) -> bool:
        """Unsubscribe user from email types using token."""
        result = await db.execute(
            select(EmailPreferences).where(EmailPreferences.unsubscribe_token == token)
        )
        prefs = result.scalar_one_or_none()

        if not prefs:
            return False

        # Unsubscribe from specified types (or all if empty list)
        if not email_types:
            # Unsubscribe from all
            prefs.workspace_invitation = False
            prefs.invitation_accepted = False
            prefs.role_changed = False
            prefs.member_removed = False
            prefs.marketing = False
        else:
            # Unsubscribe from specified types
            for email_type in email_types:
                if hasattr(prefs, email_type):
                    setattr(prefs, email_type, False)

        await db.commit()
        logger.info(f"Unsubscribed user from {email_types if email_types else 'all emails'}")
        return True

    async def get_unsubscribe_link(self, user_id: UUID, frontend_url: str, db: AsyncSession) -> str:
        """Get unsubscribe link for user."""
        prefs = await self.get_or_create_preferences(user_id, db)
        return f"{frontend_url}/unsubscribe?token={prefs.unsubscribe_token}"
