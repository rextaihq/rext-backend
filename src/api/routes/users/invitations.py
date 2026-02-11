"""
User Invitations Routes

These routes handle user-facing invitation operations like viewing pending
invitations and declining invitations.

Public endpoints:
- GET /api/v1/user/invitations/pending - Get pending invitations for current user
- POST /api/v1/user/invitations/{id}/decline - Decline an invitation
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from uuid import UUID
from datetime import datetime, timezone

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.models.user_models.invitations import UserInvitations
from src.api.config import get_settings
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.user_models.roles import Role
from src.api.models.user_models.users import Users
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    BusinessRuleViolationException
)
from src.services.invitation_service import InvitationService
from src.services.user_service import UserService
from src.services.email_service import EmailService
from src.utils.logger import logger
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.audit_helper import create_audit_log_async
from src.utils.invitation_utils import is_invitation_expired
from src.utils.logger import logger
from src.api.schema.user_schema import DeclineInvitationRequest  # Added import

router = APIRouter(prefix="/invitations", tags=["User Invitations"])


@router.get("/pending")
@require_permissions("member.read", workspace_scoped=False)
@db_transaction_handler("get pending invitations", auto_commit=False)
async def get_pending_invitations(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get all pending invitations for the current user.

    Returns invitations where:
    - Email matches current user's email
    - Status is "pending"
    - Not expired

    This endpoint is used by:
    - Pending invitations dashboard widget
    - Invitation notification badge
    - Dashboard invitation prompts

    Response structure:
    {
        "invitations": [
            {
                "id": "invitation-uuid",
                "workspace": {
                    "id": "workspace-uuid",
                    "name": "Workspace Name",
                    "slug": "workspace-slug"
                },
                "role": {
                    "id": "role-uuid",
                    "name": "editor",
                    "display_name": "Editor"
                },
                "invited_by": {
                    "id": "user-uuid",
                    "name": "John Doe",
                    "email": "john@example.com"
                },
                "token": "invitation-token",
                "expires_at": "ISO datetime",
                "created_at": "ISO datetime"
            }
        ],
        "count": 1
    }

    Args:
        request: FastAPI request object
        db: Database session
        current_user: Current authenticated user from JWT

    Returns:
        List of pending invitations with workspace and role details

    Raises:
        AuthenticationException: If user not authenticated
    """
    user_id = UUID(current_user.get("identity"))

    # Get current user's email
    user_result = await db.execute(
        select(Users).where(Users.id == user_id)
    )
    user = user_result.scalar_one_or_none()

    if not user:
        raise ResourceNotFoundException(
            resource_type="User",
            resource_id=str(user_id)
        )

    user_email = user.email.lower()

    # Query pending invitations for this email with eager loading
    query = (
        select(UserInvitations)
        .options(
            selectinload(UserInvitations.workspace),
            selectinload(UserInvitations.role),
            selectinload(UserInvitations.invited_by),
        )
        .where(
            and_(
                UserInvitations.email == user_email,
                UserInvitations.status == "pending"
            )
        )
        .order_by(UserInvitations.created_at.desc())
    )

    result = await db.execute(query)
    invitations = result.scalars().all()

    # Build response with workspace, role, and inviter details
    invitation_list = []

    for invitation in invitations:
        # Skip expired invitations (and auto-update status)
        if is_invitation_expired(invitation):
            invitation.status = "expired"
            await db.flush()
            continue

        # Workspace is already loaded - check for soft delete
        workspace = invitation.workspace
        if not workspace or workspace.deleted_at is not None:
            continue

        role = invitation.role
        inviter = invitation.invited_by

        # Build invitation data
        invitation_data = {
            "id": str(invitation.id),
            "workspace": {
                "id": str(workspace.id),
                "name": workspace.name,  # WorkspaceModel uses 'name'
                "slug": workspace.slug
            },
            "role": {
                "id": str(role.id),
                "name": role.name,
                "display_name": role.display_name
            } if role else None,
            "invited_by": {
                "id": str(inviter.id),
                "name": inviter.full_name or inviter.display_name or inviter.email,
                
                "email": inviter.email
            } if inviter else None,
            "token": invitation.invitation_token,
            "expires_at": invitation.expires_at.isoformat() if invitation.expires_at else None,
            "created_at": invitation.created_at.isoformat() if invitation.created_at else None
        }

        invitation_list.append(invitation_data)

    logger.info(
        f"Retrieved {len(invitation_list)} pending invitations for user",
        extra={
            "user_id": str(user_id),
            "user_email": user_email,
            "invitation_count": len(invitation_list)
        }
    )

    return {
        "invitations": invitation_list,
        "count": len(invitation_list)
    }


