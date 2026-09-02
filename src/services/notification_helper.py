import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import escape as html_escape
from typing import Optional
from uuid import UUID

from fastapi import BackgroundTasks
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.user_models.notification_preferences import NotificationPreferences
from src.services.notification_preferences_service import NotificationPreferencesService
from src.services.notifications_services import notification_service
from src.utils.payload_sanitizer import sanitize_notification_payload

logger = logging.getLogger(__name__)


# ==============================
# NOTIFICATION CONFIGURATION
# ==============================
@dataclass
class NotificationConfig:
    notification_type: str
    title: str
    status: str = "success"
    pref_column: Optional[str] = None

    def __getitem__(self, key: str):
        # Support both config.notification_type and config['type']
        if key == "type":
            return self.notification_type
        return getattr(self, key)


# Single source of truth for all notification flags.
# Keys are pref_flag values passed to schedule_if_allowed().
# "pref_column" is the actual column on NotificationPreferences to check.
# If pref_column matches the flag name, it's a "real" column.
# If pref_column differs, it's a "virtual" flag mapped to a real column.
NOTIFICATION_REGISTRY: dict[str, NotificationConfig] = {
    # System & Profile
    "in_app_notifications": NotificationConfig(
        notification_type="system", title="Profile Update", status="info"
    ),
    "avatar_uploaded": NotificationConfig(
        notification_type="system", title="Avatar Updated", status="success"
    ),
    # Workspace
    "ws_invite_received": NotificationConfig(
        notification_type="workspace", title="Workspace Invite", status="info"
    ),
    "ws_invite_accepted": NotificationConfig(
        notification_type="workspace", title="Invite Accepted", status="success"
    ),
    "ws_role_changed": NotificationConfig(
        notification_type="workspace", title="Role Changed", status="info"
    ),
    "ws_member_removed": NotificationConfig(
        notification_type="workspace", title="Member Removed", status="warning"
    ),
    # Content Generation
    "gen_started": NotificationConfig(
        notification_type="generation", title="Generation Started", status="info"
    ),
    "gen_completed": NotificationConfig(
        notification_type="generation", title="Generation Completed", status="success"
    ),
    "gen_failed": NotificationConfig(
        notification_type="generation", title="Generation Failed", status="error"
    ),
    "gen_published": NotificationConfig(
        notification_type="generation", title="Content Published", status="success"
    ),
    # Billing
    "billing_payment_success": NotificationConfig(
        notification_type="billing", title="Payment Successful", status="success"
    ),
    "billing_payment_failed": NotificationConfig(
        notification_type="billing", title="Payment Failed", status="error"
    ),
    "billing_subscription_cancelled": NotificationConfig(
        notification_type="billing", title="Subscription Cancelled", status="warning"
    ),
    "billing_subscription_expiring": NotificationConfig(
        notification_type="billing", title="Subscription Expiring", status="warning"
    ),
    "billing_trial_ending": NotificationConfig(
        notification_type="billing", title="Trial Ending", status="info"
    ),
    "billing_usage_limit_warning": NotificationConfig(
        notification_type="billing", title="Usage Limit Warning", status="warning"
    ),
    "billing_usage_limit_exceeded": NotificationConfig(
        notification_type="billing", title="Usage Limit Exceeded", status="error"
    ),
    # Knowledge Base
    "kb_processing_completed": NotificationConfig(
        notification_type="kb", title="Knowledge Base Processed", status="success"
    ),
    "kb_processing_failed": NotificationConfig(
        notification_type="kb", title="Knowledge Base Failed", status="error"
    ),
}

DEDUP_WINDOW_SECONDS = 60  # Suppress duplicate notifications within this window


async def _send_sse_after_commit(
    user_id: UUID,
    message: str,
    payload: dict,
    notification_id: str,
) -> None:
    """
    Send SSE notification. Designed to run as a FastAPI background task,
    which executes AFTER the response is sent (and therefore after the
    transaction is committed by the response middleware).

    This ordering guarantees that the notification record is visible in the
    database before the SSE event reaches the client.
    """
    try:
        await notification_service.send_success_notification(
            user_id=user_id,
            message=message,
            payload=payload,
        )
        logger.info(
            "SSE notification sent for notification %s to user %s",
            notification_id,
            user_id,
        )
    except Exception as e:
        logger.error(
            "Failed to send SSE notification %s for user %s: %s",
            notification_id,
            user_id,
            e,
        )


