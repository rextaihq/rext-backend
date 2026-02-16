"""
User Role Assignment API endpoints.

Routes handle HTTP concerns and delegate business logic to RoleService.
"""

from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.schema.user_role_schema import AssignUserRoleRequest
from src.services.role_service import RoleService
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.logger import logger


router = APIRouter()


@router.post("/{user_id}/roles")
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

    Requires: user.manage_roles permission OR admin role

    Parameters:
    - user_id: UUID of the user

    Request Body:
    - role_id: UUID of the role to assign
    - workspace_id: Optional workspace UUID for workspace-scoped role
    - is_primary: Whether this is the primary role

    Returns:
    - Assignment details
    """
    assigner_id = current_user.get("identity")
    service = RoleService(db)

    # Assign role
    user_role = await service.assign_role(
        user_id=UUID(user_id),
        role_id=assignment_data.role_id,
        workspace_id=assignment_data.workspace_id,
        is_primary=assignment_data.is_primary,
        assigned_by_user_id=UUID(assigner_id)
    )

    # Get role details for response
    role = await service.get_role_by_id(assignment_data.role_id)

    # Get workspace name if applicable
    workspace_name = None
    if assignment_data.workspace_id:
        from sqlalchemy import select
        from src.api.models.workspace_models.workspace_model import WorkspaceModel
        ws_result = await db.execute(
            select(WorkspaceModel).where(WorkspaceModel.id == assignment_data.workspace_id)
        )
        workspace = ws_result.scalar_one_or_none()
        workspace_name = workspace.name if workspace else None

    return {
        "assignment": user_role.to_dict(),
        "role_name": role.name,
        "role_display_name": role.display_name,
        "workspace_name": workspace_name
    }


@router.delete("/{user_id}/roles/{role_id}")
@db_transaction_handler("revoke role from user", auto_commit=True)
@require_permissions("user.manage_roles", workspace_scoped=False)
async def revoke_role_from_user(
    request: Request,
    user_id: str,
    role_id: str,
    workspace_id: str = Query(None, description="Optional workspace UUID"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Revoke a role from a user.

    Requires: user.manage_roles permission OR admin role

    Parameters:
    - user_id: UUID of the user
    - role_id: UUID of the role to revoke
    - workspace_id: Optional workspace UUID (query param) to specify which assignment

    Returns:
    - Success message
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

    return {
        "user_id": user_id,
        "role_id": role_id,
        "workspace_id": workspace_id,
        "role_name": role.name
    }


@router.get("/me/roles")
@require_permissions("role.read", workspace_scoped=False)
@db_transaction_handler("get current user roles", auto_commit=False)
async def get_current_user_roles(
    request: Request,
    workspace_id: str = Query(None, description="Optional workspace UUID filter"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get roles for the current authenticated user.
    
    This is a convenience endpoint that doesn't require passing user_id.
    
    Query Parameters:
    - workspace_id: Optional workspace UUID to filter roles
    
    Returns:
    - List of current user's roles with details
    """
    user_id = current_user.get("identity")
    service = RoleService(db)

    roles_data = await service.get_user_roles(
        user_id=UUID(user_id),
        workspace_id=UUID(workspace_id) if workspace_id else None
    )

    return {
        "user_id": user_id,
        "roles": roles_data,
        "count": len(roles_data)
    }
@router.get("/{user_id}/roles")
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

    Authorization:
    - Users can always view their own roles (no permission required).
    - Viewing another user's roles requires 'user.read' permission or admin role.

    Parameters:
    - user_id: UUID of the user whose roles to retrieve
    - workspace_id: Optional workspace UUID to filter roles by workspace

    Returns:
    - List of user's roles with details
    """
    from src.utils.rbac_utils import is_user_admin

    requester_id = current_user.get("identity")
    is_own_user = requester_id == user_id

    # Non-self requests require user.read permission or admin role
    if not is_own_user:
        from src.utils.rbac_utils import check_permission_or_admin
        await check_permission_or_admin(db, UUID(requester_id), "user.read")

    service = RoleService(db)

    roles_data = await service.get_user_roles(
        user_id=UUID(user_id),
        workspace_id=UUID(workspace_id) if workspace_id else None
    )

    return {
        "roles": roles_data,
        "count": len(roles_data)
    }