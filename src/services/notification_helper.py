from uuid import UUID
from fastapi import BackgroundTasks
from src.services.notifications_services import notification_service
from src.api.models.user_models.notification_preferences import NotificationPreferences
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
import logging

logger = logging.getLogger(__name__)

async def _recheck_preference_enabled(
    db: AsyncSession,
    user_id: UUID,  # Changed from str to UUID
    pref_flag: str,
) -> bool:
    """
    Re-read the user's notification preferences with a row-level lock
    (SELECT ... FOR UPDATE) immediately before creating a notification.

    This closes the TOCTOU race window by:
    1. Acquiring an exclusive lock on the preferences row, preventing concurrent
       updates from committing until this transaction completes.
    2. Reading the latest committed state of the preference, not a stale snapshot.

    Returns True if the notification should proceed, False otherwise.
    """
    result = await db.execute(
        select(NotificationPreferences)
        .where(NotificationPreferences.user_id == user_id)
        .with_for_update()
    )
    pref = result.scalar_one_or_none()

    if not pref:
        logger.debug(f"[recheck] No NotificationPreferences row for user {user_id}")
        return False

    if not pref.in_app_notifications:
        logger.debug(f"[recheck] User {user_id} has disabled all in-app notifications.")
        return False

    # Map virtual flags to real columns (same logic as main function)
    real_pref_column = pref_flag
    if pref_flag in ["profile_update_failed", "avatar_uploaded", "avatar_upload_failed"]:
        real_pref_column = "in_app_notifications"

    flag_enabled = getattr(pref, real_pref_column, False)
    if not flag_enabled:
        logger.debug(
            f"[recheck] User {user_id} has {real_pref_column}=False – "
            "notification suppressed after re-check."
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
            f"Invalid {param_name}: expected a valid UUID string, "
            f"got {value!r}"
        ) from exc


