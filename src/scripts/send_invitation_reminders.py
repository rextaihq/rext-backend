"""
Send Invitation Reminders

Background job to send reminder emails for pending invitations that are about to expire.
Runs daily and sends reminders 2 days before expiry.

Usage:
    python -m src.scripts.send_invitation_reminders

Or with cron:
    0 9 * * * cd /path/to/rext-backend && /path/to/python -m src.scripts.send_invitation_reminders
"""
import asyncio
from datetime import datetime, timedelta
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db_context
from src.api.models.user_models.invitations import UserInvitations
from src.api.models.user_models.users import Users
from src.api.models.user_models.roles import Role
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.config import get_settings
from src.services.email_service import EmailService
from src.utils.logger import logger
from emails.templates.workspace.invitation_reminder import create_invitation_reminder_email


async def send_invitation_reminders(db: AsyncSession):
    """
    Send reminder emails for invitations expiring within 2 days.

    Args:
        db: Database session

    Returns:
        Number of reminders sent
    """
    settings = get_settings()
    now = datetime.utcnow()
    two_days_from_now = now + timedelta(days=2)

    # Query invitations that:
    # 1. Are pending
    # 2. Expire within the next 2 days (but not yet expired)
    # 3. Haven't had a reminder sent yet
    query = select(UserInvitations).where(
        and_(
            UserInvitations.status == "pending",
            UserInvitations.expires_at > now,
            UserInvitations.expires_at <= two_days_from_now,
            UserInvitations.reminder_sent == False,  # noqa: E712
        )
    )

    result = await db.execute(query)
    invitations_to_remind = result.scalars().all()

    if not invitations_to_remind:
        logger.info("No invitations need reminders at this time")
        return 0

    logger.info(f"Found {len(invitations_to_remind)} invitations to remind")

    email_service = EmailService(db)
    reminders_sent = 0

    for invitation in invitations_to_remind:
        try:
            # Load related entities
            workspace = await db.get(WorkspaceModel, invitation.workspace_id)
            if not workspace:
                logger.warning(
                    f"Workspace not found for invitation {invitation.id}, skipping"
                )
                continue

            role = await db.get(Role, invitation.role_id)
            if not role:
                logger.warning(
                    f"Role not found for invitation {invitation.id}, skipping"
                )
                continue

            inviter = None
            if invitation.invited_by_user_id:
                inviter = await db.get(Users, invitation.invited_by_user_id)

            # Calculate days until expiry
            time_until_expiry = invitation.expires_at - now
            days_until_expiry = max(1, int(time_until_expiry.total_seconds() / 86400))

            # Eagerly load attributes before async operations
            workspace_id = workspace.id
            workspace_name = workspace.name
            workspace_description = getattr(workspace, "description", None)
            role_display_name = role.display_name or role.name
            invitation_id = invitation.id
            invitation_email = invitation.email
            invitation_token = invitation.invitation_token
            inviter_display_name = (
                inviter.display_name if inviter else "A teammate"
            )

            # Generate reminder email
            email_html = create_invitation_reminder_email(
                workspace_name=workspace_name,
                inviter_name=inviter_display_name,
                invitation_token=invitation_token,
                role_name=role_display_name,
                days_until_expiry=days_until_expiry,
                workspace_description=workspace_description,
                frontend_url=settings.FRONTEND_URL,
            )

            # Send email
            await email_service.send_email(
                to=invitation_email,
                subject=f"⏰ Reminder: Your invitation to {workspace_name} expires soon",
                html=email_html,
                workspace_id=workspace_id,
                template_type="invitation_reminder",
                tags={
                    "type": "workspace",
                    "action": "invitation_reminder",
                    "invitation_id": str(invitation_id),
                    "workspace_id": str(workspace_id),
                    "days_until_expiry": str(days_until_expiry),
                },
                auto_commit=False,  # We'll commit after marking reminder as sent
            )

            # Mark reminder as sent
            invitation.reminder_sent = True
            await db.flush()

            reminders_sent += 1

            logger.info(
                f"Reminder sent for invitation {invitation_id} to {invitation_email}",
                extra={
                    "invitation_id": str(invitation_id),
                    "email": invitation_email,
                    "workspace_id": str(workspace_id),
                    "days_until_expiry": days_until_expiry,
                },
            )

        except Exception as e:
            logger.error(
                f"Failed to send reminder for invitation {invitation.id}: {str(e)}",
                exc_info=True,
                extra={
                    "invitation_id": str(invitation.id),
                    "email": invitation.email,
                },
            )
            # Continue to next invitation even if one fails

    # Commit all changes
    await db.commit()

    logger.info(
        f"Invitation reminder job complete: {reminders_sent}/{len(invitations_to_remind)} reminders sent"
    )

    return reminders_sent


async def main():
    """Main entry point for the script."""
    logger.info("Starting invitation reminder job...")

    try:
        async with get_async_db_context() as db:
            reminders_sent = await send_invitation_reminders(db)
            logger.info(f"Successfully sent {reminders_sent} invitation reminders")
            return reminders_sent
    except Exception as e:
        logger.error(f"Invitation reminder job failed: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())
