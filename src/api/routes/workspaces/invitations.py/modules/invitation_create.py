from fastapi import APIRouter, Depends, Request, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone, timedelta
from uuid import UUID
import uuid
import os

from src.utils.logger import logger
from src.utils.response_utils import success, created
from src.utils.invitation_utils import is_invitation_expired
from src.utils.audit_helper import create_audit_log
from src.utils.email_template_utils import render_workspace_email
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.config import get_settings
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    WrextAuthenticationException,
    WrextAPIException
)
from src.api.schema.invitation_schema import (
    CreateInvitationRequest,
    BulkCreateInvitationRequest,
    BulkInvitationResult,
)
from src.api.models.user_models.users import Users
from src.api.models.user_models.invitations import UserInvitations
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.services.email_service import EmailService
from src.utils.workspace_utils import resolve_and_verify_workspace
from src.utils.db_utils import get_or_404
from src.api.models.user_models.roles import Role
from .helpers import verify_workspace_exists, verify_role_exists
from src.services.invitation_service import InvitationService


router = APIRouter()


# Get settings instance
settings = get_settings()

async def send_workspace_invitation_email_task(
    email: str,
    workspace_id: str,
    workspace_name: str,
    inviter_name: str,
    role_name: str,
    invitation_token: str,
    expiry_days: int,
    frontend_url: str,
    invitation_id: str
):
    """
    Background task to send workspace invitation email using professional template.

    Args:
        email: Recipient email address
        workspace_id: Workspace ID for tracking
        workspace_name: Name of the workspace
        inviter_name: Name of the person inviting
        role_name: Role name for the invitation
        invitation_token: Invitation token
        expiry_days: Days until invitation expires
        frontend_url: Frontend URL
        invitation_id: Invitation ID for reference
    """
    from src.api.database.async_database import get_async_db_context
    from src.services.email_helpers import send_workspace_email

    try:
        async with get_async_db_context() as async_db:
            await send_workspace_email(
                db=async_db,
                email_type="invitation",
                workspace_id=UUID(workspace_id),
                recipient_email=email,
                workspace_name=workspace_name,
                inviter_name=inviter_name,
                role_name=role_name,
                invitation_token=invitation_token,
                expiry_days=expiry_days,
                frontend_url=frontend_url
            )
            logger.info(f"Workspace invitation email sent successfully to {email}")
    except Exception as e:
        logger.error(f"Failed to send workspace invitation email to {email}: {str(e)}", exc_info=True)


@router.get("/status")
async def get_invitation_status(request: Request):
    """Qa
    Endpoint to check the invitation service status.
    """
    return success(
        message="Invitation service is up and running.",
        data={"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
    )


@router.post("/", status_code=status.HTTP_201_CREATED)
@db_transaction_handler("create invitation", auto_commit=True)
@require_permissions("member.invite", workspace_scoped=True)
async def create_invitation(
    request: Request,
    invitation_data: CreateInvitationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new invitation for a user to join a workspace - Thin controller using InvitationService
    """
    user_id = current_user.get("identity")
    logger.info(f"User {user_id} creating invitation for {invitation_data.email}")

    # Verify workspace exists and user has access
    workspace, membership = await resolve_and_verify_workspace(db, str(invitation_data.workspace_id), uuid.UUID(user_id))

    # Verify role exists
    role = await get_or_404(db, Role, invitation_data.role_id, "role")

    # Use InvitationService to create invitation
    service = InvitationService(db)
    invitation = await service.create_invitation(
        email=invitation_data.email,
        workspace_id=UUID(str(invitation_data.workspace_id)),
        role_id=UUID(str(invitation_data.role_id)),
        invited_by_user_id=UUID(user_id),
        expiry_days=invitation_data.expiry_days
    )

    # Get inviter details for email (external service concern - stays in route)
    result = await db.execute(select(Users).where(Users.id == user_id))
    inviter = result.scalar_one_or_none()

    # Send invitation email in background using custom or default template
    frontend_url = settings.FRONTEND_URL
    invitation_link = f"{frontend_url}/invitations/accept?token={invitation.invitation_token}"

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
        send_workspace_invitation_email_task,
        email=invitation_data.email,
        subject=email_content["subject"],
        body=email_content["body"],
        workspace_id=str(invitation_data.workspace_id),
        invitation_id=str(invitation.id)
    )

    logger.info(f"Invitation created: {invitation.id} for {invitation_data.email} to workspace {workspace.name}")

    # Create audit log (audit concern - stays in route)
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

    return {
        "data": {
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
        "message": f"Invitation sent to {invitation_data.email}"
    }


@router.post("/bulk", status_code=status.HTTP_201_CREATED)
@db_transaction_handler("create bulk invitations", auto_commit=True)
@require_permissions("member.invite", workspace_scoped=True)
async def create_bulk_invitations(
    request: Request,
    invitation_data: BulkCreateInvitationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Create multiple invitations at once - Thin controller using InvitationService
    """
    user_id = current_user.get("identity")
    logger.info(f"User {user_id} creating bulk invitations for {len(invitation_data.emails)} emails")

    # Verify workspace exists and user has access
    workspace = await verify_workspace_exists(db, invitation_data.workspace_id)
    workspace_check, membership_check = await resolve_and_verify_workspace(db, str(invitation_data.workspace_id), uuid.UUID(user_id))

    # Verify role exists
    role = await verify_role_exists(db, invitation_data.role_id)

    # Get inviter details for email
    result = await db.execute(select(Users).where(Users.id == user_id))
    inviter = result.scalar_one_or_none()
    inviter_name = inviter.display_name if inviter else "A workspace member"

    # Use InvitationService to create invitations
    service = InvitationService(db)
    results = []
    successful = 0
    failed = 0

    for email in invitation_data.emails:
        try:
            # Use service to create invitation (handles all business logic)
            invitation = await service.create_invitation(
                email=email,
                workspace_id=UUID(str(invitation_data.workspace_id)),
                role_id=UUID(str(invitation_data.role_id)),
                invited_by_user_id=UUID(user_id),
                expiry_days=invitation_data.expiry_days
            )

            # Send invitation email asynchronously using professional template
            frontend_url = settings.FRONTEND_URL

            background_tasks.add_task(
                send_workspace_invitation_email_task,
                email=email,
                workspace_id=str(invitation_data.workspace_id),
                workspace_name=workspace.name,
                inviter_name=inviter_name,
                role_name=role.display_name or role.name,
                invitation_token=invitation.invitation_token,
                expiry_days=invitation_data.expiry_days,
                frontend_url=frontend_url,
                invitation_id=str(invitation.id)
            )

            # Audit log for each invitation (audit concern - stays in route)
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
                    "expires_at": invitation.expires_at.isoformat()
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

    logger.info(f"Bulk invitation completed: {successful} successful, {failed} failed")

    return {
        "data": {
            "total_requested": len(invitation_data.emails),
            "successful": successful,
            "failed": failed,
            "results": [r.dict() for r in results]
        },
        "message": f"Bulk invitation completed: {successful} sent, {failed} failed"
    }
