"""
Invitation reminders.

Once a day, a pending workspace invitation that expires within two days gets one
reminder email. The server's scheduler runs it (src/tasks/scheduled_tasks.py), where
the emails' logo is already published; ``python -m src.scripts.send_invitation_reminders``
runs the same job by hand.

One invitation at a time: its row is locked while its email goes out, and the mark
that it was reminded is committed with it. So a run that stops part-way doesn't send
the same reminders again the next day, and two runs at the same moment don't both
send one.
"""

from datetime import datetime, timedelta, timezone
from html import escape
from typing import List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from emails.templates.workspace.invitation_reminder import create_invitation_reminder_email
from src.api.config import get_settings
from src.api.database.async_database import get_async_db_context
from src.api.models.enums import InvitationStatus
from src.api.models.user_models.invitations import UserInvitations
from src.api.models.user_models.roles import Role
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.services.email_preferences_service import EmailPreferencesService
from src.services.email_service import EmailService
from src.utils.logger import logger

# An invitation is reminded once, when it has this long left or less.
REMIND_WITHIN = timedelta(days=2)


async def _next_invitation(
    db: AsyncSession, now: datetime, passed_over: List[UUID]
) -> Optional[UserInvitations]:
    """The next pending invitation due its reminder, with its row locked: a run started
    at the same moment passes it over."""
    due = (
        select(UserInvitations)
        .where(
            UserInvitations.status == InvitationStatus.PENDING.value,
            UserInvitations.expires_at > now,
            UserInvitations.expires_at <= now + REMIND_WITHIN,
            UserInvitations.reminder_sent.is_(False),
            UserInvitations.id.notin_(passed_over),
        )
        .order_by(UserInvitations.expires_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    return (await db.execute(due)).scalar_one_or_none()


async def _remind(
    db: AsyncSession,
    email_service: EmailService,
    invitation: UserInvitations,
    now: datetime,
    frontend_url: str,
) -> bool:
    """Send one invitation's reminder and mark it. False when nothing was sent: the
    workspace or the role is gone, the invited person has turned these emails off, or
    the email could not be sent (it is tried again on the next run, while the
    invitation still stands)."""
    workspace = await db.get(WorkspaceModel, invitation.workspace_id)
    role = await db.get(Role, invitation.role_id)
    if workspace is None or workspace.deleted_at is not None or role is None:
        logger.warning(
            "Invitation reminder skipped: its workspace or role is gone",
            extra={"invitation_id": str(invitation.id)},
        )
        return False

    # Someone who has an account has a say in the emails they get; someone who has
    # none yet has no preferences to ask.
    invited = (
        await db.execute(
            select(Users.id).where(func.lower(Users.email) == invitation.email.lower()).limit(1)
        )
    ).scalar_one_or_none()
    if invited is not None and not await EmailPreferencesService(db).check_can_send(
        invited, "invitation_reminder"
    ):
        logger.info(
            "Invitation reminder skipped: the invited person turned these emails off",
            extra={"invitation_id": str(invitation.id)},
        )
        return False

    inviter = None
    if invitation.invited_by_user_id:
        inviter = await db.get(Users, invitation.invited_by_user_id)
    inviter_name = (inviter.display_name if inviter else None) or "A teammate"
    description = getattr(workspace, "description", None)
    # To the nearest day: 40 hours left is "in 2 days", 30 hours is "tomorrow".
    days_left = max(1, round((invitation.expires_at - now).total_seconds() / 86400))

    # The names and the description are what people typed: they go into the email's
    # HTML as text.
    html = create_invitation_reminder_email(
        workspace_name=escape(workspace.name),
        inviter_name=escape(inviter_name),
        invitation_token=invitation.invitation_token,
        role_name=escape(role.display_name or role.name),
        days_until_expiry=days_left,
        workspace_description=escape(description) if description else None,
        frontend_url=frontend_url,
    )
    sent = await email_service.send_email(
        to=invitation.email,
        subject=f"⏰ Reminder: Your invitation to {workspace.name} expires soon",
        html=html,
        workspace_id=workspace.id,
        template_type="invitation_reminder",
        tags={
            "type": "workspace",
            "action": "invitation_reminder",
            "invitation_id": str(invitation.id),
            "workspace_id": str(workspace.id),
            "days_until_expiry": str(days_left),
        },
        auto_commit=False,
    )
    # A send that fails is recorded in the email log and doesn't raise.
    if sent.status == "failed":
        logger.warning(
            "Invitation reminder not sent; it is tried again on the next run",
            extra={"invitation_id": str(invitation.id)},
        )
        return False

    invitation.reminder_sent = True
    return True


async def send_invitation_reminders(db: AsyncSession) -> int:
    """
    Send the reminder of every pending invitation that expires within two days and
    hasn't had one. Each is committed as it is sent.

    Returns:
        Number of reminders sent
    """
    frontend_url = get_settings().FRONTEND_URL
    email_service = EmailService(db)
    reminded = 0
    passed_over: List[UUID] = []

    while True:
        # Read for each one: an invitation that ran out while the others were being
        # sent gets no reminder for a link that no longer works.
        now = datetime.now(timezone.utc)
        invitation = await _next_invitation(db, now, passed_over)
        if invitation is None:
            break
        invitation_id = invitation.id
        try:
            if await _remind(db, email_service, invitation, now, frontend_url):
                reminded += 1
            else:
                passed_over.append(invitation_id)
            await db.commit()
        except Exception as error:  # noqa: BLE001 - the next invitation still gets its reminder
            await db.rollback()
            passed_over.append(invitation_id)
            logger.error(
                "Invitation reminder failed",
                exc_info=True,
                extra={"invitation_id": str(invitation_id), "error": type(error).__name__},
            )

    logger.info(
        "Invitation reminders done",
        extra={"reminded": reminded, "not_reminded": len(passed_over)},
    )
    return reminded


async def run_invitation_reminders_task() -> int:
    """Entry point for the scheduler and for the script."""
    async with get_async_db_context() as db:
        return await send_invitation_reminders(db)