# src/services/notification_helper.py
async def schedule_if_allowed(
    *,
    db: AsyncSession,
    user_id: str,
    background_tasks: BackgroundTasks,
    pref_flag: str,
    message: str,
    payload: dict,
    workspace_id: str = None,
) -> None:
    """
    Load the user's NotificationPreferences, check the master in-app toggle
    (in_app_notifications) and the specific Boolean column named ``pref_flag``.
    If both are True, schedule ``notification_service.send_success_notification``
    AND persist the notification to the database.
    """
    # 0. Validate and convert UUIDs once at entry
    try:
        user_uuid = _safe_to_uuid(user_id, "user_id")
    except ValueError:
        logger.error(
            f"schedule_if_allowed called with invalid user_id: {user_id!r} – "
            f"skipping notification (pref_flag={pref_flag})"
        )
        return

    workspace_uuid: UUID | None = None
    if workspace_id:
        try:
            workspace_uuid = _safe_to_uuid(workspace_id, "workspace_id")
        except ValueError:
            logger.error(
                f"schedule_if_allowed called with invalid workspace_id: "
                f"{workspace_id!r} – skipping notification (pref_flag={pref_flag})"
            )
            return

    # 1. Load preferences
    result = await db.execute(
        select(NotificationPreferences).where(
            NotificationPreferences.user_id == user_uuid
        )
    )
    pref = result.scalar_one_or_none()
    logger.info(f"preferences: ----------------------------------: {pref}")
    logger.info(f"Flag----------------------------------: {pref_flag}")
    if not pref:
        logger.debug(f"No NotificationPreferences row for user {user_id}")
        return

    # 2. Global master switch for in-app notifications
    if not pref.in_app_notifications:
        logger.debug(f"User {user_id} disabled all in-app notifications.")
        return

    # 3. Specific flag
    # Handle virtual flags mapping to real columns
    real_pref_column = pref_flag
    if pref_flag in ["profile_update_failed", "avatar_uploaded", "avatar_upload_failed"]:
        real_pref_column = "in_app_notifications"

    flag_enabled = getattr(pref, real_pref_column, False)
    if not flag_enabled:
        logger.debug(
            f"User {user_id} has preference {real_pref_column}=False – skipping notification."
        )
        return

    # 4. Determine notification type and status based on pref_flag
    notification_type = "system"
    notification_status = "success"
    notification_title = "Notification"

    # Map pref_flag to notification type and generate title
    if pref_flag.startswith("ws_"):
        notification_type = "workspace"
        if pref_flag == "ws_invite_received":
            notification_title = "Workspace Invitation"
        elif pref_flag == "ws_invite_accepted":
            notification_title = "Invitation Accepted"
        elif pref_flag == "ws_role_changed":
            notification_title = "Role Changed"
        elif pref_flag == "ws_member_removed":
            notification_title = "Member Removed"
    elif pref_flag.startswith("billing_"):
        notification_type = "billing"
        if pref_flag == "billing_payment_success":
            notification_title = "Payment Successful"
        elif pref_flag == "billing_payment_failed":
            notification_title = "Payment Failed"
            notification_status = "error"
        elif pref_flag == "billing_subscription_cancelled":
            notification_title = "Subscription Cancelled"
            notification_status = "warning"
        elif pref_flag == "billing_subscription_expiring":
            notification_title = "Subscription Expiring"
            notification_status = "warning"
        elif pref_flag == "billing_trial_ending":
            notification_title = "Trial Ending"
            notification_status = "warning"
        elif pref_flag == "billing_usage_limit_warning":
            notification_title = "Usage Limit Warning"
            notification_status = "warning"
        elif pref_flag == "billing_usage_limit_exceeded":
            notification_title = "Usage Limit Exceeded"
            notification_status = "error"
    elif pref_flag.startswith("kb_"):
        notification_type = "knowledge"
        if pref_flag == "kb_processing_completed":
            notification_title = "Knowledge Processing Complete"
        elif pref_flag == "kb_processing_failed":
            notification_title = "Knowledge Processing Failed"
            notification_status = "error"
    elif pref_flag.startswith("gen_"):
        notification_type = "content"
        if pref_flag == "gen_started":
            notification_title = "Content Generation Started"
            notification_status = "info"
        elif pref_flag == "gen_completed":
            notification_title = "Content Generation Complete"
        elif pref_flag == "gen_failed":
            notification_title = "Content Generation Failed"
            notification_status = "error"
        elif pref_flag == "gen_published":
            notification_title = "Content Published"
    elif pref_flag == "in_app_notifications":
        notification_type = "user"
        notification_title = "Profile Updated"
    elif pref_flag == "profile_update_failed":
        notification_type = "user"
        notification_title = "Profile Update Failed"
        notification_status = "error"
    elif pref_flag == "avatar_uploaded":
        notification_type = "user"
        notification_title = "Avatar Updated"
    elif pref_flag == "avatar_upload_failed":
        notification_type = "user"
        notification_title = "Avatar Upload Failed"
        notification_status = "error"


    # 4.5 Re-check preferences with row-level lock to prevent TOCTOU race
    if not await _recheck_preference_enabled(db, user_uuid, pref_flag):
        logger.info(
            f"Notification suppressed for user {user_id} – preference {pref_flag} "
            "was disabled between initial check and creation (TOCTOU prevented)."
        )
        return

    # 5. Create notification record in database
    from src.api.models.notification.notification_model import Notification
    from datetime import datetime, timezone

    notification = Notification(
        user_id=user_uuid,
        workspace_id=workspace_uuid,
        title=notification_title,
        message=message,
        type=notification_type,
        category=pref_flag,
        status=notification_status,
        priority="normal",
        payload=payload,
        is_read=False,
        sent_via_sse=True,
        sse_sent_at=datetime.now(timezone.utc),
    )

    # 5a. Attempt to persist notification record
    db_persist_ok = False
    try:
        db.add(notification)
        await db.flush()
        await db.refresh(notification)
        db_persist_ok = True
        logger.info(
            f"Created notification record {notification.id} for user {user_id} – "
            f"type: {notification_type}, category: {pref_flag}"
        )
    except IntegrityError as exc:
        # Constraint violation (duplicate, FK missing, etc.)
        # Expunge the dirty object and rollback to restore session health
        await db.rollback()
        db.expunge(notification)
        logger.warning(
            f"IntegrityError persisting notification for user {user_id} "
            f"(type={notification_type}, category={pref_flag}): {exc}. "
            "Notification record skipped; SSE will still be sent."
        )
    except OperationalError as exc:
        # Connection lost, deadlock, timeout, etc.
        await db.rollback()
        db.expunge(notification)
        logger.warning(
            f"OperationalError persisting notification for user {user_id} "
            f"(type={notification_type}, category={pref_flag}): {exc}. "
            "Notification record skipped; SSE will still be sent."
        )
    except Exception as exc:
        # Catch-all for unexpected DB errors (e.g., ProgrammingError, DataError)
        await db.rollback()
        try:
            db.expunge(notification)
        except Exception:
            pass  # Object may not be in session after certain errors
        logger.error(
            f"Unexpected error persisting notification for user {user_id} "
            f"(type={notification_type}, category={pref_flag}): {exc}. "
            "Notification record skipped; SSE will still be sent.",
            exc_info=True,
        )

    # 6. Schedule the SSE notification (always, even if DB persistence failed)
    logger.info(
        f"Scheduling SSE notification for user {user_id} – flag {pref_flag} – message: {message}"
        + (" (DB record saved)" if db_persist_ok else " (DB record NOT saved)")
    )
    background_tasks.add_task(
        notification_service.send_success_notification,
        user_id=user_uuid,
        message=message,
        payload=payload,
    )
    logger.info("Notification task scheduled.")