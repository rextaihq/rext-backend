"""
Email Helper Functions

Centralized helpers for sending emails with template integration.
"""

from typing import Literal, Optional
from uuid import UUID

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.lib.logger import auto_logger
from src.services.email_service import EmailService

logger = auto_logger()


async def send_auth_email(
    db: AsyncSession,
    email_type: Literal[
        "verification",
        "password_reset",
        "password_changed",
        "welcome",
        "account_recovery",
        "account_deactivated",
        "account_deleted",
        "account_recovery_received",
        "account_recovery_approved",
        "account_recovery_rejected",
    ],
    recipient_email: str,
    user_name: str,
    user_id: UUID,
    token: str = None,
    frontend_url: str = None,
    background_tasks: BackgroundTasks = None,
    **kwargs,
) -> bool:
    """
    Send authentication email using Python templates.

    Args:
        db: Database session
        email_type: Type of auth email
        recipient_email: Recipient's email address
        user_name: User's name for personalization
        user_id: User ID for logging
        token: Verification or reset token (if applicable)
        frontend_url: Frontend URL for links
        background_tasks: FastAPI background tasks (optional)
        **kwargs: Additional template variables

    Returns:
        bool: True if email sent successfully
    """
    try:
        # Get unsubscribe token for user preferences
        from src.services.email_preferences_service import EmailPreferencesService

        prefs_service = EmailPreferencesService(db)
        prefs = await prefs_service.get_or_create_preferences(user_id)
        unsubscribe_token = prefs.unsubscribe_token

        # Import templates
        from emails.templates.auth import (
            create_account_deactivated_email,
            create_account_deleted_email,
            create_account_recovery_approved_email,
            create_account_recovery_email,
            create_account_recovery_received_email,
            create_account_recovery_rejected_email,
            create_password_changed_email,
            create_password_reset_email,
            create_verification_email,
            create_welcome_email,
        )

        # Generate HTML based on type
        if email_type == "verification":
            html = create_verification_email(
                user_name=user_name,
                verification_token=token,
                frontend_url=frontend_url,
                unsubscribe_token=unsubscribe_token,
            )
            subject = "Verify Your Email Address - Rext AI"

        elif email_type == "password_reset":
            html = create_password_reset_email(
                user_name=user_name,
                reset_token=token,
                user_email=recipient_email,
                frontend_url=frontend_url,
                unsubscribe_token=unsubscribe_token,
            )
            subject = "Reset Your Password - Rext AI"

        elif email_type == "password_changed":
            html = create_password_changed_email(
                user_name=user_name,
                changed_at=kwargs.get("changed_at", "recently"),
                ip_address=kwargs.get("ip_address"),
                user_agent=kwargs.get("user_agent"),
                frontend_url=frontend_url,
                unsubscribe_token=unsubscribe_token,
            )
            subject = "Your Password Has Been Changed - Rext AI"

        elif email_type == "welcome":
            html = create_welcome_email(
                user_name=user_name, frontend_url=frontend_url, unsubscribe_token=unsubscribe_token
            )
            subject = "Welcome to Rext AI!"

        elif email_type == "account_recovery":
            html = create_account_recovery_email(
                user_name=user_name,
                recovery_token=token,
                user_email=recipient_email,
                frontend_url=frontend_url,
                unsubscribe_token=unsubscribe_token,
                retention_days=kwargs.get("retention_days", 14),
            )
            subject = "Restore Your Rext AI Account"

        elif email_type == "account_deactivated":
            html = create_account_deactivated_email(
                user_name=user_name,
                frontend_url=frontend_url,
                unsubscribe_token=unsubscribe_token,
                retention_days=kwargs.get("retention_days", 14),
                plan_ends_on=kwargs.get("plan_ends_on"),
            )
            subject = "Your Rext AI Account Has Been Deactivated"

        elif email_type == "account_deleted":
            html = create_account_deleted_email(
                user_name=user_name,
                user_email=recipient_email,
                retention_days=kwargs.get("retention_days", 14),
                frontend_url=frontend_url,
                unsubscribe_token=unsubscribe_token,
            )
            subject = "Your Rext AI Account Has Been Deleted"

        elif email_type == "account_recovery_received":
            html = create_account_recovery_received_email(
                user_name=user_name,
                user_email=recipient_email,
                frontend_url=frontend_url,
                unsubscribe_token=unsubscribe_token,
            )
            subject = "We've Received Your Account Recovery Request - Rext AI"

        elif email_type == "account_recovery_approved":
            html = create_account_recovery_approved_email(
                user_name=user_name,
                review_note=kwargs.get("review_note"),
                frontend_url=frontend_url,
                unsubscribe_token=unsubscribe_token,
            )
            subject = "Your Rext AI Account Has Been Restored"

        elif email_type == "account_recovery_rejected":
            html = create_account_recovery_rejected_email(
                user_name=user_name,
                review_note=kwargs.get("review_note"),
                frontend_url=frontend_url,
                unsubscribe_token=unsubscribe_token,
            )
            subject = "Update on Your Rext AI Account Recovery Request"

        else:
            raise ValueError(f"Unknown email type: {email_type}")

        # Send email
        email_service = EmailService(db)

        if background_tasks:
            # Queue as background task
            background_tasks.add_task(
                _send_email_task,
                db=db,
                recipient_email=recipient_email,
                subject=subject,
                html=html,
                user_id=user_id,
                email_type=email_type,
            )
        else:
            # Send immediately
            await email_service.send_email(
                to=recipient_email,
                subject=subject,
                html=html,
                user_id=user_id,
                template_type=email_type,
                tags={"type": "auth", "action": email_type},
            )

        logger.info(
            "Auth email queued/sent", extra={"email_type": email_type, "recipient": recipient_email}
        )
        return True

    except Exception as e:
        logger.error(
            f"Failed to send auth email: {str(e)}",
            extra={"email_type": email_type, "recipient": recipient_email},
            exc_info=True,
        )
        return False


