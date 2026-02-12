"""
Email Preferences Service

Manages user email notification preferences and unsubscribe functionality.
"""
from typing import Optional, List, Dict
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import secrets

from src.api.models.user_models.notification_preferences import NotificationPreferences
from src.utils.logger import logger


class EmailPreferencesService:
    """Service for managing email preferences."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_preferences(self, user_id: UUID) -> NotificationPreferences:
        """Get user preferences or create default if not exists."""
        result = await self.db.execute(
            select(NotificationPreferences).where(NotificationPreferences.user_id == user_id)
        )
        prefs = result.scalar_one_or_none()

        if not prefs:
            prefs = NotificationPreferences(
                user_id=user_id,
                unsubscribe_token=secrets.token_urlsafe(32)
            )
            self.db.add(prefs)
            await self.db.flush()
            await self.db.refresh(prefs)
            logger.info(f"Created default notification preferences for user {user_id}")

        return prefs

    async def check_can_send(self, user_id: UUID, email_type: str) -> bool:
        """Check if user allows this email type."""
        prefs = await self.get_or_create_preferences(user_id)

        # Check master email toggle first
        if not prefs.email_notifications:
            return False

        # Map email types to NotificationPreferences columns
        # This mapping should be expanded as needed
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
        preferences: Dict[str, bool]
    ) -> NotificationPreferences:
        """Update user email preferences."""
        prefs = await self.get_or_create_preferences(user_id)

        # Build update dict mapping request fields to NotificationPreferences columns
        field_mapping = {
            "workspace_invitation": "ws_invite_received",
            "invitation_accepted": "ws_invite_accepted",
            "role_changed": "ws_role_changed",
            "member_removed": "ws_member_removed",
            "content_generation_started": "gen_started",
            "content_generation_completed": "gen_completed",
            "content_generation_failed": "gen_failed",
            "content_published": "gen_published",
            "payment_succeeded": "billing_payment_success",
            "payment_failed": "billing_payment_failed",
            "subscription_cancelled": "billing_subscription_cancelled",
            "subscription_expiring_soon": "billing_subscription_expiring",
            "trial_ending_soon": "billing_trial_ending",
            "usage_limit_warning": "billing_usage_limit_warning",
            "usage_limit_exceeded": "billing_usage_limit_exceeded",
            "kb_processing_completed": "kb_processing_completed",
            "kb_processing_failed": "kb_processing_failed",
            "digest_enabled": "digest_enabled",
            "digest_frequency": "digest_frequency",
            "marketing": "marketing_updates",
        }

        for field, value in preferences.items():
            mapped_field = field_mapping.get(field, field)
            if hasattr(prefs, mapped_field):
                setattr(prefs, mapped_field, value)

        await self.db.flush()
        await self.db.refresh(prefs)

        logger.info(f"Updated email preferences for user {user_id}")
        return prefs

    async def unsubscribe(
        self,
        token: str,
        email_types: List[str]
    ) -> bool:
        """Unsubscribe user from email types using token."""
        result = await self.db.execute(
            select(NotificationPreferences).where(NotificationPreferences.unsubscribe_token == token)
        )
        prefs = result.scalar_one_or_none()

        if not prefs:
            return False

        # Map email types to NotificationPreferences columns
        type_mapping = {
            "workspace_invitation": "ws_invite_received",
            "invitation_accepted": "ws_invite_accepted",
            "role_changed": "ws_role_changed",
            "member_removed": "ws_member_removed",
            "content_generation_started": "gen_started",
            "content_generation_completed": "gen_completed",
            "content_generation_failed": "gen_failed",
            "content_published": "gen_published",
            "payment_succeeded": "billing_payment_success",
            "payment_failed": "billing_payment_failed",
            "subscription_cancelled": "billing_subscription_cancelled",
            "subscription_expiring_soon": "billing_subscription_expiring",
            "trial_ending_soon": "billing_trial_ending",
            "usage_limit_warning": "billing_usage_limit_warning",
            "usage_limit_exceeded": "billing_usage_limit_exceeded",
            "kb_processing_completed": "kb_processing_completed",
            "kb_processing_failed": "kb_processing_failed",
            "marketing": "marketing_updates",
        }

        # Unsubscribe from specified types (or master toggle if empty list)
        if not email_types:
            prefs.email_notifications = False
        else:
            # Unsubscribe from specified types
            for email_type in email_types:
                mapped_field = type_mapping.get(email_type, email_type)
                if hasattr(prefs, mapped_field):
                    setattr(prefs, mapped_field, False)

        await self.db.flush()
        logger.info(f"Unsubscribed user from {email_types if email_types else 'all emails'}")
        return True

    async def get_unsubscribe_link(self, user_id: UUID, frontend_url: str) -> str:
        """Get unsubscribe link for user."""
        prefs = await self.get_or_create_preferences(user_id)
        return f"{frontend_url}/unsubscribe?token={prefs.unsubscribe_token}"
