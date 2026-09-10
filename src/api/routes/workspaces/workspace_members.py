from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from emails.templates.workspace.invitation import create_workspace_invitation_email
from src.api.config import get_settings
from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    RextValidationException,
)
from src.api.middleware.rate_limiter import invitation_creation_rate_limit
from src.api.middleware.usage_limiter import check_member_limit
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.schema.response.invitation_responses import SingleInvitationResponse
from src.api.schema.response.member_responses import (
    MemberListResponse,
    MemberRemoveResponse,
    MemberUpdateRoleResponse,
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.workspace_schema import (
    AddWorkspaceMemberRequest,
    ChangeMemberRoleRequest,
)
from src.api.security.dependencies import get_current_user
from src.services.invitation_service import InvitationService
from src.services.member_service import MemberService
from src.services.notification_helper import schedule_if_allowed
from src.services.user_service import UserService
from src.utils.auth_utils import verify_current_user
from src.utils.logger import logger
from src.utils.response_utils import created, success
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.storage import resolve_avatar_url
from src.utils.workspace_utils import resolve_and_verify_workspace

router = APIRouter(tags=["workspace-members"])

# Reused from the invitations router so both entry points send the same
# email content and go through the same background-task delivery path.
from .workspace_invitations import (  # noqa: E402
    _serialize_invitation as _serialize_invitation_summary,
)
from .workspace_invitations import (  # noqa: E402
    send_workspace_invitation_email_task,
)

# Get settings instance
settings = get_settings()


async def send_role_changed_notification(
    workspace_id: str,
    workspace_name: str,
    workspace_slug: str,
    member_email: str,
    member_user_id: str,
    member_name: str,
    old_role_name: str,
    new_role_name: str,
    changed_by_name: str,
):
    """Send role changed notification to member."""
    from src.api.database.async_database import get_async_db_context
    from src.services.email_helpers import send_workspace_email

    try:
        async with get_async_db_context() as async_db:
            frontend_url = settings.FRONTEND_URL

            await send_workspace_email(
                db=async_db,
                email_type="role_changed",
                workspace_id=UUID(workspace_id),
                recipient_email=member_email,
                user_id=UUID(member_user_id),
                workspace_name=workspace_name,
                workspace_slug=workspace_slug,
                member_name=member_name,
                recipient_name=member_name,
                old_role_name=old_role_name,
                new_role_name=new_role_name,
                changed_by_name=changed_by_name,
                frontend_url=frontend_url,
            )

            logger.info(
                "Sent role changed notification",
                extra={"recipient_email": member_email},
            )
    except Exception as e:
        logger.error(
            "Failed to send role changed notification",
            extra={"error": str(e)},
            exc_info=True,
        )


async def send_member_removed_notification(
    workspace_id: str,
    workspace_name: str,
    member_email: str,
    member_user_id: str,
    member_name: str,
    removed_by_name: str,
    reason: str = None,
):
    """Send member removed notification."""
    from src.api.database.async_database import get_async_db_context
    from src.services.email_helpers import send_workspace_email

    try:
        async with get_async_db_context() as async_db:
            frontend_url = settings.FRONTEND_URL

            await send_workspace_email(
                db=async_db,
                email_type="member_removed",
                workspace_id=UUID(workspace_id),
                recipient_email=member_email,
                user_id=UUID(member_user_id),
                workspace_name=workspace_name,
                member_name=member_name,
                recipient_name=member_name,
                removed_by_name=removed_by_name,
                reason=reason,
                frontend_url=frontend_url,
            )
            # Note: member_removed email links to the workspace list ("/w"),
            # not a specific workspace, since the recipient no longer has access to it.

            logger.info(
                "Sent member removed notification",
                extra={"recipient_email": member_email},
            )
    except Exception as e:
        logger.error(
            "Failed to send member removed notification",
            extra={"error": str(e)},
            exc_info=True,
        )


def _serialize_member(
    member: WorkspaceMembers, user: Users, roles_arg: Any = None
) -> Dict[str, Any]:
    """Transform member + user join row into API response structure with aggregated roles."""
    # Construct full name from first_name and last_name, fallback to display_name or email
    full_name = getattr(user, "full_name", None)
    if not full_name:
        full_name = getattr(user, "display_name", None) or getattr(user, "email", "")

    roles_list = []
    if isinstance(roles_arg, list):
        roles_list = roles_arg
    elif roles_arg is not None:
        roles_list = [roles_arg]

    primary_role = roles_list[0] if roles_list else None
    combined_display_name = (
        ", ".join(r.display_name for r in roles_list) if roles_list else "No role assigned"
    )

    return {
        "id": str(member.id),
        "user_id": str(member.user_id),
        "workspace_id": str(member.workspace_id),
        "status": member.status,
        "is_default": member.is_default,
        "joined_at": member.joined_at.isoformat() if member.joined_at else None,
        "last_activity_at": (
            member.last_activity_at.isoformat() if member.last_activity_at else None
        ),
        "role": {
            "id": str(primary_role.id) if primary_role else None,
            "name": primary_role.name if primary_role else None,
            "display_name": combined_display_name,
        }
        if primary_role
        else None,
        "roles": [
            {
                "id": str(r.id),
                "name": r.name,
                "display_name": r.display_name,
            }
            for r in roles_list
        ],
        "user": {
            "id": str(user.id),
            "name": full_name,  # Frontend expects "name" field
            "email": getattr(user, "email", ""),
            # Stored as a bare object key, so it must be resolved to a real URL
            "avatar": resolve_avatar_url(getattr(user, "avatar_url", None)),
            "display_name": getattr(user, "display_name", None),  # Keep for backward compatibility
            "is_verified": getattr(user, "email_verified", False),
        },
    }


@router.get(
    "/{workspace_id}/members",
    summary="List workspace members",
    response_model=SuccessResponse[MemberListResponse],
)
@require_permissions("member.read", workspace_scoped=True)
@db_transaction_handler("get workspace members", auto_commit=False)
async def list_workspace_members(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Return the members for the given workspace."""
    user_id = user.get("identity")
    await verify_current_user(db, user_id)
    workspace, _membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Get members with user details via service
    member_service = MemberService(db)
    rows = await member_service.get_workspace_members_with_users(workspace.id)

    members = [
        _serialize_member(member, user_obj, roles_list) for member, user_obj, roles_list in rows
    ]

    return success(
        data={"members": members, "total_count": len(members)},
        request=request,
        message=f"Retrieved {len(members)} member(s)",
    )


@router.post(
    "/{workspace_id}/members",
    status_code=status.HTTP_201_CREATED,
    summary="Invite a member to workspace",
    response_model=SuccessResponse[SingleInvitationResponse],
)
@db_transaction_handler("add workspace member", auto_commit=True)
@require_permissions("member.invite", workspace_scoped=True)
async def add_workspace_member(
    workspace_id: str,
    payload: AddWorkspaceMemberRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
    _: None = Depends(check_member_limit()),
    __: None = Depends(invitation_creation_rate_limit()),
):
    """
    Invite a user (by email) to the workspace.

    Creates a pending invitation and emails the recipient — the user only
    becomes a workspace member once they accept it. This mirrors
    POST /{workspace_id}/invitations (defaulting to the 'viewer' role,
    since this endpoint's payload only carries an email) rather than
    granting access immediately.
    """
    user_id = user.get("identity")
    await verify_current_user(db, user_id)
    workspace, _membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Default to the 'viewer' role since this endpoint doesn't accept a role_id
    role_result = await db.execute(
        select(Role).where(Role.name == "viewer", Role.is_workspace_role.is_(True))
    )
    role = role_result.scalar_one_or_none()
    if not role:
        raise ResourceNotFoundException(
            message="Default role 'viewer' not found. Roles must be seeded.",
            resource_type="role",
        )

    invitation_service = InvitationService(db)
    invitation = await invitation_service.create_invitation(
        email=payload.email,
        workspace_id=workspace.id,
        role_id=role.id,
        invited_by_user_id=UUID(user_id),
        expiry_days=7,
    )

    user_service = UserService(db)
    inviter = await user_service.get_user_by_id(UUID(user_id))

    frontend_url = settings.FRONTEND_URL

    # Eagerly capture attributes before further async work to avoid lazy-load issues
    workspace_name = workspace.name
    role_display_name = role.display_name or role.name
    invitation_id = invitation.id
    invitation_email = invitation.email
    invitation_token = invitation.invitation_token
    inviter_display_name = (
        (inviter.display_name or inviter.full_name or inviter.email or "A teammate")
        if inviter
        else "A teammate"
    )

    invitation_data = _serialize_invitation_summary(invitation, role, inviter)

    invitation_html = create_workspace_invitation_email(
        workspace_name=workspace_name,
        inviter_name=inviter_display_name,
        invitation_token=invitation_token,
        role_name=role_display_name,
        expiry_days=7,
        frontend_url=frontend_url,
    )

    background_tasks.add_task(
        send_workspace_invitation_email_task,
        email=invitation_email,
        subject=f"You're invited to join {workspace_name}",
        body=invitation_html,
        workspace_id=str(workspace.id),
        invitation_id=str(invitation_id),
    )

    from src.utils.audit_helper import create_audit_log_async

    await create_audit_log_async(
        db=db,
        user_id=UUID(user_id),
        action="invitation.create",
        resource_type="invitation",
        resource_id=str(invitation_id),
        workspace_id=workspace.id,
        new_values={"email": invitation_email, "role_id": str(role.id)},
        request=request,
    )

    logger.info(
        "Workspace invitation created via members endpoint",
        extra={
            "workspace_id": str(workspace.id),
            "invited_email": invitation_email,
            "invited_by": user_id,
        },
    )

    return created(
        data={"invitation": invitation_data},
        request=request,
        message=f"Invitation sent to {invitation_email}",
    )


@router.delete(
    "/{workspace_id}/members/{member_id}",
    summary="Remove workspace member",
    response_model=SuccessResponse[MemberRemoveResponse],
)
@db_transaction_handler("remove workspace member", auto_commit=True)
@require_permissions("member.remove", workspace_scoped=True)
async def remove_workspace_member(
    workspace_id: str,
    member_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Remove a member from the workspace."""
    user_id = user.get("identity")
    await verify_current_user(db, user_id)
    workspace, _membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Get member with user details via service
    member_service = MemberService(db)
    member, member_user = await member_service.get_member_with_user(UUID(member_id), workspace.id)

    # Validate member can be removed — check if they are the workspace owner by role
    owner_role_check = await db.execute(
        select(UserRole)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            UserRole.user_id == member.user_id,
            UserRole.workspace_id == workspace.id,
            Role.hierarchy_level >= 60,  # workspace_owner or higher (60 is workspace_owner)
        )
    )
    if owner_role_check.scalar_one_or_none() is not None:
        raise RextValidationException(
            message="Cannot remove workspace owner",
            field_errors={
                "member_id": ["This member is the workspace owner and cannot be removed"]
            },
        )

    # Get current user details for notification
    user_service = UserService(db)
    current_user_obj = await user_service.get_user_by_id(UUID(user_id))

    # Remove member via service
    await member_service.remove_member(workspace_id=workspace.id, user_id=member.user_id)

    # also remove the invite if exists
    await member_service.remove_invitation_if_exists(
        workspace_id=workspace.id, email=member_user.email
    )

    #  also remove the user roles assigned in the workspace
    await member_service.remove_user_roles_in_workspace(
        workspace_id=workspace.id,
        user_id=member.user_id,
    )

    from src.utils.audit_helper import create_audit_log_async

    await create_audit_log_async(
        db=db,
        user_id=UUID(user_id),
        action="member.remove",
        resource_type="workspace_member",
        resource_id=str(member_id),
        workspace_id=workspace.id,
        old_values={
            "user_id": str(member.user_id),
            "email": member_user.email if member_user else None,
        },
        request=request,
    )

    # Send member removed notification
    if member_user:
        background_tasks.add_task(
            send_member_removed_notification,
            workspace_id=str(workspace.id),
            workspace_name=workspace.name,
            member_email=member_user.email,
            member_user_id=str(member_user.id),
            member_name=member_user.full_name or member_user.display_name or member_user.email,
            removed_by_name=current_user_obj.full_name if current_user_obj else "Admin",
        )
    logger.info("Removing Member")
    payload = {
        "workspace_id": str(workspace.id),
        "member_id": str(member_id),
        "removed_by": user_id,
    }

    logger.info("Scheduling member removed notification")
    await schedule_if_allowed(
        db=db,
        user_id=str(member_user.id),
        background_tasks=background_tasks,
        pref_flag="ws_member_removed",
        message="You have been removed from a workspace.",
        payload=payload,
        workspace_id=str(workspace.id),
    )
    logger.info(
        "Workspace member removed",
        extra={
            "workspace_id": str(workspace.id),
            "member_id": member_id,
            "removed_by": user_id,
        },
    )

    return success(
        data={"member_id": member_id},
        request=request,
        message="Member removed successfully",
    )


@router.patch(
    "/{workspace_id}/members/{member_id}/role",
    summary="Update workspace member role",
    response_model=SuccessResponse[MemberUpdateRoleResponse],
)
@db_transaction_handler("change workspace member role", auto_commit=True)
@require_permissions("member.update", workspace_scoped=True)
async def update_workspace_member_role(
    workspace_id: str,
    member_id: str,
    payload: ChangeMemberRoleRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Assign a new role to the given member."""
    user_id = user.get("identity")
    await verify_current_user(db, user_id)
    workspace, _membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Update member role via service
    member_service = MemberService(db)
    member, member_user, new_role, old_role = await member_service.update_member_role(
        workspace_id=workspace.id,
        member_id=UUID(member_id),
        new_role_id=UUID(payload.role_id),
        assigned_by_user_id=UUID(user_id),
    )
    # Capture the previous role ID for logging/response (may be None)
    previous_role_id = old_role.id if old_role else None

    from src.utils.audit_helper import create_audit_log_async

    await create_audit_log_async(
        db=db,
        user_id=UUID(user_id),
        action="member.role_update",
        resource_type="workspace_member",
        resource_id=str(member_id),
        workspace_id=workspace.id,
        old_values={"role_id": str(previous_role_id) if previous_role_id else None},
        new_values={"role_id": str(new_role.id), "role_name": new_role.name},
        request=request,
    )

    # Get current user details for notification
    user_service = UserService(db)
    current_user_obj = await user_service.get_user_by_id(UUID(user_id))

    # Send role changed notification to the member
    if member_user:
        background_tasks.add_task(
            send_role_changed_notification,
            workspace_id=str(workspace.id),
            workspace_name=workspace.name,
            workspace_slug=workspace.slug,
            member_email=member_user.email,
            member_user_id=str(member_user.id),
            member_name=member_user.full_name or member_user.display_name or member_user.email,
            old_role_name=old_role.display_name if old_role else "Member",
            new_role_name=new_role.display_name,
            changed_by_name=current_user_obj.full_name if current_user_obj else "Admin",
        )

    payload = {
        "workspace_id": str(workspace_id),
        "member_id": str(member_id),
        "new_role": {
            "id": str(new_role.id),
            "name": new_role.name,
            "display_name": new_role.display_name,
        },
    }
    # Current timestamp for response
    timestamp = datetime.now(timezone.utc)

    await schedule_if_allowed(
        db=db,
        user_id=str(member_user.id),
        background_tasks=background_tasks,
        pref_flag="ws_role_changed",
        message="Your role in a workspace was updated.",
        payload=payload,
        workspace_id=str(workspace.id),
    )

    logger.info(
        "Workspace member role updated",
        extra={
            "workspace_id": str(workspace.id),
            "member_id": member_id,
            "updated_by": user_id,
            "old_role_id": str(previous_role_id) if previous_role_id else None,
            "new_role_id": new_role.id,
        },
    )

    return success(
        data={
            "member": {
                "id": str(member.id),
                "workspace_id": str(workspace.id),
                "user_id": str(member.user_id),
                "role_id": str(new_role.id),
                "updated_at": timestamp.isoformat(),
            }
        },
        request=request,
        message=f"Role updated to {new_role.display_name}",
    )
