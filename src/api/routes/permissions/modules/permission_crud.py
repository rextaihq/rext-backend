from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.schema.permission_schema import PermissionCreate, PermissionUpdate
from src.api.security.dependencies import get_current_user
from src.services.permission_service import PermissionService
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.api.middleware.rate_limiter import permission_management_rate_limit
from src.utils.response_utils import success, created
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.response.rbac_responses import (
    PermissionListData,
    PermissionItemSchema,
    DeletePermissionData,
)


router = APIRouter()


@router.get("/", response_model=SuccessResponse[PermissionListData])
@require_permissions("permission.read", workspace_scoped=False)
@db_transaction_handler("list permissions", auto_commit=False)
async def list_permissions(
    request: Request,
    resource: str | None = Query(None, description="Filter by resource type"),
    include_roles: bool = Query(False, description="Include roles for each permission"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List all system permissions with pagination.

    Requires: permission.read permission

    Query Parameters:
        resource: Filter by resource type (e.g., 'user', 'workspace', 'content')
        include_roles: Include roles that have each permission
        page: Page number (default 1)
        per_page: Items per page (default 50, max 100)

    Returns:
        Paginated list of permissions with optional role information

    Security: Only admin and super_admin roles have permission.read by default
    """
    service = PermissionService(db)
    user_id = UUID(str(current_user.get("identity")))
    result = await service.list_permissions(
        user_id=user_id, resource=resource, include_roles=include_roles,
        page=page, per_page=per_page,
    )
    # Service returns {"data": {...}, "message": "..."} — extract just the data payload
    return success(
        data=result["data"],
        message=result.get("message")
    )


@router.get("/{permission_id}", response_model=SuccessResponse[PermissionItemSchema])
@require_permissions("permission.read", workspace_scoped=False)
@db_transaction_handler("get permission", auto_commit=False)
async def get_permission(
    request: Request,
    permission_id: str,
    include_roles: bool = Query(False, description="Include roles"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    service = PermissionService(db)
    user_id = UUID(str(current_user.get("identity")))
    result = await service.get_permission(
        user_id=user_id,
        permission_id=UUID(permission_id),
        include_roles=include_roles,
    )
    # result["data"] = {"permission": {...}}
    # Unwrap one level so schema matches PermissionItemSchema directly
    return success(
        data=result["data"]["permission"],
        message=result.get("message")
    )


@router.post("/", response_model=SuccessResponse[PermissionItemSchema], status_code=status.HTTP_201_CREATED)
@db_transaction_handler("create permission", auto_commit=True)
@require_permissions("permission.create", workspace_scoped=False)
async def create_permission(
    request: Request,
    permission_data: PermissionCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(permission_management_rate_limit())
):
    """
    Create a new permission.

    **Phase 3, Task HIGH-4: Rate Limiting**
    Rate limit: 30 requests per minute per user
    """
    service = PermissionService(db)
    user_id = UUID(str(current_user.get("identity")))
    result = await service.create_permission(user_id=user_id, payload=permission_data)
    return created(
        data=result["data"]["permission"],
        request=request,
        message=result.get("message")
    )


@router.put("/{permission_id}", response_model=SuccessResponse[PermissionItemSchema])
@db_transaction_handler("update permission", auto_commit=True)
@require_permissions("permission.update", workspace_scoped=False)
async def update_permission(
    request: Request,
    permission_id: str,
    permission_data: PermissionUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(permission_management_rate_limit())
):
    """
    Update an existing permission.

    **Phase 3, Task HIGH-4: Rate Limiting**
    Rate limit: 30 requests per minute per user
    """
    service = PermissionService(db)
    user_id = UUID(str(current_user.get("identity")))
    result = await service.update_permission(
        user_id=user_id,
        permission_id=UUID(permission_id),
        payload=permission_data,
    )
    return success(
        data=result["data"]["permission"],
        message=result.get("message")
    )


@router.delete("/{permission_id}", response_model=SuccessResponse[DeletePermissionData])
@db_transaction_handler("delete permission", auto_commit=True)
@require_permissions("permission.delete", workspace_scoped=False)
async def delete_permission(
    request: Request,
    permission_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(permission_management_rate_limit())
):
    """
    Delete a permission.

    **Phase 3, Task HIGH-4: Rate Limiting**
    Rate limit: 30 requests per minute per user
    """
    service = PermissionService(db)
    user_id = UUID(str(current_user.get("identity")))
    result = await service.delete_permission(
        user_id=user_id,
        permission_id=UUID(permission_id),
    )
    return success(
        data=result["data"],
        message=result.get("message")
    )
