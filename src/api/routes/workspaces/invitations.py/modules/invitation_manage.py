from fastapi import APIRouter, Depends, Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from src.utils.logger import logger
from src.utils.response_utils import success, error
from src.utils.invitation_utils import is_invitation_expired
from src.utils.audit_helper import create_audit_log
from src.utils.route_decorators import db_transaction_handler
from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    WrextAuthenticationException,
    WrextValidationException,
    WrextAPIException,
    DuplicateResourceException
)
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.schema.invitation_schema import (
    AcceptInvitationRequest,
    RevokeInvitationRequest,
)
from src.api.models.user_models.users import Users
from src.api.models.user_models.invitations import UserInvitations
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel


router = APIRouter()


@router.post("/accept")
@db_transaction_handler("accept invitation", auto_commit=True)
async def accept_invitation(
    request: Request,
    invitation_data: AcceptInvitationRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Accept an invitation to join a workspace.

    - **token**: Invitation token from email

    The user must be authenticated. The invitation email must match the user's email.
    """
    user_id = current_user.get("identity")
    logger.info(f"User {user_id} attempting to accept invitation with token")

    # Get user details
    result = await db.execute(select(Users).where(Users.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise ResourceNotFoundException(
            message="User not found",
            resource_type="user",
            resource_id=str(user_id)
        )

    # Find invitation by token
    result = await db.execute(
        select(UserInvitations).where(UserInvitations.invitation_token == invitation_data.token)
    )
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise ResourceNotFoundException(
            message="Invalid invitation token",
            resource_type="invitation",
            resource_id=invitation_data.token
        )

    # Validate invitation email matches user email
    if invitation.email.lower() != user.email.lower():
        logger.warning(f"Invitation email mismatch: {invitation.email} vs {user.email}")
        raise WrextAuthenticationException(
            message="This invitation is for a different email address"
        )

    # Check invitation status
    if invitation.status != "pending":
        raise WrextValidationException(
            message=f"Invitation has already been {invitation.status}",
            field_name="status"
        )

    # Check if expired
    if is_invitation_expired(invitation):
        invitation.status = "expired"
        await db.flush()
        raise WrextValidationException(
            message="Invitation has expired",
            field_name="expires_at"
        )

    # Check if user already has membership in this workspace
    result = await db.execute(
        select(WorkspaceMembers).where(
            WorkspaceMembers.user_id == user_id,
            WorkspaceMembers.workspace_id == invitation.workspace_id
        )
    )
    existing_membership = result.scalar_one_or_none()

    if existing_membership:
        raise DuplicateResourceException(
            message="You are already a member of this workspace",
            resource_type="workspace_member",
            conflicting_field="user_id",
            conflicting_value=str(user_id)
        )

    # Create workspace membership
    membership = WorkspaceMembers(
        user_id=user_id,
        workspace_id=invitation.workspace_id,
        role_id=invitation.role_id,
        status="active",
        joined_at=datetime.utcnow(),
        invitation_id=invitation.id
    )
    db.add(membership)

    # Update invitation status
    invitation.status = "accepted"

    # Get workspace details for response
    result = await db.execute(
        select(WorkspaceModel).where(WorkspaceModel.id == invitation.workspace_id)
    )
    workspace = result.scalar_one_or_none()

    # Flush all changes
    await db.flush()
    await db.refresh(membership)

    logger.info(f"User {user_id} accepted invitation to workspace {invitation.workspace_id}")

    return {
        "data": {
            "invitation_id": str(invitation.id),
            "workspace_id": str(invitation.workspace_id),
            "workspace_name": workspace.name if workspace else None,
            "role_id": str(invitation.role_id),
            "membership_id": str(membership.id),
            "joined_at": membership.joined_at.isoformat()
        },
        "message": "Successfully joined workspace"
    }


@router.post("/{invitation_id}/revoke")
@db_transaction_handler("revoke invitation", auto_commit=True)
async def revoke_invitation(
    invitation_id: str,
    request: Request,
    revoke_data: RevokeInvitationRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Revoke an invitation (admin or invitation creator only).

    - **invitation_id**: ID of the invitation to revoke
    - **reason**: Optional reason for revocation
    """
    user_id = current_user.get("identity")
    logger.info(f"User {user_id} attempting to revoke invitation {invitation_id}")

    # Get invitation
    result = await db.execute(
        select(UserInvitations).where(UserInvitations.id == invitation_id)
    )
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise ResourceNotFoundException(
            message="Invitation not found",
            resource_type="invitation",
            resource_id=invitation_id
        )

    # Check permission: must be invitation creator or workspace admin
    result = await db.execute(select(Users).where(Users.id == user_id))
    user = result.scalar_one_or_none()

    # Check if user created the invitation
    is_creator = str(invitation.invited_by_user_id) == str(user_id)

    # Check if user is workspace admin (simplified check)
    # TODO: Implement proper workspace admin check
    is_admin = False  # Placeholder

    if not is_creator and not is_admin:
        raise WrextAuthenticationException(
            message="Insufficient permissions to revoke this invitation"
        )

    # Check if already revoked or accepted
    if invitation.status in ["revoked", "accepted"]:
        raise WrextValidationException(
            message=f"Invitation has already been {invitation.status}",
            field_name="status"
        )

    # Store old status
    old_status = invitation.status

    # Revoke invitation
    invitation.status = "revoked"

    # Create audit log
    create_audit_log(
        db=db,
        user_id=user_id,
        action="invitation.revoke",
        resource_type="invitation",
        resource_id=str(invitation_id),
        old_values={"status": old_status},
        new_values={"status": "revoked", "reason": revoke_data.reason},
        request=request,
        workspace_id=invitation.workspace_id,
        username=user.username if user else None,
        user_email=user.email if user else None
    )

    await db.flush()
    await db.refresh(invitation)

    logger.info(f"Invitation {invitation_id} revoked by user {user_id}")

    return {
        "data": {
            "invitation_id": str(invitation.id),
            "status": invitation.status,
            "revoked_by": user.username if user else "unknown",
            "reason": revoke_data.reason
        },
        "message": "Invitation revoked successfully"
    }
