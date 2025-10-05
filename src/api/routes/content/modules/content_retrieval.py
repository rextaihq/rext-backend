from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, desc, select
from typing import Optional
from uuid import UUID

from src.utils.logger import logger
from src.utils.response_utils import success, error
from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.middleware.exceptions import ResourceNotFoundException
from src.api.models.content_models import Content
from .helpers import verify_workspace_access, _build_content_response


router = APIRouter()


# -------------------------
# List Content for Workspace
# -------------------------
@router.get("/")
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

    # Verify access
    workspace = await verify_workspace_access(db, workspace_id, user_id)

    try:
        # Build query
        query = select(Content).where(
            Content.workspace_id == workspace.id,
            Content.deleted_at == None
        )

        # Filter by status if provided
        if status:
            query = query.where(Content.status == status)

        # Get total count
        count_query = select(func.count()).select_from(Content).where(
            Content.workspace_id == workspace.id,
            Content.deleted_at == None
        )
        if status:
            count_query = count_query.where(Content.status == status)

        count_result = await db.execute(count_query)
        total_count = count_result.scalar()

        # Apply pagination and ordering
        query = query.order_by(desc(Content.created_at)).offset(offset).limit(limit)
        result = await db.execute(query)
        content_items = result.scalars().all()

        # Build response
        content_list = [
            _build_content_response(content, include_metadata, include_seo)
            for content in content_items
        ]

        logger.info(f"Listed {len(content_list)} content items for workspace {workspace_id}")

        return success(
            data={
                "content": content_list,
                "total_count": total_count,
                "workspace_id": str(workspace.id),
                "limit": limit,
                "offset": offset
            },
            request=request,
            message=f"Retrieved {len(content_list)} content items"
        )

    except Exception as e:
        logger.error(f"Error listing content for workspace {workspace_id}: {str(e)}")
        return error(
            message="Failed to retrieve content list",
            request=request,
            status_code=500
        )


# -------------------------
# Get Single Content by ID
# -------------------------
@router.get("/{content_id}")
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

    # Verify workspace access
    workspace = await verify_workspace_access(db, workspace_id, user_id)

    try:
        # Get content
        result = await db.execute(
            select(Content).where(
                Content.id == content_id,
                Content.workspace_id == workspace.id,
                Content.deleted_at == None
            )
        )
        content = result.scalar_one_or_none()

        if not content:
            raise ResourceNotFoundException(
                resource_type="Content",
                resource_id=str(content_id)
            )

        content_data = _build_content_response(content, include_metadata, include_seo)

        logger.info(f"Retrieved content {content_id} from workspace {workspace_id}")

        return success(
            data={"content": content_data},
            request=request,
            message="Content retrieved successfully"
        )

    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving content {content_id}: {str(e)}")
        return error(
            message="Failed to retrieve content",
            request=request,
            status_code=500
        )
