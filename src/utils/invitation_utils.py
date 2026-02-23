"""Utility functions for invitation management (Async version)."""

from datetime import datetime, timezone
from typing import Optional
from src.api.models.enums import InvitationStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.api.models.user_models.invitations import UserInvitations
from src.utils.logger import logger
from src.utils.invitation_serializers import serialize_invitation_summary

# ------------------------------------------------------------------
# CHECK EXPIRY (NO DB → stays sync)
# ------------------------------------------------------------------
def is_invitation_expired(invitation: UserInvitations) -> bool:
    """Check if an invitation has expired."""
    if not invitation.expires_at:
        return False

    now = datetime.now(timezone.utc)

    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    return now > expires_at


# ------------------------------------------------------------------
# CLEANUP EXPIRED INVITATIONS
# ------------------------------------------------------------------
async def cleanup_expired_invitations(db: AsyncSession) -> int:
    """
    Mark all expired pending invitations as 'expired'.
    """
    try:
        now = datetime.now(timezone.utc)

        # Async SELECT
        result = await db.execute(
            select(UserInvitations).where(
                UserInvitations.status == InvitationStatus.PENDING,
                UserInvitations.expires_at < now,
            )
        )

        expired_invitations = result.scalars().all()

        count = 0
        for invitation in expired_invitations:
            invitation.status = InvitationStatus.EXPIRED
            count += 1

        if count > 0:
            await db.commit()
            logger.info(f"Marked {count} expired invitations as 'expired'")
        else:
            logger.info("No expired invitations found")

        return count

    except Exception as e:
        logger.error(f"Error cleaning up expired invitations: {str(e)}")
        await db.rollback()
        return 0


# ------------------------------------------------------------------
# GET INVITATION WITH DETAILS
# ------------------------------------------------------------------
async def get_invitation_with_details(
    db: AsyncSession, invitation_id: str
) -> Optional[dict]:
    """
    Get invitation with workspace and role details.

    Uses a single query with eager loading instead of 4 separate queries
    to avoid unnecessary round-trips to the database.
    """
    from src.api.models.workspace_models.workspace_model import WorkspaceModel
    from src.api.models.user_models.roles import Role
    from src.api.models.user_models.users import Users

    # Single query with joins
    result = await db.execute(
        select(UserInvitations, WorkspaceModel, Role, Users)
        .outerjoin(WorkspaceModel, WorkspaceModel.id == UserInvitations.workspace_id)
        .outerjoin(Role, Role.id == UserInvitations.role_id)
        .outerjoin(Users, Users.id == UserInvitations.invited_by_user_id)
        .where(UserInvitations.id == invitation_id)
    )
    row = result.first()

    if not row:
        return None

    invitation, workspace, role, invited_by = row

    return serialize_invitation_summary(
        invitation=invitation,
        workspace=workspace,
        role=role,
        invited_by=invited_by,
    )