@router.post("/{invitation_id}/decline")
@require_permissions("member.read", workspace_scoped=False)
@db_transaction_handler("decline invitation", auto_commit=True)
async def decline_invitation(
    invitation_id: UUID,
    decline_data: DeclineInvitationRequest,  # CHANGED: Added Pydantic schema parameter
    request: Request,  # CHANGED: Moved to third position
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Decline a workspace invitation.

    Allows users to explicitly decline invitations they don't want to accept.
    This is better UX than ignoring invitations.

    Request Body (optional):
    {
        "reason": "Not interested" | "Wrong email" | "Other"
    }

    Args:
        invitation_id: UUID of the invitation to decline
        decline_data: Optional decline reason
        request: FastAPI request object
        db: Database session
        current_user: Current authenticated user from JWT

    Returns:
        Success message with declined invitation ID

    Raises:
        ResourceNotFoundException: If invitation not found
        BusinessRuleViolationException: If invitation doesn't belong to user
                                       or already processed
    """
    user_id = UUID(current_user.get("identity"))

    # Get current user's email
    user_result = await db.execute(
        select(Users).where(Users.id == user_id)
    )
    user = user_result.scalar_one_or_none()

    if not user:
        raise ResourceNotFoundException(
            resource_type="User",
            resource_id=str(user_id)
        )

    user_email = user.email.lower()

    # Get invitation
    invitation_service = InvitationService(db)
    try:
        invitation = await invitation_service.get_invitation_by_id(invitation_id)
    except ResourceNotFoundException:
        raise ResourceNotFoundException(
            resource_type="Invitation",
            resource_id=str(invitation_id),
            message="Invitation not found"
        )

    # Verify invitation belongs to current user's email
    if invitation.email.lower() != user_email:
        raise BusinessRuleViolationException(
            message="This invitation is not for your email address",
            rule_name="invitation_email_must_match_user"
        )

    # Check if invitation can be declined
    if invitation.status != "pending":
        raise BusinessRuleViolationException(
            message=f"Invitation is {invitation.status} and cannot be declined",
            rule_name="invitation_must_be_pending_to_decline"
        )

    # CHANGED: Access decline reason from Pydantic model
    decline_reason = decline_data.reason

    # Update invitation status
    invitation.status = "declined"

    # Get workspace details for notification
    workspace_result = await db.execute(
        select(WorkspaceModel).where(WorkspaceModel.id == invitation.workspace_id)
    )
    workspace = workspace_result.scalar_one_or_none()

    # Create audit log
    await create_audit_log_async(
        db=db,
        action="invitation.declined",
        resource_type="invitation",
        resource_id=invitation.id,
        user_id=user_id,
        details={
            "workspace_id": str(invitation.workspace_id),
            "invitation_email": invitation.email,
            "decline_reason": decline_reason,
            "declined_at": datetime.now(timezone.utc).isoformat()
        }
    )

    logger.info(
        f"User declined invitation",
        extra={
            "user_id": str(user_id),
            "invitation_id": str(invitation_id),
            "workspace_id": str(invitation.workspace_id),
            "decline_reason": decline_reason
        }
    )

    # Send notification email to inviter
    if invitation.invited_by_user_id and workspace:
        try:
            user_service = UserService(db)
            inviter = await user_service.get_user_by_id(invitation.invited_by_user_id)

            # Import email template
            from emails.templates.workspace.invitation_declined import create_invitation_declined_email

            # Generate email HTML
            email_html = create_invitation_declined_email(
                workspace_name=workspace.name,
                declined_by_email=user_email,
                decline_reason=decline_reason,
                workspace_id=str(workspace.id),
                frontend_url=get_settings().FRONTEND_URL
            )

            # Send email to inviter
            email_service = EmailService(db)
            await email_service.send_email(
                to=inviter.email,
                subject=f"Invitation to {workspace.name} was declined",
                html=email_html,
                workspace_id=invitation.workspace_id,
                user_id=invitation.invited_by_user_id,
                template_type="invitation_declined",
                tags={
                    "type": "workspace",
                    "action": "invitation_declined",
                    "invitation_id": str(invitation.id),
                    "workspace_id": str(workspace.id),
                },
                auto_commit=False  # Already in transaction
            )

            logger.info(
                f"Sent decline notification to inviter",
                extra={
                    "inviter_email": inviter.email,
                    "declined_by_email": user_email,
                    "workspace_id": str(workspace.id)
                }
            )

        except Exception as e:
            # Don't fail the decline if email fails
            logger.error(
                f"Failed to send decline notification email: {str(e)}",
                extra={
                    "invitation_id": str(invitation_id),
                    "error": str(e)
                }
            )

    return success(
        data={
            "invitation_id": str(invitation_id),
            "status": "declined",
            "declined_at": datetime.now(timezone.utc).isoformat()
        },
        request=request,
        message="Invitation declined successfully"
    )
