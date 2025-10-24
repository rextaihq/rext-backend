from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID

from src.utils.response_utils import success, error
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.services.content_service import ContentService
from src.utils.workspace_utils import resolve_and_verify_workspace


router = APIRouter()


# -------------------------
# List Content for Workspace
# -------------------------
@router.get("/")
@db_transaction_handler("list content", auto_commit=False)
async def list_content(
    request: Request,
    workspace_id: str,
    status: Optional[str] = Query(None, description="Filter by status"),
    include_metadata: bool = Query(False, description="Include metadata in response"),
    include_seo: bool = Query(False, description="Include SEO data in response"),
    limit: int = Query(100, le=500, description="Maximum number of items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    List all content for a workspace with optional filtering and pagination.

    Args:
        workspace_id: Workspace UUID or slug (query parameter)

    Requires:
        - JWT authentication
        - Workspace membership verification
    """
    user_id = user.get("identity")

    # Verify workspace access and membership in one call
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Use ContentService
    service = ContentService(db)
    result = await service.list_content(
        workspace_id=workspace.id,
        status=status,
        include_metadata=include_metadata,
        include_seo=include_seo,
        limit=limit,
        offset=offset
    )

    # Return raw data - decorator handles success response
    return {
        "content": result["content"],
        "total_count": result["total_count"],
        "workspace_id": str(workspace.id),
        "limit": limit,
        "offset": offset
    }


# -------------------------
# Get Single Content by ID
# -------------------------
@router.get("/{content_id}")
@require_permissions(["content.read"], workspace_scoped=True)
@db_transaction_handler("get content", "Content retrieved successfully", auto_commit=False)
async def get_content(
    content_id: UUID,
    request: Request,
    workspace_id: str,
    include_metadata: bool = Query(True, description="Include metadata in response"),
    include_seo: bool = Query(True, description="Include SEO data in response"),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """Get a single content item by ID"""
    user_id = user.get("identity")

    # Verify workspace access and membership in one call
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Use ContentService
    service = ContentService(db)
    content_data = await service.get_content(
        content_id=content_id,
        workspace_id=workspace.id,
        include_metadata=include_metadata,
        include_seo=include_seo
    )

    # Return raw data - decorator handles success response
    return {"content": content_data}
