from fastapi import APIRouter, Depends, Request, HTTPException, status, Query
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import Optional
import uuid

from src.utils.logger import logger
from src.utils.response_utils import success, error, created
from src.utils.invitation_utils import is_invitation_expired, get_invitation_with_details
from src.utils.audit_helper import create_audit_log
from src.api.database.database import get_db
from src.api.security.auth import get_current_user
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    WrextExternalServiceException,
    WrextValidationException,
    WrextAuthenticationException
)
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.schema.invitation_schema import (
    AcceptInvitationRequest,
    RevokeInvitationRequest,
    InvitationResponse,
    InvitationListResponse
)
from src.api.models.user_models.users import Users
from src.api.models.user_models.invitations import UserInvitations
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.user_models.roles import Role

router = APIRouter(
    prefix="/workspace/invitations",
    tags=["workspace", "invitations"],
    responses={404: {"description": "Not found"}},
)

@router.get("/status")
def get_invitation_status(request: Request):
    """Qa
    Endpoint to check the invitation service status.
    """
    return success(
        message="Invitation service is up and running.",
        data={"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
    )

@router.post("/")
def create_invitation(request: Request, db: Session = Depends(get_db), current_user: Users = Depends(get_current_user)):
    """Create a new invitation for a user to join a workspace.

    This is a placeholder function. The actual implementation would involve
    validating the request data, creating an invitation record in the database,
    and sending an invitation email to the user.
    """
    pass


# -------------------------
# Invitation Management Endpoints
# -------------------------

@router.post("/accept")
def accept_invitation(
    request: Request,
    invitation_data: AcceptInvitationRequest,
    db: Session = Depends(get_db),
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
        user = db.query(Users).filter(Users.id == user_id).first()
        if not user:
            return error(
                message="User not found",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        # Find invitation by token
        invitation = db.query(UserInvitations).filter(
            UserInvitations.invitation_token == invitation_data.token
        ).first()

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
            db.commit()
            return error(
                message="Invitation has expired",
                code=ErrorCode.INVALID_INPUT,
                status_code=400,
                severity=ErrorSeverity.LOW,
                request=request
            )

        # Check if user already has membership in this workspace
        existing_membership = db.query(WorkspaceMembers).filter(
            WorkspaceMembers.user_id == user_id,
            WorkspaceMembers.workspace_id == invitation.workspace_id
        ).first()

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
        workspace = db.query(WorkspaceModel).filter(
            WorkspaceModel.id == invitation.workspace_id
        ).first()

        # Commit all changes
        db.commit()
        db.refresh(membership)

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
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to accept invitation"
        )


@router.post("/{invitation_id}/revoke")
def revoke_invitation(
    invitation_id: str,
    request: Request,
    revoke_data: RevokeInvitationRequest,
    db: Session = Depends(get_db),
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
        invitation = db.query(UserInvitations).filter(
            UserInvitations.id == invitation_id
        ).first()

        if not invitation:
            return error(
                message="Invitation not found",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        # Check permission: must be invitation creator or workspace admin
        user = db.query(Users).filter(Users.id == user_id).first()

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

        db.commit()
        db.refresh(invitation)

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
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke invitation"
        )


@router.get("/sent")
def list_sent_invitations(
    request: Request,
    status_filter: Optional[str] = Query(None, description="Filter by status (pending, accepted, revoked, expired)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List invitations sent by the current user.

    - **status_filter**: Optional filter by invitation status
    """
    try:
        user_id = current_user.get("identity")
        logger.info(f"User {user_id} listing sent invitations")

        # Build query
        query = db.query(UserInvitations).filter(
            UserInvitations.invited_by_user_id == user_id
        )

        # Apply status filter
        if status_filter:
            query = query.filter(UserInvitations.status == status_filter)

        # Get invitations
        invitations = query.order_by(UserInvitations.created_at.desc()).all()

        # Format response with details
        invitations_data = []
        for inv in invitations:
            details = get_invitation_with_details(db, str(inv.id))
            if details:
                invitations_data.append(details)

        return success(
            data={
                "invitations": invitations_data,
                "total_count": len(invitations_data),
                "status_filter": status_filter
            },
            request=request,
            message=f"Retrieved {len(invitations_data)} sent invitation(s)"
        )

    except Exception as e:
        logger.error(f"Error listing sent invitations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve sent invitations"
        )


@router.get("/received")
def list_received_invitations(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List pending invitations for the current user's email.

    Only shows pending, non-expired invitations.
    """
    try:
        user_id = current_user.get("identity")

        # Get user email
        user = db.query(Users).filter(Users.id == user_id).first()
        if not user:
            return error(
                message="User not found",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        logger.info(f"User {user_id} listing received invitations for email {user.email}")

        # Get pending invitations for user's email
        invitations = db.query(UserInvitations).filter(
            UserInvitations.email == user.email,
            UserInvitations.status == "pending"
        ).order_by(UserInvitations.created_at.desc()).all()

        # Filter out expired and add details
        invitations_data = []
        for inv in invitations:
            if not is_invitation_expired(inv):
                details = get_invitation_with_details(db, str(inv.id))
                if details:
                    invitations_data.append(details)
            else:
                # Mark as expired
                inv.status = "expired"

        # Commit any expiry status updates
        db.commit()

        return success(
            data={
                "invitations": invitations_data,
                "total_count": len(invitations_data)
            },
            request=request,
            message=f"Retrieved {len(invitations_data)} pending invitation(s)"
        )

    except Exception as e:
        logger.error(f"Error listing received invitations: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve received invitations"
        )