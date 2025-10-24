"""
Role CRUD operations module.

Routes handle HTTP concerns and delegate business logic to RoleService.
"""

from fastapi import APIRouter, Depends, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.schema.role_schema import RoleCreate, RoleUpdate
from src.services.role_service import RoleService
from src.utils.response_utils import success, created
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.logger import logger
from .helpers import check_role_permission


router = APIRouter()


@router.get("/", response_model=dict)
@db_transaction_handler("list roles", auto_commit=False)
async def list_roles(
    request: Request,
    include_permissions: bool = Query(False, description="Include permissions for each role"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List all roles.

    Requires: role.read permission OR admin role

    Query Parameters:
    - include_permissions: If true, include permissions for each role

    Returns:
    - List of roles sorted by hierarchy_level (descending)
    """
    # Check permission
    user_id = current_user.get("identity")
    await check_role_permission(db, user_id, "role.read")

    service = RoleService(db)
    roles = await service.get_role_hierarchy()

    # Format response
    if include_permissions:
        roles_data = []
        for role in roles:
            role_data = await service.get_role_with_permissions(role.id)
            roles_data.append(role_data)
    else:
        roles_data = [role.to_dict() for role in roles]

    return {
        "data": {"roles": roles_data, "count": len(roles_data)},
        "message": f"Retrieved {len(roles_data)} roles"
    }


@router.get("/{role_id}", response_model=dict)
@require_permissions(["role.read"])
@db_transaction_handler("get role", auto_commit=False)
async def get_role(
    request: Request,
    role_id: str,
    include_permissions: bool = Query(False, description="Include permissions"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get a specific role by ID.

    Requires: role.read permission OR admin role

    Parameters:
    - role_id: UUID of the role

    Query Parameters:
    - include_permissions: If true, include permissions

    Returns:
    - Role details with optional permissions
    """
    # Check permission
    user_id = current_user.get("identity")
    await check_role_permission(db, user_id, "role.read")

    service = RoleService(db)

    if include_permissions:
        role_data = await service.get_role_with_permissions(role_id)
    else:
        from uuid import UUID
        role = await service._get_role_or_404(UUID(role_id))
        role_data = role.to_dict()

    return {
        "data": {"role": role_data},
        "message": "Role retrieved successfully"
    }


@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
@db_transaction_handler("create role", auto_commit=True)
@require_permissions("role.create", workspace_scoped=False)
async def create_role(
    request: Request,
    role_data: RoleCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new role.

    Requires: role.create permission OR admin role

    Request Body:
    - name: Unique role name (lowercase, no spaces)
    - display_name: Human-readable name
    - description: Optional description
    - hierarchy_level: 0-100 (default: 1)
    - is_system_role: Boolean (default: false)

    Returns:
    - Created role details
    """
    # Check permission
    user_id = current_user.get("identity")
    await check_role_permission(db, user_id, "role.create")

    service = RoleService(db)

    new_role = await service.create_role(
        name=role_data.name,
        display_name=role_data.display_name,
        description=role_data.description,
        hierarchy_level=role_data.hierarchy_level,
        is_system_role=role_data.is_system_role
    )

    return {
        "data": {"role": new_role.to_dict()},
        "message": f"Role '{new_role.display_name}' created successfully"
    }


@router.put("/{role_id}", response_model=dict)
@db_transaction_handler("update role", auto_commit=True)
@require_permissions("role.update", workspace_scoped=False)
async def update_role(
    request: Request,
    role_id: str,
    role_data: RoleUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Update an existing role.

    Requires: role.update permission OR admin role

    Parameters:
    - role_id: UUID of the role to update

    Request Body:
    - display_name: Optional new display name
    - description: Optional new description
    - hierarchy_level: Optional new hierarchy level (0-100)

    Note:
    - Cannot update system roles (is_system_role=true)
    - Cannot change role name (immutable)

    Returns:
    - Updated role details
    """
    # Check permission
    user_id = current_user.get("identity")
    await check_role_permission(db, user_id, "role.update")

    service = RoleService(db)
    from uuid import UUID

    updated_role = await service.update_role(
        role_id=UUID(role_id),
        display_name=role_data.display_name,
        description=role_data.description,
        hierarchy_level=role_data.hierarchy_level
    )

    return {
        "data": {"role": updated_role.to_dict()},
        "message": f"Role '{updated_role.display_name}' updated successfully"
    }


@router.delete("/{role_id}", response_model=dict)
@db_transaction_handler("delete role", auto_commit=True)
@require_permissions("role.delete", workspace_scoped=False)
async def delete_role(
    request: Request,
    role_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a role.

    Requires: role.delete permission OR admin role

    Parameters:
    - role_id: UUID of the role to delete

    Restrictions:
    - Cannot delete system roles (is_system_role=true)
    - Cannot delete roles assigned to users

    Returns:
    - Success message
    """
    # Check permission
    user_id = current_user.get("identity")
    await check_role_permission(db, user_id, "role.delete")

    service = RoleService(db)
    from uuid import UUID

    # Get role name before deletion
    role = await service._get_role_or_404(UUID(role_id))
    role_name = role.display_name

    await service.delete_role(role_id=UUID(role_id))

    return {
        "data": {"role_id": role_id},
        "message": f"Role '{role_name}' deleted successfully"
    }
