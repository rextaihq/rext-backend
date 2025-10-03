from fastapi import APIRouter, Depends, Request, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid
import os

from src.utils.logger import logger
from src.utils.response_utils import success, error, created
from src.utils.invitation_utils import is_invitation_expired, get_invitation_with_details
from src.utils.audit_helper import create_audit_log
from src.utils.email_template_utils import render_workspace_email
from src.api.database.database import get_db
from src.api.security.dependencies import get_current_user
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    WrextExternalServiceException,
    WrextValidationException,
    WrextAuthenticationException
)
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.schema.invitation_schema import (
    CreateInvitationRequest,
    BulkCreateInvitationRequest,
    AcceptInvitationRequest,
    RevokeInvitationRequest,
    InvitationResponse,
    InvitationListResponse,
    BulkInvitationResult,
    BulkInvitationResponse
)
from src.api.models.user_models.users import Users
from src.api.models.user_models.invitations import UserInvitations
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.user_models.roles import Role
from src.api.tasks.send_mail import send_email

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

@router.post("/", status_code=status.HTTP_201_CREATED)
def create_invitation(
    request: Request,
    invitation_data: CreateInvitationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new invitation for a user to join a workspace.

    - **email**: Email address of the user to invite
    - **workspace_id**: ID of the workspace
    - **role_id**: Role to assign to the invited user
    - **expiry_days**: Days until invitation expires (1-30, default 7)

    Requires: workspace admin/owner OR user.invite permission
    """
    try:
        user_id = current_user.get("identity")
        logger.info(f"User {user_id} creating invitation for {invitation_data.email}")

        # Verify workspace exists
        workspace = db.query(WorkspaceModel).filter(
            WorkspaceModel.id == invitation_data.workspace_id
        ).first()

        if not workspace:
            raise ResourceNotFoundException(
                message="Workspace not found",
                resource_type="workspace",
                resource_id=invitation_data.workspace_id
            )

        # Check if user has permission to invite to this workspace
        # Must be workspace member with appropriate role
        membership = db.query(WorkspaceMembers).filter(
            WorkspaceMembers.workspace_id == invitation_data.workspace_id,
            WorkspaceMembers.user_id == user_id,
            WorkspaceMembers.status == "active"
        ).first()

        if not membership:
            raise WrextAuthenticationException(
                message="You are not a member of this workspace",
                context={"workspace_id": invitation_data.workspace_id}
            )

        # TODO: Add permission check for user.invite or workspace admin role

        # Verify role exists
        role = db.query(Role).filter(Role.id == invitation_data.role_id).first()
        if not role:
            raise ResourceNotFoundException(
                message="Role not found",
                resource_type="role",
                resource_id=invitation_data.role_id
            )

        # Check if invitation already exists for this email + workspace
        existing_invitation = db.query(UserInvitations).filter(
            UserInvitations.email == invitation_data.email.lower(),
            UserInvitations.workspace_id == invitation_data.workspace_id,
            UserInvitations.status == "pending"
        ).first()

        if existing_invitation:
            # Check if expired - if so, revoke it and create new one
            if is_invitation_expired(existing_invitation):
                existing_invitation.status = "expired"
                db.commit()
            else:
                raise DuplicateResourceException(
                    message="An active invitation already exists for this email and workspace",
                    resource_type="invitation",
                    conflicting_field="email",
                    conflicting_value=invitation_data.email
                )

        # Check if user is already a member
        # First find if user exists with this email
        existing_user = db.query(Users).filter(Users.email == invitation_data.email.lower()).first()
        if existing_user:
            existing_membership = db.query(WorkspaceMembers).filter(
                WorkspaceMembers.user_id == existing_user.id,
                WorkspaceMembers.workspace_id == invitation_data.workspace_id
            ).first()

            if existing_membership:
                raise DuplicateResourceException(
                    message="User is already a member of this workspace",
                    resource_type="workspace_member",
                    conflicting_field="user_id",
                    conflicting_value=str(existing_user.id)
                )

        # Generate invitation token
        invitation_token = str(uuid.uuid4())

        # Calculate expiry
        expires_at = datetime.utcnow() + timedelta(days=invitation_data.expiry_days)

        # Create invitation
        invitation = UserInvitations(
            email=invitation_data.email.lower(),
            workspace_id=invitation_data.workspace_id,
            role_id=invitation_data.role_id,
            invited_by_user_id=user_id,
            invitation_token=invitation_token,
            status="pending",
            expires_at=expires_at
        )

        db.add(invitation)
        db.commit()
        db.refresh(invitation)

        # Get inviter details for email
        inviter = db.query(Users).filter(Users.id == user_id).first()

        # Send invitation email in background using custom or default template
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        invitation_link = f"{frontend_url}/invitations/accept?token={invitation_token}"

        # Render email template
        email_content = render_workspace_email(
            db=db,
            workspace_id=invitation_data.workspace_id,
            template_type="workspace_invitation",
            variables={
                "workspace_name": workspace.name,
                "inviter_name": inviter.display_name or inviter.username,
                "recipient_email": invitation_data.email,
                "role_name": role.display_name or role.name,
                "invitation_url": invitation_link,
                "expiry_days": str(invitation_data.expiry_days)
            }
        )

        background_tasks.add_task(
            send_email,
            to=invitation_data.email,
            subject=email_content["subject"],
            body=email_content["body"]
        )

        logger.info(f"Invitation created: {invitation.id} for {invitation_data.email} to workspace {workspace.name}")

        # Create audit log
        create_audit_log(
            db=db,
            user_id=user_id,
            action="invitation.create",
            resource_type="invitation",
            resource_id=str(invitation.id),
            new_values={
                "email": invitation_data.email,
                "workspace_id": str(invitation_data.workspace_id),
                "role_id": str(invitation_data.role_id)
            },
            request=request,
            workspace_id=invitation_data.workspace_id,
            username=inviter.username if inviter else None,
            user_email=inviter.email if inviter else None
        )

        return created(
            data={
                "invitation": {
                    "id": str(invitation.id),
                    "email": invitation.email,
                    "workspace_id": str(invitation.workspace_id),
                    "workspace_name": workspace.name,
                    "role_id": str(invitation.role_id),
                    "role_name": role.name,
                    "status": invitation.status,
                    "expires_at": invitation.expires_at.isoformat(),
                    "created_at": invitation.created_at.isoformat()
                }
            },
            request=request,
            message=f"Invitation sent to {invitation_data.email}"
        )

    except (DuplicateResourceException, ResourceNotFoundException, WrextAuthenticationException):
        raise
    except Exception as e:
        logger.error(f"Error creating invitation: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create invitation"
        )


@router.post("/bulk", status_code=status.HTTP_201_CREATED)
def create_bulk_invitations(
    request: Request,
    invitation_data: BulkCreateInvitationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Create multiple invitations at once for users to join a workspace.

    - **emails**: List of email addresses (max 50)
    - **workspace_id**: ID of the workspace
    - **role_id**: Role to assign to all invited users
    - **expiry_days**: Days until invitations expire (1-30, default 7)

    Returns a detailed report of successful and failed invitations.
    Requires: workspace admin/owner OR user.invite permission
    """
    try:
        user_id = current_user.get("identity")
        logger.info(f"User {user_id} creating bulk invitations for {len(invitation_data.emails)} emails")

        # Verify workspace exists
        workspace = db.query(WorkspaceModel).filter(
            WorkspaceModel.id == invitation_data.workspace_id
        ).first()

        if not workspace:
            raise ResourceNotFoundException(
                message="Workspace not found",
                resource_type="workspace",
                resource_id=invitation_data.workspace_id
            )

        # Check if user has permission to invite to this workspace
        membership = db.query(WorkspaceMembers).filter(
            WorkspaceMembers.workspace_id == invitation_data.workspace_id,
            WorkspaceMembers.user_id == user_id,
            WorkspaceMembers.status == "active"
        ).first()

        if not membership:
            raise WrextAuthenticationException(
                message="You are not a member of this workspace",
                context={"workspace_id": invitation_data.workspace_id}
            )

        # Verify role exists
        role = db.query(Role).filter(Role.id == invitation_data.role_id).first()
        if not role:
            raise ResourceNotFoundException(
                message="Role not found",
                resource_type="role",
                resource_id=invitation_data.role_id
            )

        # Get inviter details for email
        inviter = db.query(Users).filter(Users.id == user_id).first()
        inviter_name = inviter.display_name if inviter else "A workspace member"

        # Process each email
        results = []
        successful = 0
        failed = 0

        for email in invitation_data.emails:
            try:
                email_lower = email.lower()

                # Check if invitation already exists for this email + workspace
                existing_invitation = db.query(UserInvitations).filter(
                    UserInvitations.email == email_lower,
                    UserInvitations.workspace_id == invitation_data.workspace_id,
                    UserInvitations.status == "pending"
                ).first()

                if existing_invitation:
                    # Check if expired - if so, revoke it and create new one
                    if is_invitation_expired(existing_invitation):
                        existing_invitation.status = "expired"
                        db.commit()
                    else:
                        results.append(BulkInvitationResult(
                            email=email,
                            success=False,
                            error_message="An active invitation already exists for this email"
                        ))
                        failed += 1
                        continue

                # Check if user is already a member
                existing_user = db.query(Users).filter(Users.email == email_lower).first()
                if existing_user:
                    existing_membership = db.query(WorkspaceMembers).filter(
                        WorkspaceMembers.user_id == existing_user.id,
                        WorkspaceMembers.workspace_id == invitation_data.workspace_id
                    ).first()

                    if existing_membership:
                        results.append(BulkInvitationResult(
                            email=email,
                            success=False,
                            error_message="User is already a member of this workspace"
                        ))
                        failed += 1
                        continue

                # Generate invitation token
                invitation_token = str(uuid.uuid4())

                # Calculate expiry
                expires_at = datetime.utcnow() + timedelta(days=invitation_data.expiry_days)

                # Create invitation
                invitation = UserInvitations(
                    email=email_lower,
                    workspace_id=invitation_data.workspace_id,
                    role_id=invitation_data.role_id,
                    invited_by_user_id=user_id,
                    invitation_token=invitation_token,
                    status="pending",
                    expires_at=expires_at
                )

                db.add(invitation)
                db.flush()  # Get the ID without committing

                # Send invitation email asynchronously
                frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
                invitation_url = f"{frontend_url}/accept-invitation?token={invitation_token}"

                background_tasks.add_task(
                    send_email,
                    to_email=email,
                    subject=f"You're invited to join {workspace.name}",
                    body=f"""
                    Hi there,

                    {inviter_name} has invited you to join the "{workspace.name}" workspace.

                    Role: {role.display_name}

                    Click the link below to accept the invitation:
                    {invitation_url}

                    This invitation will expire in {invitation_data.expiry_days} days.

                    If you don't want to join this workspace, you can ignore this email.

                    Best regards,
                    The Wrext Team
                    """
                )

                # Audit log for each invitation
                create_audit_log(
                    db=db,
                    user_id=user_id,
                    action="invitation.created",
                    resource_type="invitation",
                    resource_id=str(invitation.id),
                    details={
                        "email": email,
                        "workspace_id": str(invitation_data.workspace_id),
                        "role_id": str(invitation_data.role_id),
                        "expires_at": expires_at.isoformat()
                    }
                )

                results.append(BulkInvitationResult(
                    email=email,
                    success=True,
                    invitation_id=str(invitation.id)
                ))
                successful += 1

            except Exception as e:
                logger.error(f"Error creating invitation for {email}: {str(e)}")
                results.append(BulkInvitationResult(
                    email=email,
                    success=False,
                    error_message=str(e)
                ))
                failed += 1

        # Commit all successful invitations
        db.commit()

        logger.info(f"Bulk invitation completed: {successful} successful, {failed} failed")

        return created(
            data={
                "total_requested": len(invitation_data.emails),
                "successful": successful,
                "failed": failed,
                "results": [r.dict() for r in results]
            },
            request=request,
            message=f"Bulk invitation completed: {successful} sent, {failed} failed"
        )

    except (ResourceNotFoundException, WrextAuthenticationException):
        raise
    except Exception as e:
        logger.error(f"Error in bulk invitation: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process bulk invitations"
        )


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