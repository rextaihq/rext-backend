
from typing import Dict, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from emails.templates.workspace.invitation import create_workspace_invitation_email
from src.api.config import get_settings
from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import (
    BusinessRuleViolationException,
    DuplicateResourceException,
    ResourceNotFoundException,
    RextValidationException,
)
from src.api.middleware.rate_limiter import invitation_creation_rate_limit
from src.api.middleware.usage_limiter import check_member_limit
from src.api.models.enums import InvitationStatus
from src.api.models.user_models.invitations import InvitationStatus, UserInvitations
from src.api.models.user_models.roles import Role
from src.api.models.user_models.users import Users
from src.api.schema.invitation_schema import (
    RevokeInvitationRequest,
    WorkspaceInvitationBulkRequest,
    WorkspaceInvitationCreateRequest,
)
from src.api.schema.response.invitation_responses import (
    BulkInvitationResponse,
    InvitationListResponse,
    ReceivedInvitationsResponse,
    RevokeInvitationResponse,
    SingleInvitationResponse,
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services.email_service import EmailService
from src.services.invitation_service import InvitationService
from src.services.notification_helper import schedule_if_allowed
from src.services.role_service import RoleService
from src.services.user_service import UserService
from src.utils.audit_helper import create_audit_log_async
from src.utils.auth_utils import verify_current_user
from src.utils.invitation_serializers import serialize_invitation_summary
from src.utils.invitation_utils import is_invitation_expired, normalize_email
from src.utils.logger import logger
from src.utils.response_utils import created, success
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.workspace_utils import resolve_and_verify_workspace

router = APIRouter(tags=["workspace-invitations"])

# Singular router for frontend parity (TASK-336)
singular_router = APIRouter(tags=["workspace-invitations"])


# Get settings instance
settings = get_settings()

async def send_workspace_invitation_email_task(
    email: str,
    subject: str,
    body: str,
    workspace_id: str,
    invitation_id: str
):
    """
    Background task to send workspace invitation email using EmailService.

    Args:
        email: Recipient email address
        subject: Email subject
        body: HTML email body
        workspace_id: Workspace ID for tracking
        invitation_id: Invitation ID for reference
    """
    from src.api.database.async_database import get_async_db_context

    try:
        async with get_async_db_context() as async_db:
            email_service = EmailService(async_db)
            await email_service.send_email(
                to=email,
                subject=subject,
                html=body,
                workspace_id=UUID(workspace_id),
                template_type="workspace_invitation",
                tags={"type": "workspace", "action": "invitation", "invitation_id": invitation_id}
            )
            logger.info(
                "Workspace invitation email sent successfully",
                extra={
                    "email": email,
                    "workspace_id": workspace_id,
                    "invitation_id": invitation_id
                }
            )
    except Exception:
        logger.error(
            "Failed to send workspace invitation email",
            exc_info=True,
            extra={
                "email": email,
                "workspace_id": workspace_id,
                "invitation_id": invitation_id
            }
        )

def _serialize_invitation(
    invitation: UserInvitations,
    role: Optional[Role],
    invited_by: Optional[Users],
) -> Dict[str, Optional[str]]:
    expires_at = (
        invitation.expires_at.isoformat() if invitation.expires_at else None
    )
    return {
        "id": str(invitation.id),
        "workspace_id": str(invitation.workspace_id),
        "email": invitation.email,
        "role_id": str(invitation.role_id) if invitation.role_id else None,
        "role_name": role.display_name if role else None,
        "status": invitation.status,
        "expires_at": expires_at,
        "created_at": invitation.created_at.isoformat()
        if invitation.created_at
        else None,
        "invited_by_user_id": str(invitation.invited_by_user_id)
        if invitation.invited_by_user_id
        else None,
        "invited_by_name": invited_by.display_name if invited_by else None,
        "is_expired": is_invitation_expired(invitation),
    }


@router.get(
    "/{workspace_id}/invitations",
    summary="List invitations for a workspace",
    response_model=SuccessResponse[InvitationListResponse]
)
@db_transaction_handler("list workspace invitations", auto_commit=False)
@require_permissions("member.invite", workspace_scoped=True)
async def list_workspace_invitations(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Return invitations created for the workspace."""
    user_uuid = UUID(str(user.get("identity")))
    await verify_current_user(db, str(user_uuid))
    workspace, _membership = await resolve_and_verify_workspace(
        db,
        workspace_id,
        user_uuid,
    )

    # Get invitations via InvitationService
    invitation_service = InvitationService(db)
    invitations = await invitation_service.get_workspace_invitations(workspace.id)

    # Collect IDs for batch loading
    role_ids = {inv.role_id for inv in invitations if inv.role_id}
    inviter_ids = {
        inv.invited_by_user_id for inv in invitations if inv.invited_by_user_id
    }

    # Load roles and users via services (batch optimization)
    role_service = RoleService(db)
    user_service = UserService(db)
    roles = await role_service.get_roles_by_ids(list(role_ids))
    inviters = await user_service.get_users_by_ids(list(inviter_ids))

    payload = [
        serialize_invitation_summary(inv, roles.get(inv.role_id), inviters.get(inv.invited_by_user_id))
        for inv in invitations
    ]

    return success(
        data={
            "invitations": payload,
            "total_count": len(payload),
        },
        request=request,
        message=f"Retrieved {len(payload)} invitation(s)",
    )


@router.post(
    "/{workspace_id}/invitations",
    status_code=status.HTTP_201_CREATED,
    summary="Create workspace invitation",
    response_model=SuccessResponse[SingleInvitationResponse]
)
@db_transaction_handler("create workspace invitation", auto_commit=True)
@require_permissions("member.invite", workspace_scoped=True)
async def create_workspace_invitation(
    workspace_id: str,
    payload: WorkspaceInvitationCreateRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
    _: None = Depends(check_member_limit()),
    __: None = Depends(invitation_creation_rate_limit()),  # Add rate limiting
):
    """Create an invitation tied to the workspace."""
    user_uuid = UUID(str(user.get("identity")))
    await verify_current_user(db, str(user_uuid))
    workspace, _membership = await resolve_and_verify_workspace(
        db,
        workspace_id,
        user_uuid,
    )

    # Get role via RoleService
    role_service = RoleService(db)
    role = await role_service.get_role_by_id(UUID(payload.role_id))

    # Create invitation via InvitationService
    invitation_service = InvitationService(db)
    try:
        invitation = await invitation_service.create_invitation(
            email=payload.email,
            workspace_id=workspace.id,
            role_id=role.id,
            invited_by_user_id=user_uuid,
            expiry_days=payload.expiry_days or 7,
        )
    except DuplicateResourceException:
        raise
    except BusinessRuleViolationException:
        raise

    # Get inviter details via UserService
    user_service = UserService(db)
    inviter = await user_service.get_user_by_id(user_uuid)

    frontend_url = settings.FRONTEND_URL

    # Serialize invitation BEFORE async operations to avoid lazy-load issues
    invitation_data = _serialize_invitation(invitation, role, inviter)

    # Eagerly load attributes before async operations to avoid lazy-load issues
    workspace_id = workspace.id
    workspace_name = workspace.name
    role_id = role.id
    role_display_name = role.display_name or role.name
    invitation_id = invitation.id
    invitation_email = invitation.email
    invitation_token = invitation.invitation_token

    # Safely access inviter attributes
    if inviter:
        inviter_display_name = inviter.display_name or inviter.full_name or inviter.email or "A teammate"
        inviter_full_name = inviter.full_name
        inviter_email = inviter.email
    else:
        inviter_display_name = "A teammate"
        inviter_full_name = None
        inviter_email = None

    invitation_html = create_workspace_invitation_email(
        workspace_name=workspace_name,
        inviter_name=inviter_display_name,
        invitation_token=invitation_token,
        role_name=role_display_name,
        expiry_days=payload.expiry_days or 7,
        frontend_url=frontend_url,
    )

    background_tasks.add_task(
        send_workspace_invitation_email_task,
        email=invitation_email,
        subject=f"You're invited to join {workspace_name}",
        body=invitation_html,
        workspace_id=str(workspace_id),
        invitation_id=str(invitation_id)
    )

    await create_audit_log_async(
        db=db,
        user_id=str(user_uuid),
        action="invitation.create",
        resource_type="invitation",
        resource_id=str(invitation_id),
        new_values={
            "email": invitation_email,
            "workspace_id": str(workspace_id),
            "role_id": str(role_id),
        },
        request=request,
        workspace_id=workspace_id,
        full_name=inviter_full_name,
        user_email=inviter_email,
    )

    # Check if user exists to send in-app notification
    existing_user = await user_service.get_user_by_email(invitation_email)
    if existing_user:
        await schedule_if_allowed(
            db=db,
            user_id=str(existing_user.id),
            background_tasks=background_tasks,
            pref_flag="ws_invite_received",
            message=f"You have been invited to join workspace {workspace_name}",
            payload={
                "workspace_id": str(workspace_id),
                "workspace_name": workspace_name,
                "invitation_id": str(invitation_id),
                "role_name": role_display_name,
                "invited_by": inviter_display_name
            },
            workspace_id=str(workspace_id),
        )
        logger.info(
            "Scheduled in-app notification for existing user",
            extra={
                "user_id": str(existing_user.id),
                "workspace_id": str(workspace_id),
                "invitation_id": str(invitation_id)
            }
        )

    return created(
        data={
            "invitation": invitation_data
        },
        request=request,
        message="Invitation created successfully",
    )


@router.post(
    "/{workspace_id}/invitations/bulk",
    status_code=status.HTTP_201_CREATED,
    summary="Create multiple workspace invitations",
    response_model=SuccessResponse[BulkInvitationResponse]
)
@db_transaction_handler("create bulk workspace invitations", auto_commit=True)
@require_permissions("member.invite", workspace_scoped=True)
async def create_bulk_workspace_invitations(
    workspace_id: str,
    payload: WorkspaceInvitationBulkRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
    _: None = Depends(check_member_limit()),
    __: None = Depends(invitation_creation_rate_limit()),  # Add rate limiting
):
    """Create invitations for multiple recipients."""
    user_uuid = UUID(str(user.get("identity")))
    await verify_current_user(db, str(user_uuid))
    workspace, _membership = await resolve_and_verify_workspace(
        db,
        workspace_id,
        user_uuid,
    )

    # Get role via RoleService
    role_service = RoleService(db)
    role = await role_service.get_role_by_id(UUID(payload.role_id))

    # Get inviter details via UserService
    user_service = UserService(db)
    inviter = await user_service.get_user_by_id(user_uuid)

    frontend_url = settings.FRONTEND_URL

    # Eagerly load all attributes we'll need before the loop
    workspace_id_value = workspace.id
    workspace_name_value = workspace.name
    role_id_value = role.id
    role_display_name = role.display_name or role.name
    inviter_display_name = (inviter.display_name or inviter.full_name or inviter.email or "A teammate") if inviter else "A teammate"
    inviter_full_name = inviter.full_name if inviter else None
    inviter_email = inviter.email if inviter else None

    invitation_service = InvitationService(db)
    created_invitations = []
    failures = []

    for email in payload.emails:
        try:
            invitation = await invitation_service.create_invitation(
                email=email,
                workspace_id=workspace_id_value,
                role_id=role_id_value,
                invited_by_user_id=user_uuid,
                expiry_days=payload.expiry_days or 7,
            )

            # Eagerly load invitation attributes BEFORE using them
            invitation_id = invitation.id
            invitation_token = invitation.invitation_token
            invitation_email = invitation.email

            # Store eagerly-loaded values for later use
            created_invitations.append({
                "email": invitation_email,
                "id": str(invitation_id),
            })

            invitation_html = create_workspace_invitation_email(
                workspace_name=workspace_name_value,
                inviter_name=inviter_display_name,
                invitation_token=invitation_token,
                role_name=role_display_name,
                expiry_days=payload.expiry_days or 7,
                frontend_url=frontend_url,
            )

            background_tasks.add_task(
                send_workspace_invitation_email_task,
                email=email,
                subject=f"You're invited to join {workspace_name_value}",
                body=invitation_html,
                workspace_id=str(workspace_id_value),
                invitation_id=str(invitation_id)
            )

            # Check if user exists to send in-app notification
            existing_user = await user_service.get_user_by_email(email)
            if existing_user:
                await schedule_if_allowed(
                    db=db,
                    user_id=str(existing_user.id),
                    background_tasks=background_tasks,
                    pref_flag="ws_invite_received",
                    message=f"You have been invited to join workspace {workspace_name_value}",
                    payload={
                        "workspace_id": str(workspace_id_value),
                        "workspace_name": workspace_name_value,
                        "invitation_id": str(invitation_id),
                        "role_name": role_display_name,
                        "invited_by": inviter_display_name
                    },
                    workspace_id=str(workspace_id_value),
                )
        except (DuplicateResourceException, BusinessRuleViolationException) as exc:
            failures.append({"email": email, "error": str(exc)})

    await create_audit_log_async(
        db=db,
        user_id=str(user_uuid),
        action="invitation.bulk_create",
        resource_type="invitation",
        resource_id="bulk",
        new_values={
            "workspace_id": str(workspace_id_value),
            "emails": payload.emails,
            "role_id": payload.role_id,
        },
        request=request,
        workspace_id=workspace_id_value,
        full_name=inviter_full_name,
        user_email=inviter_email,
    )

    return created(
        data={
            "total_requested": len(payload.emails),
            "successful": len(created_invitations),
            "failed": len(failures),
            "results": [
                {
                    "email": inv["email"],
                    "success": True,
                    "invitation_id": inv["id"],
                }
                for inv in created_invitations
            ]
            + [
                {"email": failure["email"], "success": False, "error_message": failure["error"]}
                for failure in failures
            ],
        },
        request=request,
        message="Bulk invitations processed",
    )


@router.post(
    "/{workspace_id}/invitations/{invitation_id}/resend",
    summary="Resend workspace invitation",
    response_model=SuccessResponse[SingleInvitationResponse]
)
@db_transaction_handler("resend workspace invitation", auto_commit=True)
@require_permissions("member.invite", workspace_scoped=True)
async def resend_workspace_invitation(
    workspace_id: str,
    invitation_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
    __: None = Depends(invitation_creation_rate_limit()),
):
    """Resend a pending invitation with a new token and extended expiry."""
    user_uuid = UUID(str(user.get("identity")))
    await verify_current_user(db, str(user_uuid))
    workspace, _membership = await resolve_and_verify_workspace(
        db,
        workspace_id,
        user_uuid,
    )

    service = InvitationService(db)
    invitation = await service.get_invitation_by_id(UUID(invitation_id))
    if invitation.workspace_id != workspace.id:
        raise ResourceNotFoundException(
            resource_type="invitation",
            resource_id=invitation_id,
        )

    # Resend invitation (generates new token and extends expiry)
    invitation = await service.resend_invitation(
        invitation_id=UUID(invitation_id),
        extend_days=7
    )

    # Get role and inviter details
    role_service = RoleService(db)
    user_service = UserService(db)
    role = await role_service.get_role_by_id(invitation.role_id)
    inviter = await user_service.get_user_by_id(user_uuid)

    frontend_url = settings.FRONTEND_URL

    # Eagerly load attributes before async operations
    workspace_id_value = workspace.id
    workspace_name_value = workspace.name
    role_display_name = role.display_name or role.name
    invitation_id_value = invitation.id
    invitation_email = invitation.email
    invitation_token = invitation.invitation_token
    inviter_display_name = (inviter.display_name or inviter.full_name or inviter.email or "A teammate") if inviter else "A teammate"
    inviter_full_name = inviter.full_name if inviter else None
    inviter_email = inviter.email if inviter else None

    invitation_html = create_workspace_invitation_email(
        workspace_name=workspace_name_value,
        inviter_name=inviter_display_name,
        invitation_token=invitation_token,
        role_name=role_display_name,
        expiry_days=7,
        frontend_url=frontend_url,
    )

    background_tasks.add_task(
        send_workspace_invitation_email_task,
        email=invitation_email,
        subject=f"You're invited to join {workspace_name_value}",
        body=invitation_html,
        workspace_id=str(workspace_id_value),
        invitation_id=str(invitation_id_value)
    )

    await create_audit_log_async(
        db=db,
        user_id=str(user_uuid),
        action="invitation.resend",
        resource_type="invitation",
        resource_id=invitation_id,
        new_values={
            "new_token": invitation_token,
            "new_expires_at": invitation.expires_at.isoformat()
        },
        request=request,
        workspace_id=workspace_id_value,
        full_name=inviter_full_name,
        user_email=inviter_email,
    )

    logger.info(
        "Workspace invitation resent",
        extra={
            "workspace_id": str(workspace_id_value),
            "invitation_id": invitation_id,
            "email": invitation_email,
        },
    )

    # Serialize invitation for response
    invitation_data = _serialize_invitation(invitation, role, inviter)

    return success(
        data={"invitation": invitation_data},
        request=request,
        message="Invitation resent successfully",
    )


@router.delete(
    "/{workspace_id}/invitations/{invitation_id}",
    summary="Revoke workspace invitation",
    response_model=SuccessResponse[RevokeInvitationResponse]
)
@db_transaction_handler("revoke workspace invitation", auto_commit=True)
@require_permissions("member.invite", workspace_scoped=True)
async def revoke_workspace_invitation(
    workspace_id: str,
    invitation_id: str,
    request: Request,
    payload: Optional[RevokeInvitationRequest] = None,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Revoke a pending invitation for the workspace."""
    user_uuid = UUID(str(user.get("identity")))
    await verify_current_user(db, str(user_uuid))
    workspace, _membership = await resolve_and_verify_workspace(
        db,
        workspace_id,
        user_uuid,
    )

    service = InvitationService(db)
    invitation = await service.get_invitation_by_id(UUID(invitation_id))
    if invitation.workspace_id != workspace.id:
        raise ResourceNotFoundException(
            resource_type="invitation",
            resource_id=invitation_id,
        )

    if invitation.status != InvitationStatus.PENDING:
        raise RextValidationException(
            message="Only pending invitations can be revoked",
            field_errors={"status": ["Invitation is not pending"]},
        )

    await service.revoke_invitation(
        invitation_id=UUID(invitation_id),
        revoked_by_user_id=user_uuid,
    )

    await create_audit_log_async(
        db=db,
        user_id=str(user_uuid),
        action="invitation.revoke",
        resource_type="invitation",
        resource_id=invitation_id,
        old_values={"status": InvitationStatus.PENDING},
        new_values={
            "status": InvitationStatus.REVOKED,
            "reason": payload.reason if payload else None,
        },
        request=request,
        workspace_id=workspace.id,
    )

    logger.info(
        "Workspace invitation revoked",
        extra={
            "workspace_id": str(workspace.id),
            "invitation_id": invitation_id,
            "revoked_by": str(user_uuid),
        },
    )

    return success(
        data={"invitation_id": invitation_id, "status": InvitationStatus.REVOKED},
        request=request,
        message="Invitation revoked successfully",
    )



@singular_router.get("/invitations/received", response_model=SuccessResponse[ReceivedInvitationsResponse])
@router.get("/invitations/received", response_model=SuccessResponse[ReceivedInvitationsResponse]) # Also keep plural for consistency
# No permission gate: this only ever returns/acts on the caller's own
# invitations (filtered by current_user), so authentication is the check.
# It used to require member.read, which forced that workspace permission
# onto the global "user" role and became a floor under every workspace.
@db_transaction_handler("get received invitations", auto_commit=False)
async def get_received_invitations(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get all received (pending) invitations for the current user.

    This endpoint mirrors /api/v1/user/invitations/pending but is mounted
    at a path the frontend expects. Returns invitations where the email
    matches the current user and status is 'pending'.
    """
    from src.api.models.user_models.invitations import UserInvitations
    from src.api.models.user_models.users import Users

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

    user_email = normalize_email(user.email)

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

    # Filter out expired invitations
    from src.utils.invitation_utils import is_invitation_expired

    active_invitations = [
        inv for inv in invitations if not is_invitation_expired(inv)
    ]

    invitation_list = []
    for inv in active_invitations:
        invitation_list.append({
            "id": str(inv.id),
            "workspace_id": str(inv.workspace_id),
            "workspace_name": inv.workspace.name if inv.workspace else None,
            "role_id": str(inv.role_id),
            "status": inv.status,
            "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
        })

    return success(
        data={
            "invitations": invitation_list,
            "total_count": len(invitation_list)
        },
        message="Received invitations retrieved"
    )