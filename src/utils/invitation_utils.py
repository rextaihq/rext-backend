"""Utility functions for invitation management."""
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from src.api.models.user_models.invitations import UserInvitations
from src.utils.logger import logger


def is_invitation_expired(invitation: UserInvitations) -> bool:
    """
    Check if an invitation has expired.

    Args:
        invitation: UserInvitations model instance

    Returns:
        bool: True if expired, False otherwise
    """
    if not invitation.expires_at:
        return False

    now = datetime.now(timezone.utc)

    # Handle both timezone-aware and naive datetimes
    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    return now > expires_at


def cleanup_expired_invitations(db: Session) -> int:
    """
    Mark all expired pending invitations as 'expired'.

    Args:
        db: Database session

    Returns:
        int: Number of invitations marked as expired
    """
    try:
        now = datetime.now(timezone.utc)

        # Find all pending invitations that have expired
        expired_invitations = db.query(UserInvitations).filter(
            UserInvitations.status == "pending",
            UserInvitations.expires_at < now
        ).all()

        count = 0
        for invitation in expired_invitations:
            invitation.status = "expired"
            count += 1

        db.commit()

        if count > 0:
            logger.info(f"Marked {count} expired invitations as 'expired'")

        return count

    except Exception as e:
        logger.error(f"Error cleaning up expired invitations: {str(e)}")
        db.rollback()
        return 0


def get_invitation_with_details(db: Session, invitation_id: str) -> Optional[dict]:
    """
    Get invitation with workspace and role details.

    Args:
        db: Database session
        invitation_id: Invitation ID

    Returns:
        dict: Invitation details with related entities, or None if not found
    """
    from src.api.models.workspace_models.workspace_model import WorkspaceModel
    from src.api.models.user_models.roles import Role
    from src.api.models.user_models.users import Users

    invitation = db.query(UserInvitations).filter(
        UserInvitations.id == invitation_id
    ).first()

    if not invitation:
        return None

    # Get related entities
    workspace = db.query(WorkspaceModel).filter(
        WorkspaceModel.id == invitation.workspace_id
    ).first()

    role = db.query(Role).filter(
        Role.id == invitation.role_id
    ).first()

    invited_by = db.query(Users).filter(
        Users.id == invitation.invited_by_user_id
    ).first()

    return {
        "id": str(invitation.id),
        "email": invitation.email,
        "workspace_id": str(invitation.workspace_id),
        "workspace_name": workspace.name if workspace else None,
        "role_id": str(invitation.role_id),
        "role_name": role.name if role else None,
        "invited_by_user_id": str(invitation.invited_by_user_id),
        "invited_by_name": invited_by.username if invited_by else None,
        "status": invitation.status,
        "created_at": invitation.created_at.isoformat() if invitation.created_at else None,
        "expires_at": invitation.expires_at.isoformat() if invitation.expires_at else None,
        "is_expired": is_invitation_expired(invitation)
    }
