"""Shared serialization functions for workspace invitations.

Centralizes invitation-to-response conversion to avoid inconsistent
serialization patterns across route files.
"""
from typing import Optional, Dict, Any

from src.api.models.user_models.invitations import UserInvitations
from src.api.models.user_models.users import Users
from src.api.models.user_models.roles import Role
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.utils.invitation_utils import is_invitation_expired


def serialize_invitation_summary(
    invitation: UserInvitations,
    role: Optional[Role] = None,
    invited_by: Optional[Users] = None,
) -> Dict[str, Any]:
    """Serialize invitation to flat summary dict (for list endpoints).

    Args:
        invitation: The invitation model instance.
        role: The role model instance (optional, for display name).
        invited_by: The user who created the invitation (optional).

    Returns:
        Flat dictionary matching InvitationSummaryResponse schema.
    """
    return {
        "id": str(invitation.id),
        "workspace_id": str(invitation.workspace_id),
        "email": invitation.email,
        "role_id": str(invitation.role_id) if invitation.role_id else None,
        "role_name": (role.display_name or role.name) if role else None,
        "status": invitation.status,
        "expires_at": invitation.expires_at.isoformat() if invitation.expires_at else None,
        "created_at": invitation.created_at.isoformat() if invitation.created_at else None,
        "invited_by_user_id": str(invitation.invited_by_user_id) if invitation.invited_by_user_id else None,
        "invited_by_name": invited_by.display_name if invited_by else None,
        "is_expired": is_invitation_expired(invitation),
    }


def serialize_invitation_detail(
    invitation: UserInvitations,
    workspace: Optional[WorkspaceModel] = None,
    role: Optional[Role] = None,
    invited_by: Optional[Users] = None,
    include_token: bool = False,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """Serialize invitation to detailed nested dict (for single-item endpoints).

    Args:
        invitation: The invitation model instance.
        workspace: The workspace model instance (optional).
        role: The role model instance (optional).
        invited_by: The user who created the invitation (optional).
        include_token: Whether to include the invitation token in the response.
        token: The token string (used when include_token=True).

    Returns:
        Nested dictionary matching InvitationDetailResponse schema.
    """
    result: Dict[str, Any] = {
        "id": str(invitation.id),
        "email": invitation.email,
        "status": invitation.status,
        "expires_at": invitation.expires_at.isoformat() if invitation.expires_at else None,
        "created_at": invitation.created_at.isoformat() if invitation.created_at else None,
        "is_expired": is_invitation_expired(invitation),
        "workspace": None,
        "role": None,
        "invited_by": None,
    }

    if workspace:
        result["workspace"] = {
            "id": str(workspace.id),
            "name": workspace.name,
            "slug": getattr(workspace, "slug", None),
        }

    if role:
        result["role"] = {
            "id": str(role.id),
            "name": role.display_name or role.name,
        }

    if invited_by:
        result["invited_by"] = {
            "id": str(invited_by.id),
            "name": invited_by.display_name or invited_by.full_name,
            "username": getattr(invited_by, "username", None),
        }

    if include_token and token:
        result["token"] = token

    return result
