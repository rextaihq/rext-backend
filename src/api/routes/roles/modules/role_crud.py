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
from src.api.middleware.rate_limiter import role_management_rate_limit
from .helpers import check_role_permission


router = APIRouter()


@router.get("/", response_model=dict)
@require_permissions("role.read")
@db_transaction_handler("list roles", auto_commit=False)
async def list_roles(
    request: Request,
    include_permissions: bool = Query(False, description="Include permissions for each role"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List all roles with pagination.

    **Security: Requires role.read permission**

    This endpoint lists all system and workspace roles. Access is restricted to users
    with the role.read permission (admin and super_admin roles by default).

    Query Parameters:
    - include_permissions: If true, include permissions for each role
    - page: Page number (default 1)
    - per_page: Items per page (default 50, max 100)

    Returns:
    - Paginated list of roles sorted by hierarchy_level (descending)

    Raises:
        HTTPException: 401 if not authenticated, 403 if insufficient permissions
    """

    service = RoleService(db)
    result = await service.get_role_hierarchy(page=page, per_page=per_page)

    # Format response
    if include_permissions:
        roles_data = []
        for role in result["roles"]:
            role_data = await service.get_role_with_permissions(role.id)
            roles_data.append(role_data)
    else:
        roles_data = [role.to_dict() for role in result["roles"]]

    return {
        "data": {"roles": roles_data, "count": len(roles_data), "pagination": result["pagination"]},
        "message": f"Retrieved {len(roles_data)} roles"
    }


@router.get("/{role_id}", response_model=dict)
@require_permissions("role.read")
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
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(role_management_rate_limit())
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

    **Phase 2, Task HIGH-3: Audit Logging**
    This endpoint logs role creation to the audit table for compliance tracking.

    **Phase 3, Task HIGH-4: Rate Limiting**
    Rate limit: 20 requests per minute per user
    """
    # Check permission
    user_id = current_user.get("identity")
    await check_role_permission(db, user_id, "role.create")

    service = RoleService(db)

    # Create the role
    new_role = await service.create_role(
        name=role_data.name,
        display_name=role_data.display_name,
        description=role_data.description,
        hierarchy_level=role_data.hierarchy_level,
        is_system_role=role_data.is_system_role
    )

    # Prepare values for audit log
    new_values = {
        "name": new_role.name,
        "display_name": new_role.display_name,
        "description": new_role.description,
        "hierarchy_level": new_role.hierarchy_level,
        "is_system_role": new_role.is_system_role
    }

    # Create audit log (HIGH-3: Role Creation Audit Logging)
    from src.utils.audit_helper import create_audit_log_async
    from uuid import UUID
    await create_audit_log_async(
        db=db,
        user_id=UUID(user_id),
        action="role.create",
        resource_type="role",
        resource_id=str(new_role.id),
        old_values=None,
        new_values=new_values,
        request=request,
        metadata={
            "created_by_email": current_user.get("email"),
            "created_by_username": current_user.get("username"),
            "role_name": new_role.name,
            "role_type": "system" if new_role.is_system_role else "custom"
        }
    )

    logger.info(
        f"Role created and logged to audit: {new_role.display_name}",
        extra={
            "role_id": str(new_role.id),
            "created_by": user_id,
            "role_name": new_role.name
        }
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
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(role_management_rate_limit())
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

    **Phase 2, Task HIGH-3: Audit Logging**
    This endpoint logs role updates to the audit table for compliance tracking.

    **Phase 3, Task HIGH-4: Rate Limiting**
    Rate limit: 20 requests per minute per user
    """
    # Check permission
    user_id = current_user.get("identity")
    await check_role_permission(db, user_id, "role.update")

    service = RoleService(db)
    from uuid import UUID

    # Get role details before update for audit log
    role_before = await service._get_role_or_404(UUID(role_id))
    old_values = {
        "display_name": role_before.display_name,
        "description": role_before.description,
        "hierarchy_level": role_before.hierarchy_level
    }

    # Update the role
    updated_role = await service.update_role(
        role_id=UUID(role_id),
        display_name=role_data.display_name,
        description=role_data.description,
        hierarchy_level=role_data.hierarchy_level
    )

    # Prepare new values for audit log
    new_values = {
        "display_name": updated_role.display_name,
        "description": updated_role.description,
        "hierarchy_level": updated_role.hierarchy_level
    }

    # Create audit log (HIGH-3: Role Update Audit Logging)
    from src.utils.audit_helper import create_audit_log_async
    await create_audit_log_async(
        db=db,
        user_id=UUID(user_id),
        action="role.update",
        resource_type="role",
        resource_id=role_id,
        old_values=old_values,
        new_values=new_values,
        request=request,
        metadata={
            "updated_by_email": current_user.get("email"),
            "updated_by_username": current_user.get("username"),
            "role_name": updated_role.name,
            "changes": {
                k: {"from": old_values[k], "to": new_values[k]}
                for k in old_values
                if old_values[k] != new_values[k]
            }
        }
    )

    logger.info(
        f"Role updated and logged to audit: {updated_role.display_name}",
        extra={
            "role_id": role_id,
            "updated_by": user_id,
            "role_name": updated_role.name
        }
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
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(role_management_rate_limit())
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

    **Phase 2, Task HIGH-3: Audit Logging**
    This endpoint logs role deletion to the audit table for compliance tracking.

    **Phase 3, Task HIGH-4: Rate Limiting**
    Rate limit: 20 requests per minute per user
    """
    # Check permission
    user_id = current_user.get("identity")
    await check_role_permission(db, user_id, "role.delete")

    service = RoleService(db)
    from uuid import UUID

    # Get role details before deletion for audit log
    role = await service._get_role_or_404(UUID(role_id))
    role_name = role.display_name
    role_details = {
        "name": role.name,
        "display_name": role.display_name,
        "description": role.description,
        "hierarchy_level": role.hierarchy_level,
        "is_system_role": role.is_system_role,
        "created_at": role.created_at.isoformat() if role.created_at else None
    }

    # Delete the role
    await service.delete_role(role_id=UUID(role_id))

    # Create audit log (HIGH-3: Role Deletion Audit Logging)
    from src.utils.audit_helper import create_audit_log_async
    await create_audit_log_async(
        db=db,
        user_id=UUID(user_id),
        action="role.delete",
        resource_type="role",
        resource_id=role_id,
        old_values=role_details,
        new_values=None,
        request=request,
        metadata={
            "deleted_by_email": current_user.get("email"),
            "deleted_by_username": current_user.get("username"),
            "role_name": role_name,
            "role_type": "system" if role_details["is_system_role"] else "custom"
        }
    )

    logger.info(
        f"Role deleted and logged to audit: {role_name}",
        extra={
            "role_id": role_id,
            "deleted_by": user_id,
            "role_name": role_name
        }
    )

    return {
        "data": {"role_id": role_id},
        "message": f"Role '{role_name}' deleted successfully"
    }
