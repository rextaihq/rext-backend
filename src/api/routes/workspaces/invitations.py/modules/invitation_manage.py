from fastapi import APIRouter, Depends, Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from uuid import UUID

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
from src.services.invitation_service import InvitationService


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
    Accept an invitation to join a workspace - Thin controller using InvitationService
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

    # Get workspace details for response
    workspace_result = await db.execute(
        select(WorkspaceModel).where(WorkspaceModel.id == invitation.workspace_id)
    )
    workspace = workspace_result.scalar_one_or_none()

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

    # Get user and invitation details for permission check
    result = await db.execute(select(Users).where(Users.id == user_id))
    user = result.scalar_one_or_none()

    # Use InvitationService to get invitation
    service = InvitationService(db)
    invitation = await service.get_invitation_by_id(UUID(invitation_id))

    # Check permission: must be invitation creator or workspace admin (route-level authorization)
    is_creator = str(invitation.invited_by_user_id) == str(user_id)
    # TODO: Implement proper workspace admin check
    is_admin = False  # Placeholder

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
