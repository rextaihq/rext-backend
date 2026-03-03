"""Utility functions for invitation management (Async version)."""

from datetime import datetime, timezone
from typing import Optional
import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.api.models.user_models.invitations import UserInvitations
from src.utils.logger import logger
from src.api.middleware.exceptions import RextValidationException



MIN_EXPIRY_DAYS = 1
MAX_EXPIRY_DAYS = 30

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

def generate_invitation_token(nbytes: int = 32) -> str:
    """
    Generate a cryptographically secure invitation token.

    Uses Python's secrets module which provides access to the most secure
    source of randomness available on the OS. The token is URL-safe
    Base64-encoded, suitable for use in invitation URLs.

    Args:
        nbytes: Number of random bytes. Defaults to 32 (produces ~43 char token).
                Use 48 for higher-security tokens (~64 chars).

    Returns:
        URL-safe token string.

    Reference:
        https://docs.python.org/3.11/library/secrets.html#secrets.token_urlsafe
    """
    return secrets.token_urlsafe(nbytes)

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

    invited_by_result = await db.execute(
        select(Users).where(Users.id == invitation.invited_by_user_id)
    )
    invited_by = invited_by_result.scalar_one_or_none()

    return {
        "id": str(invitation.id),
        "email": invitation.email,
        "workspace_id": str(invitation.workspace_id),
        "workspace_name": workspace.name if workspace else None,
        "role_id": str(invitation.role_id),
        "role_name": role.name if role else None,
        "invited_by_user_id": str(invitation.invited_by_user_id),
        "invited_by_name": invited_by.full_name if invited_by else None,
        "status": invitation.status,
        "created_at": invitation.created_at.isoformat() if invitation.created_at else None,
        "expires_at": invitation.expires_at.isoformat() if invitation.expires_at else None,
        "is_expired": is_invitation_expired(invitation),
    }


def validate_expiry_days(expiry_days: int) -> None:
    """
    Validate that invitation expiry days is within the allowed range.

    Args:
        expiry_days: Number of days until invitation expires.

    Raises:
        RextValidationException: If expiry_days is not between
            MIN_EXPIRY_DAYS and MAX_EXPIRY_DAYS (inclusive).
    """
    if not MIN_EXPIRY_DAYS <= expiry_days <= MAX_EXPIRY_DAYS:
        raise RextValidationException(
            message=f"Expiry days must be between {MIN_EXPIRY_DAYS} and {MAX_EXPIRY_DAYS}",
            field_errors={
                "expiry_days": [
                    f"Must be between {MIN_EXPIRY_DAYS} and {MAX_EXPIRY_DAYS} days"
                ]
            }
        )


def normalize_email(email: str) -> str:
    """
    Normalize an email address for consistent comparison and storage.

    Applies lowercase and whitespace trimming. Per RFC 5321, the domain
    part is case-insensitive. While the local part is technically
    case-sensitive, all major providers treat it as case-insensitive.

    Args:
        email: Email address to normalize.

    Returns:
        Normalized email address (lowercase, trimmed).
    """
    return email.lower().strip()
