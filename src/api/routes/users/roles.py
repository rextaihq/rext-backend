"""
User Role Assignment API endpoints.

Routes handle HTTP concerns and delegate business logic to RoleService.
"""

from typing import Any, Dict
from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from src.api.database.async_database import get_async_db
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.routes.roles.modules.helpers import check_role_permission
from src.api.security.dependencies import get_current_user
from src.api.schema.user_role_schema import AssignUserRoleRequest
from src.services.role_service import RoleService
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.response.user_role_responses import (
    RoleAssignmentResponse,
    RoleRevokeResponse,
    UserRolesListResponse,
    UserWorkspaceScopeListResponse
)
from src.utils.response_utils import success
from src.utils.logger import logger

router = APIRouter()


@router.post("/{user_id}/roles", response_model=SuccessResponse[RoleAssignmentResponse])
@db_transaction_handler("assign role to user", auto_commit=True)
@require_permissions("user.manage_roles", workspace_scoped=False)
async def assign_role_to_user(
    request: Request,
    user_id: str,
    assignment_data: AssignUserRoleRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Assign a role to a user.
    """
    assigner_id = current_user.get("identity")
    service = RoleService(db)

    # Convert IDs
    target_user_id = UUID(user_id)
    role_id = UUID(assignment_data.role_id)
    workspace_id = UUID(assignment_data.workspace_id) if assignment_data.workspace_id else None

    # Get role for response
    role = await service.get_role_by_id(role_id)

    # Perform assignment
    user_role = await service.assign_role(
        user_id=target_user_id,
        role_id=role_id,
        workspace_id=workspace_id,
        is_primary=assignment_data.is_primary,
        assigned_by_user_id=UUID(assigner_id)
    )

    # Get workspace name if applicable
    workspace_name = None
    if workspace_id:
        ws_result = await db.execute(
            select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)
        )
        workspace = ws_result.scalar_one_or_none()
        workspace_name = workspace.name if workspace else None

    return success(
        data={
            "assignment": user_role.to_dict(),
            "role_name": role.name,
            "role_display_name": role.display_name,
            "workspace_name": workspace_name
        },
        request=request,
        message="Role assigned successfully"
    )


@router.delete("/{user_id}/roles/{role_id}", response_model=SuccessResponse[RoleRevokeResponse])
@db_transaction_handler("revoke role from user", auto_commit=True)
@require_permissions("user.manage_roles", workspace_scoped=False)
async def revoke_user_role(
    request: Request,
    user_id: str,
    role_id: str,
    workspace_id: str = Query(None, description="Workspace ID for workspace-scoped role"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Revoke a role from a user.
    """
    service = RoleService(db)

    # Get role for response before revoking
    role = await service.get_role_by_id(UUID(role_id))

    # Revoke role
    await service.revoke_role(
        user_id=UUID(user_id),
        role_id=UUID(role_id),
        workspace_id=UUID(workspace_id) if workspace_id else None
    )

    return success(
        data={
            "user_id": user_id,
            "role_id": role_id,
            "workspace_id": workspace_id,
            "role_name": role.name
        },
        request=request,
        message="Role revoked successfully"
    )


@router.get("/me/roles", response_model=SuccessResponse[UserRolesListResponse])
@db_transaction_handler("get current user roles", auto_commit=False)
async def get_current_user_roles(
    request: Request,
    workspace_id: str = Query(None, description="Optional workspace UUID filter"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get roles for the current authenticated user.
    """
    user_id = current_user.get("identity")
    service = RoleService(db)

    roles_data = await service.get_user_roles(
        user_id=UUID(user_id),
        workspace_id=UUID(workspace_id) if workspace_id else None
    )

    return success(
        data={
            "user_id": user_id,
            "roles": roles_data,
            "count": len(roles_data)
        },
        request=request,
        message="User roles retrieved successfully"
    )
@router.get("/{user_id}/roles", response_model=SuccessResponse[UserRolesListResponse])
@db_transaction_handler("list user roles", auto_commit=False)
async def list_user_roles(
    request: Request,
    user_id: str,
    workspace_id: str = Query(None, description="Optional workspace UUID filter"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List all roles assigned to a user.
    """
    requester_id = current_user.get("identity")
    is_own_user = requester_id == user_id

    # Non-self requests require user.read permission or admin role
    if not is_own_user:
        await check_role_permission(db, UUID(requester_id), "user.read")

    service = RoleService(db)

    roles_data = await service.get_user_roles(
        user_id=UUID(user_id),
        workspace_id=UUID(workspace_id) if workspace_id else None
    )

    return success(
        data={
            "roles": roles_data,
            "count": len(roles_data)
        },
        request=request,
        message="User roles retrieved successfully"
    )


@router.get(
    "/{user_id}/workspaces",
    response_model=SuccessResponse[UserWorkspaceScopeListResponse],
)
@db_transaction_handler("list user workspaces for role scoping", auto_commit=False)
@require_permissions("user.manage_roles", workspace_scoped=False)
async def list_user_workspaces_for_role_scoping(
    request: Request,
    user_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List the workspaces a user belongs to, for scoping a role assignment.

    GET /user/workspaces only ever answers for the caller, so an admin
    assigning a role on someone else's behalf had no way to discover which
    workspaces were valid scopes — which is why the admin UI could only ever
    send workspace_id = null (a platform-wide role that never shows on a
    workspace's Members page). This endpoint fills that gap.

    Each entry carries the role the user currently holds in that workspace so
    the picker can show what an assignment would replace.
    """
    target_user_id = UUID(user_id)

    result = await db.execute(
        select(
            WorkspaceModel.id,
            WorkspaceModel.name,
            Role.display_name,
        )
        .join(
            WorkspaceMembers,
            WorkspaceMembers.workspace_id == WorkspaceModel.id,
        )
        .outerjoin(
            UserRole,
            and_(
                UserRole.workspace_id == WorkspaceModel.id,
                UserRole.user_id == target_user_id,
            ),
        )
        .outerjoin(Role, Role.id == UserRole.role_id)
        .where(
            WorkspaceMembers.user_id == target_user_id,
            WorkspaceModel.deleted_at.is_(None),
        )
        .order_by(WorkspaceModel.name)
    )

    rows = result.all()
    workspace_map: Dict[str, Dict[str, Any]] = {}
    for ws_id, ws_name, role_display_name in rows:
        ws_id_str = str(ws_id)
        if ws_id_str not in workspace_map:
            workspace_map[ws_id_str] = {
                "workspace_id": ws_id_str,
                "workspace_name": ws_name,
                "roles": [],
            }
        if role_display_name and role_display_name not in workspace_map[ws_id_str]["roles"]:
            workspace_map[ws_id_str]["roles"].append(role_display_name)

    workspaces = [
        {
            "workspace_id": item["workspace_id"],
            "workspace_name": item["workspace_name"],
            "current_role_display_name": ", ".join(item["roles"]) if item["roles"] else None,
        }
        for item in workspace_map.values()
    ]

    return success(
        data={
            "user_id": str(target_user_id),
            "workspaces": workspaces,
            "count": len(workspaces),
        },
        request=request,
        message="User workspaces retrieved successfully"
    )