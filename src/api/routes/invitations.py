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
from datetime import datetime

from src.api.database.async_database import get_async_db
from src.api.models.user_models.invitations import UserInvitations
from src.api.models.user_models.users import Users
from src.api.models.user_models.roles import Role
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    BusinessRuleViolationException,
)
from src.api.security.dependencies import get_current_user
from src.services.invitation_service import InvitationService
from src.services.member_service import MemberService
from src.services.user_service import UserService
from src.services.role_service import RoleService
from src.utils.response_utils import success, created
from src.utils.route_decorators import db_transaction_handler
from src.utils.audit_helper import create_audit_log_async
from src.utils.invitation_utils import is_invitation_expired
from src.utils.logger import logger

router = APIRouter(prefix="/invitations", tags=["Invitations"])


@router.get("/{token}/validate")
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
            message="Invitation not found or already used"
        )

    # Check if invitation is pending
    if invitation.status != "pending":
        raise BusinessRuleViolationException(
            message=f"Invitation is {invitation.status} and cannot be used",
            rule_name="invitation_must_be_pending"
        )

    # Check if expired
    if is_invitation_expired(invitation):
        # Auto-expire it
        invitation.status = "expired"
        await db.flush()
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
    role_id = str(role.id)
    role_name = role.display_name or role.name
    inviter_name = inviter.display_name or inviter.username if inviter else "Unknown"

    return success(
        data={
            "invitation": {
                "id": invitation_id,
                "email": invitation_email,
                "workspace_id": workspace_id,
                "workspace_name": workspace_name,
                "role_id": role_id,
                "role_name": role_name,
                "invited_by": inviter_name,
                "expires_at": invitation_expires_at,
                "status": invitation_status,
            }
        },
        request=request,
        message="Invitation is valid",
    )


@router.post("/{token}/accept")
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

    # Check if invitation is pending
    if invitation.status != "pending":
        raise BusinessRuleViolationException(
            message=f"Invitation is {invitation.status} and cannot be accepted",
            rule_name="invitation_must_be_pending"
        )

    # Check if expired
    if is_invitation_expired(invitation):
        # Auto-expire it
        invitation.status = "expired"
        await db.flush()
        raise BusinessRuleViolationException(
            message="Invitation has expired",
            rule_name="invitation_not_expired"
        )

    # Get current user details
    user_service = UserService(db)
    current_user_obj = await user_service.get_user_by_id(user_id)

    # Optional: Verify email matches invitation
    # Note: Commented out to allow any authenticated user to accept
    # This is useful if user signed up with different email or OAuth
    # if current_user_obj.email != invitation.email:
    #     raise BusinessRuleViolationException(
    #         message=f"This invitation is for {invitation.email}, but you are logged in as {current_user_obj.email}",
    #         rule_name="email_must_match_invitation"
    #     )

    # Load workspace and role for response
    workspace = await db.get(WorkspaceModel, invitation.workspace_id)
    if not workspace:
        raise ResourceNotFoundException(
            resource_type="Workspace",
            resource_id=str(invitation.workspace_id)
        )

    role_service = RoleService(db)
    role = await role_service.get_role_by_id(invitation.role_id)

    # Add member to workspace via service
    member_service = MemberService(db)
    try:
        membership = await member_service.add_member(
            workspace_id=invitation.workspace_id,
            user_id=user_id,
            invitation_id=invitation.id,
            status="active"
        )
    except Exception as e:
        # MemberService will raise DuplicateResourceException if already a member
        raise

    # Update invitation status
    invitation.status = "accepted"
    invitation.accepted_at = datetime.utcnow()
    invitation.accepted_by_user_id = user_id
    await db.flush()

    # Eagerly load all attributes for response (avoid lazy loading issues)
    membership_id = str(membership.id)
    workspace_id_str = str(workspace.id)
    workspace_name_str = workspace.name
    workspace_slug_str = workspace.slug
    role_name_str = role.display_name or role.name
    user_username = current_user_obj.username
    user_email = current_user_obj.email

    # Create audit log
    await create_audit_log_async(
        db=db,
        user_id=str(user_id),
        action="invitation.accept",
        resource_type="invitation",
        resource_id=str(invitation.id),
        new_values={
            "workspace_id": workspace_id_str,
            "role_id": str(role.id),
            "membership_id": membership_id,
        },
        request=request,
        workspace_id=invitation.workspace_id,
        username=user_username,
        user_email=user_email,
    )

    logger.info(
        f"Invitation accepted: {user_email} joined {workspace_name_str}",
        extra={
            "invitation_id": str(invitation.id),
            "user_id": str(user_id),
            "workspace_id": workspace_id_str,
            "membership_id": membership_id,
        }
    )

    return created(
        data={
            "membership_id": membership_id,
            "workspace_id": workspace_id_str,
            "workspace_name": workspace_name_str,
            "workspace_slug": workspace_slug_str,
            "role": role_name_str,
            "message": f"Welcome to {workspace_name_str}!",
        },
        request=request,
        message="Invitation accepted successfully",
    )