async def _recheck_preference_enabled(
    db: AsyncSession,
    user_id: UUID,  # Changed from str to UUID
    pref_flag: str,
) -> bool:
    """
    Re-read the user's notification preferences with a row-level lock
    (SELECT ... FOR UPDATE) immediately before creating a notification.


    Returns True if the notification should proceed, False otherwise.
    """
    result = await db.execute(
        select(NotificationPreferences)
        .where(NotificationPreferences.user_id == user_id)
        .with_for_update()
    )
    pref = result.scalar_one_or_none()

    if not pref:
        logger.debug("[recheck] No NotificationPreferences row for user %s", user_id)
        return False

    if not pref.in_app_notifications:
        logger.debug("[recheck] User %s has disabled all in-app notifications.", user_id)
        return False

    # Map virtual flags to real columns (same logic as main function)
    real_pref_column = pref_flag
    if pref_flag in ["profile_update_failed", "avatar_uploaded", "avatar_upload_failed"]:
        real_pref_column = "in_app_notifications"

    # Dedicated column (in_app_notifications) — access via attribute.
    # Category preferences live in JSONB — use get_preference().
    if real_pref_column == "in_app_notifications":
        flag_enabled = pref.in_app_notifications
    else:
        flag_enabled = pref.get_preference(real_pref_column)

    if not flag_enabled:
        logger.debug(
            "[recheck] User %s has %s=False – notification suppressed after re-check.",
            user_id,
            real_pref_column,
        )
        return False

    return True