async def send_workspace_email(
    db: AsyncSession,
    email_type: Literal[
        "invitation",
        "invitation_accepted",
        "role_changed",
        "member_removed",
        "workspace_deleted",
        "workspace_restored",
    ],
    workspace_id: UUID,
    recipient_email: str,
    user_id: UUID = None,
    background_tasks: BackgroundTasks = None,
    **context,
) -> bool:
    """
    Send workspace email using DB templates with preferences check.

    Args:
        db: Database session
        email_type: Type of workspace email
        workspace_id: Workspace ID for template lookup
        recipient_email: Recipient's email address
        user_id: User ID for preferences check (if applicable)
        background_tasks: FastAPI background tasks (optional)
        **context: Template context variables

    Returns:
        bool: True if email sent successfully
    """
    try:
        # Get unsubscribe token if user_id provided
        unsubscribe_token = None
        if user_id:
            from src.services.email_preferences_service import EmailPreferencesService

            prefs_service = EmailPreferencesService(db)

            # Check email preferences
            can_send = await prefs_service.check_can_send(user_id, email_type)
            if not can_send:
                logger.info(
                    "Email blocked by user preferences",
                    extra={"user_id": str(user_id), "email_type": email_type},
                )
                return False

            # Get unsubscribe token
            prefs = await prefs_service.get_or_create_preferences(user_id)
            unsubscribe_token = prefs.unsubscribe_token

        # Add unsubscribe token and workspace_id to context for templates
        # (workspace_id is consumed as a named param above for the custom-template
        # lookup, so it must be re-added here or templates never get it and fall
        # back to a generic, non-workspace-specific link).
        context_with_token = {
            **context,
            "unsubscribe_token": unsubscribe_token,
            "workspace_id": str(workspace_id),
        }

        from emails.templates.workspace import (
            create_invitation_accepted_email,
            create_member_removed_email,
            create_role_changed_email,
            create_workspace_deleted_email,
            create_workspace_invitation_email,
            create_workspace_restored_email,
        )
        from src.utils.email_template_utils import render_template

        # Check for workspace-specific custom DB template (admin-created, not default)
        html = None
        subject = None
        try:
            from sqlalchemy import String, cast, select

            from src.api.models.workspace_models.email_template import EmailTemplate

            result = await db.execute(
                select(EmailTemplate).where(
                    EmailTemplate.workspace_id == str(workspace_id),
                    cast(EmailTemplate.template_type, String) == email_type,
                    EmailTemplate.is_active.is_(True),
                    EmailTemplate.is_default.is_(False),
                )
            )
            custom = result.scalar_one_or_none()
            if custom:
                subject = render_template(custom.subject, context_with_token)
                html = render_template(custom.body, context_with_token)
        except Exception as e:
            logger.warning(f"Custom DB template lookup failed: {str(e)}")

        if html is None:
            if email_type == "invitation":
                html = create_workspace_invitation_email(**context_with_token)
                subject = f"You're invited to join {context.get('workspace_name', 'a workspace')}"
            elif email_type == "invitation_accepted":
                html = create_invitation_accepted_email(**context_with_token)
                subject = f"{context.get('new_member_name', 'A member')} joined {context.get('workspace_name', 'your workspace')}"
            elif email_type == "role_changed":
                html = create_role_changed_email(**context_with_token)
                subject = (
                    f"Your role in {context.get('workspace_name', 'workspace')} has been updated"
                )
            elif email_type == "member_removed":
                html = create_member_removed_email(**context_with_token)
                subject = f"You've been removed from {context.get('workspace_name', 'a workspace')}"
            elif email_type == "workspace_deleted":
                html = create_workspace_deleted_email(**context_with_token)
                subject = f"Workspace '{context.get('workspace_name', 'your workspace')}' has been deleted"
            elif email_type == "workspace_restored":
                html = create_workspace_restored_email(**context_with_token)
                subject = f"Workspace '{context.get('workspace_name', 'your workspace')}' has been restored"
            else:
                raise ValueError(f"Unknown workspace email type: {email_type}")

        # Send email
        email_service = EmailService(db)

        if background_tasks:
            background_tasks.add_task(
                _send_email_task,
                db=db,
                recipient_email=recipient_email,
                subject=subject,
                html=html,
                user_id=user_id,
                workspace_id=workspace_id,
                email_type=email_type,
            )
        else:
            await email_service.send_email(
                to=recipient_email,
                subject=subject,
                html=html,
                user_id=user_id,
                workspace_id=workspace_id,
                template_type=email_type,
                tags={"type": "workspace", "action": email_type},
            )

        logger.info(
            "Workspace email queued/sent",
            extra={
                "email_type": email_type,
                "workspace_id": str(workspace_id),
                "recipient": recipient_email,
            },
        )
        return True

    except Exception as e:
        logger.error(
            f"Failed to send workspace email: {str(e)}",
            extra={
                "email_type": email_type,
                "workspace_id": str(workspace_id),
                "recipient": recipient_email,
            },
            exc_info=True,
        )
        return False


