# src/api/services/notification_helper.py
from uuid import UUID
from fastapi import BackgroundTasks
from src.services.notifications_services import notification_service
from src.api.models.user_models.notification_preferences import NotificationPreferences
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging

logger = logging.getLogger(__name__)

# src/services/notification_helper.py
async def schedule_if_allowed(
    *,
    db: AsyncSession,
    user_id: str,
    background_tasks: BackgroundTasks,
    pref_flag: str,
    message: str,
    payload: dict,
) -> None:
    """
    Load the user's NotificationPreferences, check the master in‑app toggle
    (in_app_notifications) and the specific Boolean column named ``pref_flag``.
    If both are True, schedule ``notification_service.send_success_notification``.
    """
    # 1️⃣ Load preferences
    result = await db.execute(
        select(NotificationPreferences).where(NotificationPreferences.user_id == UUID(user_id))
    )
    pref: NotificationPreferences | None = result.scalar_one_or_none()
    if not pref:
        logger.debug(f"No NotificationPreferences row for user {user_id}")
        return

    # 2️⃣ Global master switch for in‑app notifications
    if not pref.in_app_notifications:
        logger.debug(f"User {user_id} disabled all in‑app notifications.")
        return

    # 3️⃣ Specific flag
    flag_enabled = getattr(pref, pref_flag, False)
    if not flag_enabled:
        logger.debug(
            f"User {user_id} has preference {pref_flag}=False – skipping notification."
        )
        return

    # 4️⃣ Schedule the SSE notification
    logger.info(
        f"Scheduling notification for user {user_id} – flag {pref_flag} – message: {message}"
    )
    background_tasks.add_task(
        notification_service.send_success_notification,
        user_id=UUID(user_id),
        message=message,
        payload=payload,
    )
    logger.info("Notification task scheduled.")



async def schedule_email_if_allowed(
    *,
    db: AsyncSession,
    user_id: str,
    background_tasks: BackgroundTasks,
    pref_flag: str,          # e.g. "email_workspace_invite"
    email_task_callable,    # e.g. send_workspace_invitation_email_task
    task_kwargs: dict,
) -> None:
    """
    Load the user's NotificationPreferences, check the master email toggle
    (email_notifications) and the specific Boolean column ``pref_flag``.
    If both are True, schedule the provided email background task.
    """
    result = await db.execute(
        select(NotificationPreferences).where(NotificationPreferences.user_id == UUID(user_id))
    )
    pref: NotificationPreferences | None = result.scalar_one_or_none()
    if not pref:
        logger.debug(f"No NotificationPreferences row for user {user_id}")
        return

    # Global master switch for email
    if not pref.email_notifications:
        logger.debug(f"User {user_id} disabled all email notifications.")
        return

    # Specific flag
    flag_enabled = getattr(pref, pref_flag, False)
    if not flag_enabled:
        logger.debug(
            f"User {user_id} has preference {pref_flag}=False – skipping email."
        )
        return

    logger.info(
        f"Scheduling email task for user {user_id} – flag {pref_flag}"
    )
    background_tasks.add_task(email_task_callable, **task_kwargs)
    logger.info("Email background task scheduled.")