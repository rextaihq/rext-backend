from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    WrextValidationException,
)
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.schema.workspace_schema import (
    AddWorkspaceMemberRequest,
    ChangeMemberRoleRequest,
)
from src.api.security.dependencies import get_current_user
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.services.member_service import MemberService
from src.utils.auth_utils import verify_current_user
from src.utils.logger import logger
from src.utils.response_utils import created, success
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.workspace_utils import resolve_and_verify_workspace


router = APIRouter(tags=["workspace-members"])


def _serialize_member(member: WorkspaceMembers, user: Users) -> Dict[str, Any]:
    """Transform member + user join row into API response structure."""
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
        "user": {
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "is_verified": getattr(user, "email_verified", False),
        },
    }


@router.get(
    "/{workspace_id}/members",
    summary="List workspace members",
)
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

    query = (
        select(WorkspaceMembers, Users)
        .join(Users, Users.id == WorkspaceMembers.user_id)
        .where(WorkspaceMembers.workspace_id == workspace.id)
        .order_by(WorkspaceMembers.joined_at.asc())
    )
    result = await db.execute(query)
    rows: List[tuple[WorkspaceMembers, Users]] = result.all()

    members = [_serialize_member(member, user) for member, user in rows]

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

    result = await db.execute(
        select(Users).where(
            Users.email == payload.email.lower(),
            Users.deleted_at.is_(None),
        )
    )
    invited_user = result.scalar_one_or_none()
    if not invited_user:
        raise ResourceNotFoundException(
            resource_type="user",
            resource_id=payload.email,
        )

    service = MemberService(db)
    new_member = await service.add_member(
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
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Remove a member from the workspace."""
    user_id = user.get("identity")
    await verify_current_user(db, user_id)
    workspace, _membership = await resolve_and_verify_workspace(
        db, workspace_id, UUID(user_id)
    )

    result = await db.execute(
        select(WorkspaceMembers).where(
            WorkspaceMembers.id == UUID(member_id),
            WorkspaceMembers.workspace_id == workspace.id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise ResourceNotFoundException(
            resource_type="member",
            resource_id=member_id,
        )

    if member.is_default:
        raise WrextValidationException(
            message="Cannot remove workspace owner",
            field_errors={
                "member_id": ["This member is the workspace owner and cannot be removed"]
            },
            error_code=ErrorCode.VALIDATION_ERROR,
            error_severity=ErrorSeverity.ERROR,
        )

    service = MemberService(db)
    await service.remove_member(workspace_id=workspace.id, user_id=member.user_id)

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
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Assign a new role to the given member."""
    user_id = user.get("identity")
    await verify_current_user(db, user_id)
    workspace, _membership = await resolve_and_verify_workspace(
        db, workspace_id, UUID(user_id)
    )

    result = await db.execute(
        select(WorkspaceMembers).where(
            WorkspaceMembers.id == UUID(member_id),
            WorkspaceMembers.workspace_id == workspace.id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise ResourceNotFoundException(
            resource_type="member",
            resource_id=member_id,
        )

    if member.is_default:
        raise WrextValidationException(
            message="Cannot change role of workspace owner",
            field_errors={"member_id": ["Workspace owner role is immutable"]},
            error_code=ErrorCode.VALIDATION_ERROR,
            error_severity=ErrorSeverity.ERROR,
        )

    result = await db.execute(select(Role).where(Role.id == UUID(payload.role_id)))
    new_role = result.scalar_one_or_none()
    if not new_role:
        raise ResourceNotFoundException(
            resource_type="role",
            resource_id=payload.role_id,
        )

    result = await db.execute(
        select(UserRole).where(
            UserRole.user_id == member.user_id,
            UserRole.workspace_id == workspace.id,
        )
    )
    user_role = result.scalar_one_or_none()

    previous_role_id = getattr(user_role, "role_id", None)
    timestamp = datetime.now(timezone.utc)
    if user_role:
        user_role.role_id = UUID(payload.role_id)
        user_role.assigned_by_user_id = UUID(user_id)
        user_role.assigned_at = timestamp
    else:
        db.add(
            UserRole(
                user_id=member.user_id,
                workspace_id=workspace.id,
                role_id=UUID(payload.role_id),
                assigned_by_user_id=UUID(user_id),
                assigned_at=timestamp,
                is_primary=False,
            )
        )

    await db.flush()

    logger.info(
        "Workspace member role updated",
        extra={
            "workspace_id": str(workspace.id),
            "member_id": member_id,
            "updated_by": user_id,
            "old_role_id": str(previous_role_id) if previous_role_id else None,
            "new_role_id": payload.role_id,
        },
    )

    return success(
        data={
            "member": {
                "id": str(member.id),
                "workspace_id": str(workspace.id),
                "user_id": str(member.user_id),
                "role_id": payload.role_id,
                "updated_at": timestamp.isoformat(),
            }
        },
        request=request,
        message=f"Role updated to {new_role.display_name}",
    )
