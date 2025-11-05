from fastapi import APIRouter, Depends, Request, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from uuid import UUID
import os

from src.utils.logger import logger
from src.utils.response_utils import success, error
from src.utils.invitation_utils import is_invitation_expired
from src.utils.audit_helper import create_audit_log_async
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.config import get_settings
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
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.services.invitation_service import InvitationService
from src.services.user_service import UserService
from src.services.member_service import MemberService
from src.services.workspace_service import WorkspaceService
from src.services.role_service import RoleService


router = APIRouter()


# Get settings instance
settings = get_settings()

async def notify_workspace_admins_of_acceptance(
    workspace_id: str,
    workspace_name: str,
    new_member_name: str,
    new_member_email: str,
    role_name: str
):
    """
    Notify workspace admins when a new member accepts an invitation.
    """
    from src.api.database.async_database import get_async_db_context
    from src.services.email_helpers import send_workspace_email

    try:
        async with get_async_db_context() as async_db:
            # Get all workspace admins/owners using MemberService
            member_service = MemberService(async_db)
            admin_members = await member_service.get_admin_members_with_users(
                workspace_id=UUID(workspace_id)
            )

            frontend_url = settings.FRONTEND_URL

            # Send notification to each admin
            for member, admin_user in admin_members:
                await send_workspace_email(
                    db=async_db,
                    email_type="invitation_accepted",
                    workspace_id=UUID(workspace_id),
                    recipient_email=admin_user.email,
                    user_id=admin_user.id,
                    workspace_name=workspace_name,
                    new_member_name=new_member_name,
                    new_member_email=new_member_email,
                    role_name=role_name,
                    workspace_id_str=workspace_id,
                    frontend_url=frontend_url
                )

            logger.info(f"Sent invitation accepted notifications to {len(admin_members)} admins")
    except Exception as e:
        logger.error(f"Failed to send invitation accepted notifications: {str(e)}", exc_info=True)


@router.post("/accept")
@require_permissions("member.read")
@db_transaction_handler("accept invitation", auto_commit=True)
async def accept_invitation(
    request: Request,
    invitation_data: AcceptInvitationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Accept an invitation to join a workspace - Thin controller using InvitationService
    """
    user_id = current_user.get("identity")
    logger.info(f"User {user_id} attempting to accept invitation with token")

    # Get user details using UserService
    user_service = UserService(db)
    user = await user_service.get_user_by_id(UUID(user_id))

    # Use InvitationService to get invitation by token
    service = InvitationService(db)
    invitation = await service.get_invitation_by_token(invitation_data.token)

    # Validate invitation email matches user email (route-level validation)
    if invitation.email.lower() != user.email.lower():
        logger.warning(f"Invitation email mismatch: {invitation.email} vs {user.email}")
        raise WrextAuthenticationException(
            message="This invitation is for a different email address"
        )

    # Use service to accept invitation (handles all business logic)
    result = await service.accept_invitation(
        invitation_id=invitation.id,
        user_id=UUID(user_id)
    )

    # Get workspace and role details using services
    workspace_service = WorkspaceService(db)
    workspace = await workspace_service.get_workspace_by_id(invitation.workspace_id)

    role_service = RoleService(db)
    role = await role_service.get_role_by_id(invitation.role_id)

    # Send invitation accepted notification to workspace admins
    if workspace:
        background_tasks.add_task(
            notify_workspace_admins_of_acceptance,
            workspace_id=str(workspace.id),
            workspace_name=workspace.name,
            new_member_name=user.first_name or user.username,
            new_member_email=user.email,
            role_name=role.display_name if role else "Member"
        )

    logger.info(f"User {user_id} accepted invitation to workspace {invitation.workspace_id}")

    return {
        "data": {
            "invitation_id": result["invitation_id"],
            "workspace_id": result["workspace_id"],
            "workspace_name": workspace.name if workspace else None,
            "role_id": str(invitation.role_id),
            "membership_id": result["membership_id"],
            "joined_at": datetime.utcnow().isoformat()
        },
        "message": "Successfully joined workspace"
    }


@router.post("/{invitation_id}/revoke")
@require_permissions("member.invite", workspace_scoped=True)
@db_transaction_handler("revoke invitation", auto_commit=True)
async def revoke_invitation(
    invitation_id: str,
    request: Request,
    revoke_data: RevokeInvitationRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Revoke an invitation - Thin controller using InvitationService
    """
    user_id = current_user.get("identity")
    logger.info(f"User {user_id} attempting to revoke invitation {invitation_id}")

    # Get user using UserService
    user_service = UserService(db)
    user = await user_service.get_user_by_id(UUID(user_id))

    # Use InvitationService to get invitation
    service = InvitationService(db)
    invitation = await service.get_invitation_by_id(UUID(invitation_id))

    # Check permission: must be invitation creator or workspace admin (route-level authorization)
    is_creator = str(invitation.invited_by_user_id) == str(user_id)

    # Check if user has admin role in the workspace
    result = await db.execute(
        select(UserRole)
        .join(Role, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id == UUID(user_id),
            UserRole.workspace_id == invitation.workspace_id,
            Role.name.in_(["admin", "owner", "workspace_admin"])
        )
    )
    is_admin = result.first() is not None

    if not is_creator and not is_admin:
        raise WrextAuthenticationException(
            message="Insufficient permissions to revoke this invitation"
        )

    # Store old status for audit
    old_status = invitation.status

    # Use service to revoke invitation (handles business logic)
    invitation = await service.revoke_invitation(
        invitation_id=UUID(invitation_id),
        revoked_by_user_id=UUID(user_id)
    )

    # Create audit log (audit concern - stays in route)
    await create_audit_log_async(
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

    # No need for flush/refresh - service handles it
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
