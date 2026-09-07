"""
Public Invitation Routes

These routes handle invitation validation and acceptance for workspace invitations.
They follow the existing architecture pattern used in workspace_invitations.py
and use services for business logic.

Public endpoints:
- GET /api/v1/invitations/{token}/validate - Validate invitation token
- POST /api/v1/invitations/{token}/accept - Accept invitation (requires auth)
"""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from datetime import datetime, timezone
from src.api.database.async_database import get_async_db
from src.api.models.user_models.users import Users
from src.api.models.user_models.roles import Role
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.user_models.invitations import UserInvitations, InvitationStatus
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    BusinessRuleViolationException,
    DuplicateResourceException,
)
from src.api.security.dependencies import get_current_user
from src.services.invitation_service import InvitationService
from src.services.member_service import MemberService
from src.services.user_service import UserService
from src.services.role_service import RoleService
from src.services.email_service import EmailService
from src.utils.response_utils import success, created
from src.utils.route_decorators import db_transaction_handler
from src.utils.audit_helper import create_audit_log_async
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.response.public_invitation_responses import (
    InvitationValidationResponse,
    InvitationAcceptResponse,
    InvitationDeclineResponse
)
from src.utils.invitation_utils import is_invitation_expired
from src.utils.logger import logger

router = APIRouter(prefix="/invitations", tags=["Invitations"])


