from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import UUID
import os

from fastapi import APIRouter, Depends, Request, status, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.config import get_settings
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    RextValidationException,
)
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.schema.workspace_schema import (
    AddWorkspaceMemberRequest,
    ChangeMemberRoleRequest,
)
from src.services.notification_helper import schedule_if_allowed
from src.api.security.dependencies import get_current_user
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.services.member_service import MemberService
from src.services.user_service import UserService
from src.utils.auth_utils import verify_current_user
from src.utils.logger import logger
from src.utils.response_utils import created, success
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.workspace_utils import resolve_and_verify_workspace


router = APIRouter(tags=["workspace-members"])


# Get settings instance
settings = get_settings()

async def send_role_changed_notification(
    workspace_id: str,
    workspace_name: str,
    member_email: str,
    member_user_id: str,
    member_name: str,
    old_role_name: str,
    new_role_name: str,
    changed_by_name: str
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
                member_name=member_name,
                old_role_name=old_role_name,
                new_role_name=new_role_name,
                changed_by_name=changed_by_name,
                frontend_url=frontend_url
            )

            logger.info(f"Sent role changed notification to {member_email}")
    except Exception as e:
        logger.error(f"Failed to send role changed notification: {str(e)}", exc_info=True)


async def send_member_removed_notification(
    workspace_id: str,
    workspace_name: str,
    member_email: str,
    member_user_id: str,
    member_name: str,
    removed_by_name: str,
    reason: str = None
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
                removed_by_name=removed_by_name,
                reason=reason,
                frontend_url=frontend_url
            )

            logger.info(f"Sent member removed notification to {member_email}")
    except Exception as e:
        logger.error(f"Failed to send member removed notification: {str(e)}", exc_info=True)


def _serialize_member(member: WorkspaceMembers, user: Users, role: Role = None) -> Dict[str, Any]:
    """Transform member + user join row into API response structure."""
    # Construct full name from first_name and last_name, fallback to display_name or email
    full_name = user.full_name
    if not full_name:
        full_name = user.display_name or user.email

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
            "id": str(role.id),
            "name": role.name,
            "display_name": role.display_name,
        } if role else None,
        "user": {
            "id": str(user.id),
            "name": full_name,  # Frontend expects "name" field
            "email": user.email,
            "avatar": user.avatar_url,  # Include avatar URL
            "display_name": user.display_name,  # Keep for backward compatibility
            "is_verified": getattr(user, "email_verified", False),
        },
    }


@router.get(
    "/{workspace_id}/members",
    summary="List workspace members",
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
    workspace, _membership = await resolve_and_verify_workspace(
        db, workspace_id, UUID(user_id)
    )

    # Get members with user details via service
    member_service = MemberService(db)
    rows = await member_service.get_workspace_members_with_users(workspace.id)

    members = [_serialize_member(member, user, role) for member, user, role in rows]

    return success(
        data={"members": members, "total_count": len(members)},
        request=request,
        message=f"Retrieved {len(members)} member(s)",
    )


@router.post(
    "/{workspace_id}/members",
    status_code=status.HTTP_201_CREATED,
    summary="Add member to workspace",
)
@db_transaction_handler("add workspace member", auto_commit=True)
@require_permissions("member.invite", workspace_scoped=True)
async def add_workspace_member(
    workspace_id: str,
    payload: AddWorkspaceMemberRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Add a user (by email) to the workspace."""
    user_id = user.get("identity")
    await verify_current_user(db, user_id)
    workspace, _membership = await resolve_and_verify_workspace(
        db, workspace_id, UUID(user_id)
    )

    # Get user by email via UserService
    user_service = UserService(db)
    invited_user = await user_service.get_user_by_email_or_404(payload.email)

    # Add member via MemberService
    member_service = MemberService(db)
    new_member = await member_service.add_member(
        workspace_id=workspace.id,
        user_id=invited_user.id,
    )

    logger.info(
        "User invited to workspace",
        extra={
            "workspace_id": str(workspace.id),
            "invited_user_id": str(invited_user.id),
            "invited_email": invited_user.email,
            "invited_by": user_id,
        },
    )

    return created(
        data={"member": _serialize_member(new_member, invited_user)},
        request=request,
        message=f"User {invited_user.email} added to workspace",
    )


@router.delete(
    "/{workspace_id}/members/{member_id}",
    summary="Remove workspace member",
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
    workspace, _membership = await resolve_and_verify_workspace(
        db, workspace_id, UUID(user_id)
    )

    # Get member with user details via service
    member_service = MemberService(db)
    member, member_user = await member_service.get_member_with_user(
        UUID(member_id), workspace.id
    )

    # Validate member can be removed
    if member.is_default:
        raise RextValidationException(
            message="Cannot remove workspace owner",
            field_errors={
                "member_id": ["This member is the workspace owner and cannot be removed"]
            },
            error_code=ErrorCode.VALIDATION_ERROR,
            error_severity=ErrorSeverity.ERROR,
        )

    # Get current user details for notification
    user_service = UserService(db)
    current_user_obj = await user_service.get_user_by_id(UUID(user_id))

    # Remove member via service
    await member_service.remove_member(workspace_id=workspace.id, user_id=member.user_id)

    # also remove the invite if exists
    await member_service.remove_invitation_if_exists(
        workspace_id=workspace.id,
        email=member_user.email
    )

    #  also remove the user roles assigned in the workspace
    await member_service.remove_user_roles_in_workspace(
        workspace_id=workspace.id,
        user_id=member.user_id,
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
            removed_by_name=current_user_obj.full_name if current_user_obj else "Admin"
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
    workspace, _membership = await resolve_and_verify_workspace(
        db, workspace_id, UUID(user_id)
    )

    # Update member role via service
    member_service = MemberService(db)
    member, member_user, new_role, old_role = await member_service.update_member_role(
        workspace_id=workspace.id,
        member_id=UUID(member_id),
        new_role_id=UUID(payload.role_id),
        assigned_by_user_id=UUID(user_id)
    )
    # Capture the previous role ID for logging/response (may be None)
    previous_role_id = old_role.id if old_role else None

    # Get current user details for notification
    user_service = UserService(db)
    current_user_obj = await user_service.get_user_by_id(UUID(user_id))

    # Send role changed notification to the member
    if member_user:
        background_tasks.add_task(
            send_role_changed_notification,
            workspace_id=str(workspace.id),
            workspace_name=workspace.name,
            member_email=member_user.email,
            member_user_id=str(member_user.id),
            member_name=member_user.full_name or member_user.display_name or member_user.email,
            old_role_name=old_role.display_name if old_role else "Member",
            new_role_name=new_role.display_name,
            changed_by_name=current_user_obj.full_name if current_user_obj else "Admin"
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
