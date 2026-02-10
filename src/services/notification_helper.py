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
    workspace_id: str = None,
) -> None:
    """
    Load the user's NotificationPreferences, check the master in‑app toggle
    (in_app_notifications) and the specific Boolean column named ``pref_flag``.
    If both are True, schedule ``notification_service.send_success_notification``
    AND persist the notification to the database.
    """
    # 1️⃣ Load preferences
    result = await db.execute(
        select(NotificationPreferences).where(NotificationPreferences.user_id == UUID(user_id))
    )
    pref = result.scalar_one_or_none()
    logger.info(f"preferences: ----------------------------------: {pref}")
    logger.info(f"Flag----------------------------------: {pref_flag}")
    if not pref:
        logger.debug(f"No NotificationPreferences row for user {user_id}")
        return

    # 2️⃣ Global master switch for in‑app notifications
    if not pref.in_app_notifications:
        logger.debug(f"User {user_id} disabled all in‑app notifications.")
        return

    # 3️⃣ Specific flag
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

    # 4️⃣ Determine notification type and status based on pref_flag
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
    
    # 5️⃣ Create notification record in database
    from src.api.models.notification.notification_model import Notification
    from datetime import datetime
    
    notification = Notification(
        user_id=UUID(user_id),
        workspace_id=UUID(workspace_id) if workspace_id else None,
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
    
    db.add(notification)
    await db.commit()
    await db.refresh(notification)
    
    logger.info(
        f"Created notification record {notification.id} for user {user_id} – "
        f"type: {notification_type}, category: {pref_flag}"
    )

    # 6️⃣ Schedule the SSE notification
    logger.info(
        f"Scheduling SSE notification for user {user_id} – flag {pref_flag} – message: {message}"
    )
    background_tasks.add_task(
        notification_service.send_success_notification,
        user_id=UUID(user_id),
        message=message,
        payload=payload,
    )
    logger.info("Notification task scheduled.")



# async def schedule_email_if_allowed(
#     *,
#     db: AsyncSession,
#     user_id: str,
#     background_tasks: BackgroundTasks,
#     pref_flag: str,          # e.g. "email_workspace_invite"
#     email_task_callable,    # e.g. send_workspace_invitation_email_task
#     task_kwargs: dict,
# ) -> None:
#     """
#     Load the user's NotificationPreferences, check the master email toggle
#     (email_notifications) and the specific Boolean column ``pref_flag``.
#     If both are True, schedule the provided email background task.
#     """
#     result = await db.execute(
#         select(NotificationPreferences).where(NotificationPreferences.user_id == UUID(user_id))
#     )
#     pref: NotificationPreferences | None = result.scalar_one_or_none()
#     if not pref:
#         logger.debug(f"No NotificationPreferences row for user {user_id}")
#         return

#     # Global master switch for email
#     if not pref.email_notifications:
#         logger.debug(f"User {user_id} disabled all email notifications.")
#         return

#     # Specific flag
#     flag_enabled = getattr(pref, pref_flag, False)
#     if not flag_enabled:
#         logger.debug(
#             f"User {user_id} has preference {pref_flag}=False – skipping email."
#         )
#         return

#     logger.info(
#         f"Scheduling email task for user {user_id} – flag {pref_flag}"
#     )
#     background_tasks.add_task(email_task_callable, **task_kwargs)
#     logger.info("Email background task scheduled.")
