# src/api/services/notification_helper.py
from uuid import UUID
from typing import Optional
from fastapi import BackgroundTasks
from src.services.notifications_services import notification_service
from src.api.models.user_models.notification_preferences import NotificationPreferences
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging

logger = logging.getLogger(__name__)


# ==============================
# NOTIFICATION CONFIGURATION
# ==============================
# Single source of truth for all notification flags.
# Keys are pref_flag values passed to schedule_if_allowed().
# "pref_column" is the actual column on NotificationPreferences to check.
# If pref_column matches the flag name, it's a "real" column.
# If pref_column differs, it's a "virtual" flag mapped to a real column.

NOTIFICATION_CONFIG = {
    # Workspace notifications
    "ws_invite_received": {
        "pref_column": "ws_invite_received",
        "type": "workspace",
        "title": "Workspace Invitation",
        "status": "success",
    },
    "ws_invite_accepted": {
        "pref_column": "ws_invite_accepted",
        "type": "workspace",
        "title": "Invitation Accepted",
        "status": "success",
    },
    "ws_role_changed": {
        "pref_column": "ws_role_changed",
        "type": "workspace",
        "title": "Role Changed",
        "status": "success",
    },
    "ws_member_removed": {
        "pref_column": "ws_member_removed",
        "type": "workspace",
        "title": "Member Removed",
        "status": "success",
    },
    # Billing notifications
    "billing_payment_success": {
        "pref_column": "billing_payment_success",
        "type": "billing",
        "title": "Payment Successful",
        "status": "success",
    },
    "billing_payment_failed": {
        "pref_column": "billing_payment_failed",
        "type": "billing",
        "title": "Payment Failed",
        "status": "error",
    },
    "billing_subscription_cancelled": {
        "pref_column": "billing_subscription_cancelled",
        "type": "billing",
        "title": "Subscription Cancelled",
        "status": "warning",
    },
    "billing_subscription_expiring": {
        "pref_column": "billing_subscription_expiring",
        "type": "billing",
        "title": "Subscription Expiring",
        "status": "warning",
    },
    "billing_trial_ending": {
        "pref_column": "billing_trial_ending",
        "type": "billing",
        "title": "Trial Ending",
        "status": "warning",
    },
    "billing_usage_limit_warning": {
        "pref_column": "billing_usage_limit_warning",
        "type": "billing",
        "title": "Usage Limit Warning",
        "status": "warning",
    },
    "billing_usage_limit_exceeded": {
        "pref_column": "billing_usage_limit_exceeded",
        "type": "billing",
        "title": "Usage Limit Exceeded",
        "status": "error",
    },
    # Knowledge base notifications
    "kb_processing_completed": {
        "pref_column": "kb_processing_completed",
        "type": "knowledge",
        "title": "Knowledge Processing Complete",
        "status": "success",
    },
    "kb_processing_failed": {
        "pref_column": "kb_processing_failed",
        "type": "knowledge",
        "title": "Knowledge Processing Failed",
        "status": "error",
    },
    # Content generation notifications
    "gen_started": {
        "pref_column": "gen_started",
        "type": "content",
        "title": "Content Generation Started",
        "status": "info",
    },
    "gen_completed": {
        "pref_column": "gen_completed",
        "type": "content",
        "title": "Content Generation Complete",
        "status": "success",
    },
    "gen_failed": {
        "pref_column": "gen_failed",
        "type": "content",
        "title": "Content Generation Failed",
        "status": "error",
    },
    "gen_published": {
        "pref_column": "gen_published",
        "type": "content",
        "title": "Content Published",
        "status": "success",
    },
    # User/profile notifications (virtual flags → in_app_notifications column)
    "in_app_notifications": {
        "pref_column": "in_app_notifications",
        "type": "user",
        "title": "Profile Updated",
        "status": "success",
    },
    "profile_update_failed": {
        "pref_column": "in_app_notifications",
        "type": "user",
        "title": "Profile Update Failed",
        "status": "error",
    },
    "avatar_uploaded": {
        "pref_column": "in_app_notifications",
        "type": "user",
        "title": "Avatar Updated",
        "status": "success",
    },
    "avatar_upload_failed": {
        "pref_column": "in_app_notifications",
        "type": "user",
        "title": "Avatar Upload Failed",
        "status": "error",
    },
}


async def schedule_if_allowed(
    *,
    db: AsyncSession,
    user_id: str,
    background_tasks: BackgroundTasks,
    pref_flag: str,
    message: str,
    payload: dict,
    workspace_id: Optional[str] = None,
) -> None:
    """
    Load the user's NotificationPreferences, check the master in-app toggle
    and the specific preference column for the given flag.
    If both are True, persist the notification to the database and schedule
    SSE delivery via background task.
    """
    # 1. Validate the pref_flag against known configuration
    config = NOTIFICATION_CONFIG.get(pref_flag)
    if config is None:
        logger.warning(
            f"Unknown notification flag '{pref_flag}' — no configuration entry exists. "
            f"Notification for user {user_id} will not be sent. "
            f"Add an entry to NOTIFICATION_CONFIG in notification_helper.py."
        )
        return

    # 2. Load preferences
    result = await db.execute(
        select(NotificationPreferences).where(
            NotificationPreferences.user_id == UUID(user_id)
        )
    )
    pref = result.scalar_one_or_none()

    if not pref:
        logger.debug(f"No NotificationPreferences row for user {user_id}")
        return

    # 3. Global master switch for in-app notifications
    if not pref.in_app_notifications:
        logger.debug(f"User {user_id} disabled all in-app notifications.")
        return

    # 4. Specific flag check using the mapped column
    pref_column = config["pref_column"]
    flag_enabled = getattr(pref, pref_column, None)
    if flag_enabled is None:
        logger.error(
            f"Preference column '{pref_column}' does not exist on NotificationPreferences model. "
            f"Flag: '{pref_flag}'. This indicates a configuration error in NOTIFICATION_CONFIG."
        )
        return
    if not flag_enabled:
        logger.debug(
            f"User {user_id} has preference {pref_column}=False — skipping notification."
        )
        return

    # 5. Create notification record in database
    from src.api.models.notification.notification_model import Notification
    from datetime import datetime, timezone

    notification = Notification(
        user_id=UUID(user_id),
        workspace_id=UUID(workspace_id) if workspace_id else None,
        title=config["title"],
        message=message,
        type=config["type"],
        category=pref_flag,
        status=config["status"],
        priority="normal",
        payload=payload,
        is_read=False,
        sent_via_sse=True,
        sse_sent_at=datetime.now(timezone.utc),
    )

    db.add(notification)
    await db.flush()
    await db.refresh(notification)

    logger.info(
        f"Created notification record {notification.id} for user {user_id} — "
        f"type: {config['type']}, category: {pref_flag}"
    )

    # 6. Schedule the SSE notification
    logger.info(
        f"Scheduling SSE notification for user {user_id} — flag {pref_flag} — message: {message}"
    )
    background_tasks.add_task(
        notification_service.send_success_notification,
        user_id=UUID(user_id),
        message=message,
        payload=payload,
    )
    logger.info("Notification task scheduled.")