async def send_content_publish_failed_email(
    db: AsyncSession,
    recipient_email: str,
    user_id: UUID,
    user_name: str,
    content_title: str,
    site_url: str,
    error_message: str,
    will_retry: bool,
    attempt_number: int,
    max_retries: int,
    retry_url: str,
    reschedule_url: str,
    next_retry_at: Optional[str] = None,
    workspace_id: Optional[UUID] = None,
) -> bool:
    """
    Send a scheduled-publish-failure email to the content owner.

    Args:
        db: Database session
        recipient_email: Owner's email address
        user_id: Owner's user ID for logging
        user_name: Owner's name for personalization
        content_title: Title of the content that failed to publish
        site_url: URL of the WordPress site the content was being published to
        error_message: User-friendly error message
        will_retry: True if the system will automatically retry, False if attempts are exhausted
        attempt_number: The attempt number that just failed
        max_retries: Maximum number of attempts configured
        retry_url: URL to retry publishing immediately
        reschedule_url: URL to pick a new publish time
        next_retry_at: When the automatic retry will run (only used if will_retry=True)
        workspace_id: Associated workspace ID (optional)

    Returns:
        bool: True if email sent successfully
    """
    try:
        from emails.templates.content import render_content_publish_failed_email

        html = render_content_publish_failed_email(
            user_name=user_name,
            content_title=content_title,
            site_url=site_url,
            error_message=error_message,
            will_retry=will_retry,
            attempt_number=attempt_number,
            max_retries=max_retries,
            retry_url=retry_url,
            reschedule_url=reschedule_url,
            next_retry_at=next_retry_at,
        )
        subject = (
            f"Scheduled publish delayed: {content_title}"
            if will_retry
            else f"Scheduled publish failed: {content_title}"
        )

        email_service = EmailService(db)
        await email_service.send_email(
            to=recipient_email,
            subject=subject,
            html=html,
            user_id=user_id,
            workspace_id=workspace_id,
            template_type="content_publish_failed",
            tags={"type": "content", "action": "publish_failed"},
        )

        logger.info(
            "Scheduled publish failure email sent",
            extra={
                "recipient": recipient_email,
                "will_retry": will_retry,
                "attempt_number": attempt_number,
            },
        )
        return True

    except Exception as e:
        logger.error(
            f"Failed to send scheduled publish failure email: {str(e)}",
            extra={
                "recipient": recipient_email,
            },
            exc_info=True,
        )
        return False


async def _send_email_task(
    db: AsyncSession,
    recipient_email: str,
    subject: str,
    html: str,
    user_id: UUID = None,
    workspace_id: UUID = None,
    email_type: str = None,
):
    """
    Internal background task for sending emails.

    This function is called by background_tasks.add_task().
    """
    from src.api.database.async_database import get_async_db_context

    try:
        async with get_async_db_context() as async_db:
            email_service = EmailService(async_db)
            await email_service.send_email(
                to=recipient_email,
                subject=subject,
                html=html,
                user_id=user_id,
                workspace_id=workspace_id,
                template_type=email_type,
                tags={"background_task": True},
            )
            logger.info(f"Background email sent successfully to {recipient_email}")
    except Exception as e:
        logger.error(f"Background email task failed for {recipient_email}: {str(e)}", exc_info=True)