@router.get("/{token}/validate", response_model=SuccessResponse[InvitationValidationResponse])
@db_transaction_handler("validate invitation", auto_commit=False)
async def validate_invitation(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Validate invitation token (public endpoint).

    Returns invitation details if valid and pending.
    This endpoint is public to allow unauthenticated users to view invitation details
    before deciding to sign up or log in.

    Args:
        token: Invitation token from email link
        request: FastAPI request object
        db: Database session

    Returns:
        Invitation details including workspace and role information

    Raises:
        ResourceNotFoundException: If invitation not found or invalid
        BusinessRuleViolationException: If invitation is expired
    """
    # Get invitation via service
    invitation_service = InvitationService(db)
    try:
        invitation = await invitation_service.get_invitation_by_token(token)
    except ResourceNotFoundException:
        raise ResourceNotFoundException(
            resource_type="Invitation",
            resource_id=token,
            message="Invitation not found. If you received multiple invitation emails, "
                    "please use the link from the most recent one."
        )

    # A revoked or declined invitation can never be used again.
    # An already-accepted invitation is still returned (status = "accepted") so
    # the client can show an "already a member" screen instead of a hard error -
    # this is the common case after login auto-accepts a pending invitation and
    # the client then re-opens the accept link.
    if invitation.status in (InvitationStatus.REVOKED, InvitationStatus.DECLINED):
        raise BusinessRuleViolationException(
            message=f"Invitation is {invitation.status} and cannot be used",
            rule_name="invitation_must_be_pending"
        )

    # Check if expired (only a still-pending invitation can transition to expired)
    if invitation.status == InvitationStatus.PENDING and is_invitation_expired(invitation):
        invitation.status = InvitationStatus.EXPIRED
        await db.flush()
        raise BusinessRuleViolationException(
            message="Invitation has expired",
            rule_name="invitation_not_expired"
        )

    if invitation.status == InvitationStatus.EXPIRED:
        raise BusinessRuleViolationException(
            message="Invitation has expired",
            rule_name="invitation_not_expired"
        )

    # Get related entities via services
    # Note: We need workspace and role details for the response
    user_service = UserService(db)
    role_service = RoleService(db)

    # Load workspace
    workspace = await db.get(WorkspaceModel, invitation.workspace_id)
    if not workspace:
        raise ResourceNotFoundException(
            resource_type="Workspace",
            resource_id=str(invitation.workspace_id)
        )
    # Load role
    role = await role_service.get_role_by_id(invitation.role_id)

    # Load inviter
    inviter = None
    if invitation.invited_by_user_id:
        try:
            inviter = await user_service.get_user_by_id(invitation.invited_by_user_id)
        except ResourceNotFoundException:
            pass  # Inviter might have been deleted

    # Eagerly load all attributes we need (avoid lazy loading issues)
    invitation_id = str(invitation.id)
    invitation_email = invitation.email
    invitation_expires_at = invitation.expires_at.isoformat()
    invitation_status = invitation.status
    workspace_id = str(workspace.id)
    workspace_name = workspace.name
    workspace_slug = workspace.slug
    role_id = str(role.id)
    role_name = role.display_name or role.name
    inviter_display_name = inviter.display_name if inviter else None
    inviter_username = (inviter.display_name or inviter.email) if inviter else "Unknown"
    inviter_first_name = inviter.first_name if inviter and hasattr(inviter, 'first_name') else ""
    inviter_last_name = inviter.last_name if inviter and hasattr(inviter, 'last_name') else ""
    inviter_id = str(inviter.id) if inviter else None

    # Build data for response
    invitation_data = {
        "id": invitation_id,
        "email": invitation_email,
        "expires_at": invitation_expires_at,
        "status": invitation_status,
        "workspace_id": workspace_id,
        "workspace_name": workspace_name,
        "workspace_slug": workspace_slug,
        "role_id": role_id,
        "role_name": role_name,
        "inviter_display_name": inviter_display_name,
        "inviter_username": inviter_username,
        "inviter_first_name": inviter_first_name,
        "inviter_last_name": inviter_last_name,
        "inviter_id": inviter_id,
    }

    return success(
        data={"invitation": invitation_data},
        request=request,
        message="Invitation is valid",
    )


@router.post("/{token}/accept", response_model=SuccessResponse[InvitationAcceptResponse], status_code=status.HTTP_201_CREATED)
@db_transaction_handler("accept invitation", auto_commit=True)
async def accept_invitation(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    Accept workspace invitation (requires authentication).

    Creates workspace membership for the authenticated user and updates invitation status.
    Follows existing architecture pattern from workspace_invitations.py

    Args:
        token: Invitation token from email link
        request: FastAPI request object
        db: Database session
        user: Authenticated user from JWT token

    Returns:
        Workspace membership details and welcome message

    Raises:
        ResourceNotFoundException: If invitation not found
        BusinessRuleViolationException: If invitation is expired or already used
    """
    user_id = UUID(str(user.get("identity")))

    # Get invitation via service
    invitation_service = InvitationService(db)
    try:
        invitation = await invitation_service.get_invitation_by_token(token)
    except ResourceNotFoundException:
        raise ResourceNotFoundException(
            resource_type="Invitation",
            resource_id=token,
            message="Invitation not found or already used"
        )

    # A revoked, declined or expired invitation can never be accepted.
    # PENDING is the normal case; ACCEPTED is allowed through so this endpoint is
    # idempotent - login already auto-accepts pending invitations, and the client
    # then re-calls this endpoint. The membership handling below returns the
    # existing membership instead of erroring.
    if invitation.status in (InvitationStatus.REVOKED, InvitationStatus.DECLINED):
        raise BusinessRuleViolationException(
            message=f"Invitation is {invitation.status} and cannot be accepted",
            rule_name="invitation_must_be_pending"
        )

    # Check if expired (only a still-pending invitation can transition to expired)
    if invitation.status == InvitationStatus.PENDING and is_invitation_expired(invitation):
        invitation.status = InvitationStatus.EXPIRED
        await db.flush()
        raise BusinessRuleViolationException(
            message="Invitation has expired",
            rule_name="invitation_not_expired"
        )

    if invitation.status == InvitationStatus.EXPIRED:
        raise BusinessRuleViolationException(
            message="Invitation has expired",
            rule_name="invitation_not_expired"
        )

    # Get current user details
    user_service = UserService(db)
    current_user_obj = await user_service.get_user_by_id(user_id)

    # Verify authenticated user's email matches the invitation target email
    # This prevents unauthorized users from accepting invitations meant for others
    if current_user_obj.email.lower().strip() != invitation.email.lower().strip():
        raise BusinessRuleViolationException(
            message=f"This invitation is for {invitation.email}, but you are logged in as {current_user_obj.email}. "
                    f"Please sign in with the correct account to accept this invitation.",
            rule_name="email_must_match_invitation"
        )

    # Load workspace and role for response
    workspace = await db.get(WorkspaceModel, invitation.workspace_id)
    if not workspace:
        raise ResourceNotFoundException(
            resource_type="Workspace",
            resource_id=str(invitation.workspace_id)
        )

    role_service = RoleService(db)
    role = await role_service.get_role_by_id(invitation.role_id)

    from sqlalchemy import select, and_

    # Is the caller already a member of this workspace?
    existing_membership = (
        await db.execute(
            select(WorkspaceMembers).where(
                and_(
                    WorkspaceMembers.user_id == user_id,
                    WorkspaceMembers.workspace_id == invitation.workspace_id,
                )
            )
        )
    ).scalar_one_or_none()

    # An already-accepted invitation is only reusable by the person who is
    # actually a member (idempotent retry, or login already auto-accepted it).
    # If it is accepted and the caller is not a member, the link is spent.
    if invitation.status == InvitationStatus.ACCEPTED and existing_membership is None:
        raise BusinessRuleViolationException(
            message="Invitation has already been used",
            rule_name="invitation_must_be_pending"
        )

    member_service = MemberService(db)
    already_member = existing_membership is not None
    if already_member:
        membership = existing_membership
        logger.info(
            "User already member of workspace, accept invitation is a no-op",
            extra={
                "user_id": str(user_id),
                "workspace_id": str(invitation.workspace_id),
                "invitation_id": str(invitation.id)
            }
        )
    else:
        try:
            membership = await member_service.add_member(
                workspace_id=invitation.workspace_id,
                user_id=user_id,
                role_id=invitation.role_id,
                invitation_id=invitation.id,
                status="active"
            )
        except DuplicateResourceException:
            already_member = True
            membership = (
                await db.execute(
                    select(WorkspaceMembers).where(
                        and_(
                            WorkspaceMembers.user_id == user_id,
                            WorkspaceMembers.workspace_id == invitation.workspace_id
                        )
                    )
                )
            ).scalar_one()

    # Update invitation status
    invitation.status = InvitationStatus.ACCEPTED
    invitation.accepted_at = datetime.now(timezone.utc)
    await db.flush()

    # Eagerly load all attributes for response (avoid lazy loading issues)
    membership_id = str(membership.id)
    workspace_id_str = str(workspace.id)
    workspace_name_str = workspace.name
    workspace_slug_str = workspace.slug
    role_name_str = role.display_name or role.name
    user_display_name = current_user_obj.display_name or current_user_obj.email
    user_email = current_user_obj.email

    # Create audit log
    await create_audit_log_async(
        db=db,
        user_id=str(user_id),
        action="invitation.accept",
        resource_type="invitation",
        resource_id=str(invitation.id),
        new_values={
            "invited_email": invitation.email,
            "accepted_by": user_display_name,
            "workspace": workspace_name_str,
            "role": role_name_str,
        },
        request=request,
        workspace_id=invitation.workspace_id,
        username=user_display_name,
        user_email=user_email,
    )

    logger.info(
        "Invitation accepted",
        extra={
            "invitation_id": str(invitation.id),
            "user_id": str(user_id),
            "workspace_id": workspace_id_str,
            "membership_id": membership_id,
        }
    )

    # Send notification email to inviter
    if invitation.invited_by_user_id:
        try:
            inviter = await user_service.get_user_by_id(invitation.invited_by_user_id)

            # Import email template
            from emails.templates.workspace.invitation_accepted import create_invitation_accepted_email

            # Prepare member details
            new_member_name = current_user_obj.display_name or current_user_obj.email

            # Generate email HTML
            email_html = create_invitation_accepted_email(
                workspace_name=workspace_name_str,
                new_member_name=new_member_name,
                new_member_email=user_email,
                role_name=role_name_str,
                workspace_id=workspace_id_str,
                workspace_slug=workspace_slug_str,
                frontend_url=get_settings().FRONTEND_URL
            )

            # Send email to inviter
            email_service = EmailService(db)
            await email_service.send_email(
                to=inviter.email,
                subject=f"✅ {new_member_name} joined {workspace_name_str}",
                html=email_html,
                workspace_id=invitation.workspace_id,
                user_id=invitation.invited_by_user_id,
                template_type="invitation_accepted",
                tags={
                    "type": "workspace",
                    "action": "invitation_accepted",
                    "invitation_id": str(invitation.id),
                    "workspace_id": workspace_id_str,
                },
                auto_commit=False  # Already in transaction
            )

            logger.info(
                "Invitation accepted notification sent to inviter",
                extra={
                    "invitation_id": str(invitation.id),
                    "inviter_id": str(invitation.invited_by_user_id),
                    "inviter_email": inviter.email,
                }
            )
        except Exception as e:
            # Don't fail the acceptance if email fails
            logger.error(
                "Failed to send invitation accepted notification",
                exc_info=True,
                extra={
                    "invitation_id": str(invitation.id),
                    "inviter_id": str(invitation.invited_by_user_id),
                }
            )

    response_message = (
        f"You're already a member of {workspace_name_str}"
        if already_member
        else f"Welcome to {workspace_name_str}!"
    )

    api_message = (
        "Invitation accepted - already a member"
        if already_member
        else "Invitation accepted successfully"
    )

    return created(
        data={
            "membership_id": membership_id,
            "workspace_id": workspace_id_str,
            "workspace_name": workspace_name_str,
            "workspace_slug": workspace_slug_str,
            "role": role_name_str,
            "already_member": already_member,
            "message": response_message,
        },
        request=request,
        message=api_message,
    )


from src.api.schema.invitation_schema import DeclineInvitationByTokenRequest


@router.post("/{token}/decline", response_model=SuccessResponse[InvitationDeclineResponse])
@db_transaction_handler("decline invitation by token", auto_commit=True)
async def decline_invitation_by_token(
    token: str,
    request: Request,
    data: DeclineInvitationByTokenRequest,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Decline a workspace invitation by token (public endpoint).

    Allows invited users to decline without authentication.
    The token from the email link serves as proof of invitation.

    Args:
        token: Invitation token from email link
        request: FastAPI request object
        data: Optional decline reason
        db: Database session

    Returns:
        Success message with declined invitation details
    """
    invitation_service = InvitationService(db)
    invitation = await invitation_service.decline_invitation_by_token(
        token=token,
        reason=data.reason if data else None,
    )

    # Send decline notification to inviter
    if invitation.invited_by_user_id:
        try:
            workspace = await db.get(WorkspaceModel, invitation.workspace_id)
            user_service = UserService(db)
            inviter = await user_service.get_user_by_id(invitation.invited_by_user_id)

            from emails.templates.workspace.invitation_declined import create_invitation_declined_email
            from src.api.config import get_settings

            settings = get_settings()
            email_html = create_invitation_declined_email(
                workspace_name=workspace.name if workspace else "Unknown",
                declined_by_email=invitation.email,
                decline_reason=data.reason if data else None,
                workspace_id=str(invitation.workspace_id),
                workspace_slug=workspace.slug if workspace else None,
                frontend_url=settings.FRONTEND_URL
            )

            email_service = EmailService(db)
            await email_service.send_email(
                to=inviter.email,
                subject=f"Invitation to {workspace.name if workspace else 'workspace'} was declined",
                html=email_html,
                workspace_id=invitation.workspace_id,
                user_id=invitation.invited_by_user_id,
                template_type="invitation_declined",
                tags={
                    "type": "workspace",
                    "action": "invitation_declined",
                    "invitation_id": str(invitation.id),
                },
                auto_commit=False
            )
        except Exception:
            logger.error(
                "Failed to send decline notification email",
                exc_info=True,
                extra={"invitation_id": str(invitation.id)}
            )

    await create_audit_log_async(
        db=db,
        action="invitation.declined_by_token",
        resource_type="invitation",
        resource_id=str(invitation.id),
        details={
            "workspace_id": str(invitation.workspace_id),
            "invitation_email": invitation.email,
            "decline_reason": data.reason if data else None,
        },
        request=request,
    )

    return success(
        data={
            "invitation_id": str(invitation.id),
            "status": "declined",
        },
        request=request,
        message="Invitation declined successfully",
    )