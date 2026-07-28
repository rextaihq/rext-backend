"""
Email Preferences Service

Manages user email notification preferences and unsubscribe functionality.
"""
from typing import Optional, List, Dict, Set
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import secrets

from src.api.models.user_models.notification_preferences import NotificationPreferences
from src.utils.logger import logger


# Single source of truth: maps email type strings to NotificationPreferences column names
EMAIL_TYPE_TO_COLUMN: Dict[str, str] = {
    # Workspace notifications
    "workspace_invitation": "ws_invite_received",
    "invitation": "ws_invite_received",
    "invitation_accepted": "ws_invite_accepted",
    "invitation_reminder": "ws_invite_received",
    "role_changed": "ws_role_changed",
    "member_removed": "ws_member_removed",
    # Content generation notifications
    "content_generation_started": "gen_started",
    "content_generation_completed": "gen_completed",
    "content_generation_failed": "gen_failed",
    "content_published": "gen_published",
    # Billing notifications
    "subscription_created": "billing_payment_success",  # Using payment success as proxy
    "payment_succeeded": "billing_payment_success",
    "payment_failed": "billing_payment_failed",
    "subscription_cancelled": "billing_subscription_cancelled",
    "subscription_expiring_soon": "billing_subscription_expiring",
    "subscription_expired": "billing_subscription_expiring",  # Using expiring as proxy
    "trial_ending_soon": "billing_trial_ending",
    "trial_expired": "billing_subscription_expiring",  # Using expiring as proxy
    "payment_recovered": "billing_payment_success",  # Using success as proxy
    # Plan changes and lifecycle — treated as transactional billing confirmations
    "subscription_upgraded": "billing_payment_success",
    "subscription_downgraded": "billing_payment_success",
    "subscription_renewed": "billing_payment_success",
    "subscription_paused": "billing_subscription_cancelled",  # Using cancelled as proxy
    "subscription_resumed": "billing_payment_success",
    "usage_limit_warning": "billing_usage_limit_warning",
    "usage_limit_exceeded": "billing_usage_limit_exceeded",
    # Knowledge base notifications
    "kb_processing_completed": "kb_processing_completed",
    "kb_processing_failed": "kb_processing_failed",
    # Marketing
    "marketing": "marketing_updates",
}

# Reverse mapping for update_preferences (request field → column name)
PREFERENCE_FIELD_TO_COLUMN: Dict[str, str] = {
    **EMAIL_TYPE_TO_COLUMN,
    "digest_enabled": "digest_enabled",
    "digest_frequency": "digest_frequency",
}

VALID_EMAIL_TYPES: Set[str] = set(EMAIL_TYPE_TO_COLUMN.keys())

# Preferences that are still real ORM columns; everything else in
# EMAIL_TYPE_TO_COLUMN / PREFERENCE_FIELD_TO_COLUMN lives inside the
# category_preferences JSONB document and must go through get/set_preference().
_REAL_COLUMNS: Set[str] = {
    "email_notifications",
    "in_app_notifications",
    "digest_enabled",
    "digest_frequency",
    "marketing_updates",
}


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

        if not prefs.email_notifications:
            return False

        column_name = EMAIL_TYPE_TO_COLUMN.get(email_type)
        if column_name is None:
            logger.warning(
                f"Unknown email type '{email_type}' in check_can_send — defaulting to allowed",
                extra={"email_type": email_type, "user_id": str(user_id)}
            )
            return True

        # Category flags live in the category_preferences JSONB column, not as ORM
        # attributes. getattr() therefore always hit its default and every opt-out
        # was ignored — read through the model accessor instead.
        if column_name in _REAL_COLUMNS:
            return bool(getattr(prefs, column_name))
        return bool(prefs.get_preference(column_name))

    async def update_preferences(
        self,
        user_id: UUID,
        preferences: Dict[str, bool]
    ) -> NotificationPreferences:
        """Update user email preferences."""
        prefs = await self.get_or_create_preferences(user_id)

        for field, value in preferences.items():
            mapped_field = PREFERENCE_FIELD_TO_COLUMN.get(field, field)
            if mapped_field in _REAL_COLUMNS:
                setattr(prefs, mapped_field, value)
            else:
                # hasattr() is False for JSONB-backed categories, so the previous
                # setattr branch silently discarded every category update.
                prefs.set_preference(mapped_field, value)

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

        if not email_types:
            prefs.email_notifications = False
        else:
            for email_type in email_types:
                mapped_field = EMAIL_TYPE_TO_COLUMN.get(email_type, email_type)
                if mapped_field in _REAL_COLUMNS:
                    setattr(prefs, mapped_field, False)
                else:
                    prefs.set_preference(mapped_field, False)

        await self.db.flush()
        logger.info(f"Unsubscribed user from {email_types if email_types else 'all emails'}")
        return True

    async def get_unsubscribe_link(self, user_id: UUID, frontend_url: str) -> str:
        """Get unsubscribe link for user."""
        prefs = await self.get_or_create_preferences(user_id)
        return f"{frontend_url}/unsubscribe?token={prefs.unsubscribe_token}"