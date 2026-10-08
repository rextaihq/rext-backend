"""
The email a platform admin invitation sends.

An invitation that nobody can open is not an invitation: when its email can't be
sent, the caller's transaction is rolled back with it (nothing is stored, or a resend
changes nothing) and the admin is told, instead of reading "sent".
"""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from emails.templates.auth.admin_invitation import ROLE_LABELS, render_admin_invitation_email
from src.api.config import get_settings
from src.api.middleware.exceptions import RextExternalServiceException
from src.api.models.admin_models.admin_invitations import PlatformAdminInvitations
from src.services.email_service import EmailService
from src.utils.logger import logger

# The dashboard's page that validates the token and offers Accept and Decline.
ACCEPT_PATH = "/accept-admin-invitation"

NOT_SENT = (
    "The invitation email couldn't be sent, so nothing was saved. Try again in a few minutes."
)


def person_name(user) -> str | None:
    """A person as an email or a screen names them: what they chose to be called."""
    if user is None:
        return None
    return user.display_name or user.full_name or None


def accept_url(token: str) -> str:
    """The link the email carries: the dashboard's accept page with the token."""
    return f"{get_settings().FRONTEND_URL.rstrip('/')}{ACCEPT_PATH}?token={token}"


async def send_admin_invitation_email(
    db: AsyncSession, invitation: PlatformAdminInvitations
) -> None:
    """
    Send the invitation to the address it names.

    ``invitation`` is read whole, its inviter included. Raises
    RextExternalServiceException when the email can't be sent, so that the caller's
    transaction (the new invitation, or a resend's new link) is rolled back.
    """
    days_left = max(
        1, round((invitation.expires_at - datetime.now(timezone.utc)).total_seconds() / 86400)
    )
    html = render_admin_invitation_email(
        inviter_name=person_name(invitation.invited_by),
        admin_role=invitation.admin_role,
        invitation_url=accept_url(invitation.invitation_token),
        expiry_days=days_left,
        message=invitation.message,
    )
    role = ROLE_LABELS.get(invitation.admin_role, invitation.admin_role)
    try:
        sent = await EmailService(db).send_email(
            to=invitation.email,
            subject=f"You're invited to the Rext AI admin area ({role})",
            html=html,
            template_type="admin_invitation",
            tags={"type": "admin", "action": "admin_invitation"},
            auto_commit=False,
        )
        failed = sent.status == "failed"
    except Exception as error:  # noqa: BLE001 - whatever stopped it, the admin is told
        logger.error(
            "Admin invitation email not sent",
            extra={"invitation_id": str(invitation.id), "error": type(error).__name__},
        )
        raise RextExternalServiceException(message=NOT_SENT, service_name="email") from error
    if failed:
        logger.error(
            "Admin invitation email not sent",
            extra={"invitation_id": str(invitation.id), "error": "provider"},
        )
        raise RextExternalServiceException(message=NOT_SENT, service_name="email")
