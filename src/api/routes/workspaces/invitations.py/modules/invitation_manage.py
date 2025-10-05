from fastapi import APIRouter, Depends, Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from src.utils.logger import logger
from src.utils.response_utils import success, error
from src.utils.invitation_utils import is_invitation_expired
from src.utils.audit_helper import create_audit_log
from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
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
    try:
        user_id = current_user.get("identity")
        logger.info(f"User {user_id} attempting to accept invitation with token")

        # Get user details
        result = await db.execute(select(Users).where(Users.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            return error(
                message="User not found",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        # Find invitation by token
        result = await db.execute(
            select(UserInvitations).where(UserInvitations.invitation_token == invitation_data.token)
        )
        invitation = result.scalar_one_or_none()

        if not invitation:
            return error(
                message="Invalid invitation token",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        # Validate invitation email matches user email
        if invitation.email.lower() != user.email.lower():
            logger.warning(f"Invitation email mismatch: {invitation.email} vs {user.email}")
            return error(
                message="This invitation is for a different email address",
                code=ErrorCode.PERMISSION_DENIED,
                status_code=403,
                severity=ErrorSeverity.HIGH,
                request=request
            )

        # Check invitation status
        if invitation.status != "pending":
            return error(
                message=f"Invitation has already been {invitation.status}",
                code=ErrorCode.INVALID_INPUT,
                status_code=400,
                severity=ErrorSeverity.LOW,
                request=request
            )

        # Check if expired
        if is_invitation_expired(invitation):
            invitation.status = "expired"
            await db.commit()
            return error(
                message="Invitation has expired",
                code=ErrorCode.INVALID_INPUT,
                status_code=400,
                severity=ErrorSeverity.LOW,
                request=request
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
            return error(
                message="You are already a member of this workspace",
                code=ErrorCode.DUPLICATE_RESOURCE,
                status_code=409,
                severity=ErrorSeverity.LOW,
                request=request
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

        # Commit all changes
        await db.commit()
        await db.refresh(membership)

        logger.info(f"User {user_id} accepted invitation to workspace {invitation.workspace_id}")

        return success(
            data={
                "invitation_id": str(invitation.id),
                "workspace_id": str(invitation.workspace_id),
                "workspace_name": workspace.name if workspace else None,
                "role_id": str(invitation.role_id),
                "membership_id": str(membership.id),
                "joined_at": membership.joined_at.isoformat()
            },
            request=request,
            message=f"Successfully joined workspace"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error accepting invitation: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to accept invitation"
        )


@router.post("/{invitation_id}/revoke")
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
    try:
        user_id = current_user.get("identity")
        logger.info(f"User {user_id} attempting to revoke invitation {invitation_id}")

        # Get invitation
        result = await db.execute(
            select(UserInvitations).where(UserInvitations.id == invitation_id)
        )
        invitation = result.scalar_one_or_none()

        if not invitation:
            return error(
                message="Invitation not found",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.MEDIUM,
                request=request
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
            return error(
                message="Insufficient permissions to revoke this invitation",
                code=ErrorCode.PERMISSION_DENIED,
                status_code=403,
                severity=ErrorSeverity.HIGH,
                request=request
            )

        # Check if already revoked or accepted
        if invitation.status in ["revoked", "accepted"]:
            return error(
                message=f"Invitation has already been {invitation.status}",
                code=ErrorCode.INVALID_INPUT,
                status_code=400,
                severity=ErrorSeverity.LOW,
                request=request
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

        await db.commit()
        await db.refresh(invitation)

        logger.info(f"Invitation {invitation_id} revoked by user {user_id}")

        return success(
            data={
                "invitation_id": str(invitation.id),
                "status": invitation.status,
                "revoked_by": user.username if user else "unknown",
                "reason": revoke_data.reason
            },
            request=request,
            message="Invitation revoked successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking invitation {invitation_id}: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke invitation"
        )