def _safe_to_uuid(value: str, param_name: str) -> UUID:
    """
    Convert a string to a UUID, raising a clear ValueError with context
    if the string is not a valid UUID format.
    """
    try:
        return UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ValueError(
            f"Invalid {param_name}: expected a valid UUID string, got {value!r}"
        ) from exc


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
    # 0. Validate and convert UUIDs once at entry
    try:
        user_uuid = _safe_to_uuid(user_id, "user_id")
    except ValueError:
        logger.error(
            "schedule_if_allowed called with invalid user_id: %r – "
            "skipping notification (pref_flag=%s)",
            user_id,
            pref_flag,
        )
        return

    workspace_uuid: UUID | None = None
    if workspace_id:
        try:
            workspace_uuid = _safe_to_uuid(workspace_id, "workspace_id")
        except ValueError:
            logger.error(
                "schedule_if_allowed called with invalid workspace_id: %r – "
                "skipping notification (pref_flag=%s)",
                workspace_id,
                pref_flag,
            )
            return

    # 1. Load or create preferences (guarantees a record always exists)
    pref_service = NotificationPreferencesService(db)
    pref = await pref_service.get_or_create(user_uuid)

    logger.debug(
        "Notification preferences for user %s: in_app=%s", user_id, pref.in_app_notifications
    )
    logger.debug("Checking preference flag: %s", pref_flag)
    if not pref:
        # This branch is technically unreachable now because get_or_create guarantees a record,
        # but we keep it for defensive stability.
        logger.debug("No NotificationPreferences row for user %s", user_id)
        return

    # 3. Global master switch for in-app notifications
    if not pref.in_app_notifications:
        logger.debug("User %s disabled all in-app notifications.", user_id)
        return

    # 3. Specific flag
    # Handle virtual flags mapping to real columns
    real_pref_column = pref_flag
    if pref_flag in ["profile_update_failed", "avatar_uploaded", "avatar_upload_failed"]:
        real_pref_column = "in_app_notifications"

    # Dedicated column (in_app_notifications) — access via attribute.
    # Category preferences live in JSONB — use get_preference().
    if real_pref_column == "in_app_notifications":
        flag_enabled = pref.in_app_notifications
    else:
        flag_enabled = pref.get_preference(real_pref_column)

    if not flag_enabled:
        logger.debug(
            "User %s has preference %s=False – skipping notification.",
            user_id,
            real_pref_column,
        )
        return

    # 4️⃣ Resolve notification configuration
    config = NOTIFICATION_REGISTRY.get(pref_flag)
    if not config:
        logger.error(
            "Notification flag %r not found in NOTIFICATION_REGISTRY – "
            "skipping notification for user %s",
            pref_flag,
            user_id,
        )
        return

    notification_type = config.notification_type

    # 4.5 Re-check preferences with row-level lock to prevent TOCTOU race
    if not await _recheck_preference_enabled(db, user_uuid, pref_flag):
        logger.info(
            "Notification suppressed for user %s – preference %s "
            "was disabled between initial check and creation (TOCTOU prevented).",
            user_id,
            pref_flag,
        )
        return

    # 4.6 Sanitize message and payload to prevent stored XSS (TASK-280)
    safe_message = html_escape(message[:2000]) if message else ""
    safe_payload = sanitize_notification_payload(payload)

    # 4.7 Deduplication check — prevent duplicate notifications within time window
    from src.api.models.notification.notification_model import Notification

    dedup_cutoff = datetime.now(timezone.utc) - timedelta(seconds=DEDUP_WINDOW_SECONDS)
    dedup_conditions = [
        Notification.user_id == user_uuid,
        Notification.category == pref_flag,
        Notification.created_at >= dedup_cutoff,
        Notification.is_deleted.is_(False),
    ]
    if workspace_uuid:
        dedup_conditions.append(Notification.workspace_id == workspace_uuid)
    else:
        dedup_conditions.append(Notification.workspace_id.is_(None))

    existing_count_result = await db.execute(
        select(func.count(Notification.id)).where(and_(*dedup_conditions))
    )
    if existing_count_result.scalar() > 0:
        logger.info(
            f"Duplicate notification suppressed for user {user_id} – "
            f"category: {pref_flag}, workspace: {workspace_id}, "
            f"window: {DEDUP_WINDOW_SECONDS}s"
        )
        return

    # 5. Create notification record in database

    notification = Notification(
        user_id=user_uuid,
        workspace_id=workspace_uuid,
        title=config["title"],
        message=message,
        type=config["type"],
        category=pref_flag,
        status=config["status"],
        priority="normal",
        payload=safe_payload,
        is_read=False,
        sent_via_sse=True,
        sse_sent_at=datetime.now(timezone.utc),
    )

    # 5a. Attempt to persist notification record
    try:
        db.add(notification)
        await db.flush()
        await db.refresh(notification)
        logger.info(
            "Created notification record %s for user %s – type: %s, category: %s",
            notification.id,
            user_id,
            notification_type,
            pref_flag,
        )
    except IntegrityError as exc:
        # Constraint violation (duplicate, FK missing, etc.)
        # Expunge the dirty object and rollback to restore session health
        await db.rollback()
        db.expunge(notification)
        logger.warning(
            "IntegrityError persisting notification for user %s "
            "(type=%s, category=%s): %s. Notification record skipped; SSE will still be sent.",
            user_id,
            notification_type,
            pref_flag,
            exc,
        )
    except OperationalError as exc:
        # Connection lost, deadlock, timeout, etc.
        await db.rollback()
        db.expunge(notification)
        logger.warning(
            "OperationalError persisting notification for user %s "
            "(type=%s, category=%s): %s. Notification record skipped; SSE will still be sent.",
            user_id,
            notification_type,
            pref_flag,
            exc,
        )
    except Exception as exc:
        # Catch-all for unexpected DB errors (e.g., ProgrammingError, DataError)
        await db.rollback()
        try:
            db.expunge(notification)
        except Exception:
            pass  # Object may not be in session after certain errors
        logger.error(
            "Unexpected error persisting notification for user %s "
            "(type=%s, category=%s): %s. Notification record skipped; SSE will still be sent.",
            user_id,
            notification_type,
            pref_flag,
            exc,
            exc_info=True,
        )

    logger.info(
        f"Created notification record {notification.id} for user {user_id} — "
        f"type: {config['type']}, category: {pref_flag}"
    )

    # 6. Schedule the SSE notification
    logger.info(
        f"Scheduling SSE notification for user {user_id} — flag {pref_flag} — message: {message}"
    )
    background_tasks.add_task(
        _send_sse_after_commit,
        user_id=user_uuid,
        message=safe_message,
        payload=safe_payload,
        notification_id=str(notification.id),
    )
    logger.debug("SSE notification task scheduled for notification %s", notification.id)
