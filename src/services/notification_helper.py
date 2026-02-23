from uuid import UUID
from typing import Optional
from fastapi import BackgroundTasks
from html import escape as html_escape
from src.services.notifications_services import notification_service
from src.services.notification_preferences_service import NotificationPreferencesService
from src.api.models.user_models.notification_preferences import NotificationPreferences
from src.utils.payload_sanitizer import sanitize_notification_payload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.exc import IntegrityError, OperationalError
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)

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

# ==============================
# NOTIFICATION CONFIGURATION
# ==============================
# Single source of truth for all notification flags.
# Keys are pref_flag values passed to schedule_if_allowed().
# "pref_column" is the actual column on NotificationPreferences to check.
# If pref_column matches the flag name, it's a "real" column.
# If pref_column differs, it's a "virtual" flag mapped to a real column.

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

    # Resolve the real preference column via the registry (single source of truth)
    recheck_config = NOTIFICATION_REGISTRY.get(pref_flag)
    real_pref_column = (recheck_config.pref_column if recheck_config and recheck_config.pref_column else pref_flag)

    flag_enabled = getattr(pref, real_pref_column, False)
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
            f"Invalid {param_name}: expected a valid UUID string, "
            f"got {value!r}"
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

    logger.debug("Notification preferences for user %s: in_app=%s", user_id, pref.in_app_notifications)
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

    # 3️⃣ Resolve preference column and check specific flag
    config = NOTIFICATION_REGISTRY.get(pref_flag)
    if config is None:
        logger.warning(
            "Unknown notification pref_flag '%s' for user %s — using defaults",
            pref_flag,
            user_id,
        )
        config = NotificationConfig(
            notification_type="system",
            title="Notification",
        )

    real_pref_column = config.pref_column or pref_flag
    flag_enabled = getattr(pref, real_pref_column, False)
    if not flag_enabled:
        logger.debug(
            "User %s has preference %s=False – skipping notification.",
            user_id,
            real_pref_column,
        )
        return

    # 4️⃣ Use resolved notification metadata
    notification_type = config.notification_type
    notification_status = config.status
    notification_title = config.title


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
    from datetime import datetime, timezone

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
        payload=safe_payload,
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
