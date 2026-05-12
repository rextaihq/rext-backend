"""
Email Helper Functions

Centralized helpers for sending emails with template integration.
"""
from typing import Literal, Optional
from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from src.services.email_service import EmailService
from src.api.lib.logger import auto_logger

logger = auto_logger()


async def send_auth_email(
    db: AsyncSession,
    email_type: Literal["verification", "password_reset", "password_changed", "welcome"],
    recipient_email: str,
    user_name: str,
    user_id: UUID,
    token: str = None,
    frontend_url: str = None,
    background_tasks: BackgroundTasks = None,
    **kwargs
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
            create_verification_email,
            create_password_reset_email,
            create_password_changed_email,
            create_welcome_email
        )

        # Generate HTML based on type
        if email_type == "verification":
            html = create_verification_email(
                user_name=user_name,
                verification_token=token,
                frontend_url=frontend_url,
                unsubscribe_token=unsubscribe_token
            )
            subject = "Verify Your Email Address - REXT"

        elif email_type == "password_reset":
            html = create_password_reset_email(
                user_name=user_name,
                reset_token=token,
                user_email=recipient_email,
                frontend_url=frontend_url,
                unsubscribe_token=unsubscribe_token
            )
            subject = "Reset Your Password - REXT"

        elif email_type == "password_changed":
            html = create_password_changed_email(
                user_name=user_name,
                changed_at=kwargs.get('changed_at', 'recently'),
                ip_address=kwargs.get('ip_address'),
                user_agent=kwargs.get('user_agent'),
                frontend_url=frontend_url,
                unsubscribe_token=unsubscribe_token
            )
            subject = "Your Password Has Been Changed - REXT"

        elif email_type == "welcome":
            html = create_welcome_email(
                user_name=user_name,
                frontend_url=frontend_url,
                unsubscribe_token=unsubscribe_token
            )
            subject = "Welcome to REXT!"

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
                email_type=email_type
            )
        else:
            # Send immediately
            await email_service.send_email(
                to=recipient_email,
                subject=subject,
                html=html,
                user_id=user_id,
                template_type=email_type,
                tags={"type": "auth", "action": email_type}
            )

        logger.info(f"Auth email queued/sent", extra={
            "email_type": email_type,
            "recipient": recipient_email
        })
        return True

    except Exception as e:
        logger.error(f"Failed to send auth email: {str(e)}", extra={
            "email_type": email_type,
            "recipient": recipient_email
        }, exc_info=True)
        return False


async def send_workspace_email(
    db: AsyncSession,
    email_type: Literal["invitation", "invitation_accepted", "role_changed", "member_removed", "workspace_deleted"],
    workspace_id: UUID,
    recipient_email: str,
    user_id: UUID = None,
    background_tasks: BackgroundTasks = None,
    **context
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
                logger.info(f"Email blocked by user preferences", extra={
                    "user_id": str(user_id),
                    "email_type": email_type
                })
                return False

            # Get unsubscribe token
            prefs = await prefs_service.get_or_create_preferences(user_id)
            unsubscribe_token = prefs.unsubscribe_token

        # Add unsubscribe token to context for templates
        context_with_token = {**context, "unsubscribe_token": unsubscribe_token}

        from emails.templates.workspace import (
            create_workspace_invitation_email,
            create_invitation_accepted_email,
            create_role_changed_email,
            create_member_removed_email,
            create_workspace_deleted_email
        )
        from src.utils.email_template_utils import render_template

        # Check for workspace-specific custom DB template (admin-created, not default)
        html = None
        subject = None
        try:
            from sqlalchemy import select, cast, String
            from src.api.models.workspace_models.email_template import EmailTemplate

            result = await db.execute(
                select(EmailTemplate).where(
                    EmailTemplate.workspace_id == str(workspace_id),
                    cast(EmailTemplate.template_type, String) == email_type,
                    EmailTemplate.is_active.is_(True),
                    EmailTemplate.is_default.is_(False)
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
                subject = f"Your role in {context.get('workspace_name', 'workspace')} has been updated"
            elif email_type == "member_removed":
                html = create_member_removed_email(**context_with_token)
                subject = f"You've been removed from {context.get('workspace_name', 'a workspace')}"
            elif email_type == "workspace_deleted":
                html = create_workspace_deleted_email(**context_with_token)
                subject = f"Workspace '{context.get('workspace_name', 'your workspace')}' has been deleted"
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
                email_type=email_type
            )
        else:
            await email_service.send_email(
                to=recipient_email,
                subject=subject,
                html=html,
                user_id=user_id,
                workspace_id=workspace_id,
                template_type=email_type,
                tags={"type": "workspace", "action": email_type}
            )

        logger.info(f"Workspace email queued/sent", extra={
            "email_type": email_type,
            "workspace_id": str(workspace_id),
            "recipient": recipient_email
        })
        return True

    except Exception as e:
        logger.error(f"Failed to send workspace email: {str(e)}", extra={
            "email_type": email_type,
            "workspace_id": str(workspace_id),
            "recipient": recipient_email
        }, exc_info=True)
        return False


async def _send_email_task(
    db: AsyncSession,
    recipient_email: str,
    subject: str,
    html: str,
    user_id: UUID = None,
    workspace_id: UUID = None,
    email_type: str = None
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
                tags={"background_task": True}
            )
            logger.info(f"Background email sent successfully to {recipient_email}")
    except Exception as e:
        logger.error(
            f"Background email task failed for {recipient_email}: {str(e)}",
            exc_info=True
        )
