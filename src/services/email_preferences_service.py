"""
Email Preferences Service

Manages user email notification preferences and unsubscribe functionality.
"""

import secrets
from typing import Any, Dict, List, Set
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.user_models.notification_preferences import (
    DEFAULT_CATEGORY_PREFERENCES,
    NotificationPreferences,
)
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
    "subscription_upgraded": "billing_payment_success",
    "subscription_downgraded": "billing_payment_success",
    "payment_succeeded": "billing_payment_success",
    "payment_failed": "billing_payment_failed",
    "subscription_cancelled": "billing_subscription_cancelled",
    "subscription_expiring_soon": "billing_subscription_expiring",
    "trial_ending_soon": "billing_trial_ending",
    "trial_expired": "billing_subscription_expiring",  # Using expiring as proxy
    "payment_recovered": "billing_payment_success",  # Using success as proxy
    "usage_limit_warning": "billing_usage_limit_warning",
    "usage_limit_exceeded": "billing_usage_limit_exceeded",
    # Refund lifecycle. The payout rides on the approval preference: a customer
    # who wants to hear that a refund was approved wants to hear it arrived.
    "refund_requested": "billing_refund_requested",
    "refund_approved": "billing_refund_approved",
    "refund_rejected": "billing_refund_rejected",
    "refund_issued": "billing_refund_approved",
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

# The preferences that are columns of NotificationPreferences. Every other one is a category
# preference in its JSONB, read and written with get_preference / set_preference: reading it as an
# attribute finds nothing, so an opt-out was never seen (G61, rext-control #523).
COLUMN_PREFERENCES: frozenset[str] = frozenset(
    {
        "email_notifications",
        "in_app_notifications",
        "marketing_updates",
        "digest_enabled",
        "digest_frequency",
    }
)


def read_preference(prefs: NotificationPreferences, key: str) -> Any:
    """A preference's value, a column or a category key alike (a category's default if unset)."""
    if key in COLUMN_PREFERENCES:
        return getattr(prefs, key)
    return prefs.get_preference(key)


def write_preference(prefs: NotificationPreferences, key: str, value: Any) -> bool:
    """Set a preference, a column or a category key; False for a key that is neither."""
    if key in COLUMN_PREFERENCES:
        setattr(prefs, key, value)
        return True
    if key in DEFAULT_CATEGORY_PREFERENCES:
        prefs.set_preference(key, value)
        return True
    return False


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
                user_id=user_id, unsubscribe_token=secrets.token_urlsafe(32)
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
                extra={"email_type": email_type, "user_id": str(user_id)},
            )
            return True

        return bool(read_preference(prefs, column_name))

    async def update_preferences(
        self, user_id: UUID, preferences: Dict[str, bool]
    ) -> NotificationPreferences:
        """Update user email preferences."""
        prefs = await self.get_or_create_preferences(user_id)

        for field, value in preferences.items():
            write_preference(prefs, PREFERENCE_FIELD_TO_COLUMN.get(field, field), value)

        await self.db.flush()
        await self.db.refresh(prefs)

        logger.info(f"Updated email preferences for user {user_id}")
        return prefs

    async def unsubscribe(self, token: str, email_types: List[str]) -> bool:
        """Unsubscribe user from email types using token."""
        result = await self.db.execute(
            select(NotificationPreferences).where(
                NotificationPreferences.unsubscribe_token == token
            )
        )
        prefs = result.scalar_one_or_none()

        if not prefs:
            return False

        if not email_types:
            prefs.email_notifications = False
        else:
            for email_type in email_types:
                write_preference(prefs, EMAIL_TYPE_TO_COLUMN.get(email_type, email_type), False)

        await self.db.flush()
        logger.info(f"Unsubscribed user from {email_types if email_types else 'all emails'}")
        return True

    async def get_unsubscribe_link(self, user_id: UUID, frontend_url: str) -> str:
        """Get unsubscribe link for user."""
        prefs = await self.get_or_create_preferences(user_id)
        return f"{frontend_url}/unsubscribe?token={prefs.unsubscribe_token}"
