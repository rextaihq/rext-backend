from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from src.utils.logger import logger
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.schema.content_schema import ContentCreate, ContentUpdate, ContentResponse
from src.utils.workspace_utils import resolve_and_verify_workspace
from src.services.content_service import ContentService

router = APIRouter()


# -------------------------
# Create New Content
# -------------------------
@router.post("/", response_model=ContentResponse)
@db_transaction_handler("create content", "Content created successfully")
@require_permissions("content.create", workspace_scoped=True)
async def create_content(
    data: ContentCreate,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Create new content in a workspace.
    
    This is a simple save operation. For AI generation, 
    use the generation-specific endpoints.
    """
    user_id = user.get("identity")
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    service = ContentService(db)
    content = await service.create_content(
        workspace_id=workspace.id,
        user_id=UUID(user_id),
        data=data
    )

    return content.to_dict()


# -------------------------
# Get Content
# -------------------------
@router.get("/{content_id}", response_model=ContentResponse)
@require_permissions("content.read", workspace_scoped=True)
async def get_content(
    content_id: UUID,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """Get single content item"""
    user_id = user.get("identity")
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    service = ContentService(db)
    content_data = await service.get_content(content_id, workspace.id)
    return content_data


# -------------------------
# Update Content
# -------------------------
@router.put("/{content_id}", response_model=ContentResponse)
@db_transaction_handler("update content", "Content updated successfully")
@require_permissions("content.update", workspace_scoped=True)
async def update_content(
    content_id: UUID,
    data: ContentUpdate,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """Update existing content"""
    user_id = user.get("identity")
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    service = ContentService(db)
    content = await service.update_content(
        content_id=content_id,
        workspace_id=workspace.id,
        user_id=UUID(user_id),
        data=data
    )

    return content.to_dict()


# -------------------------
# Delete Content (Soft Delete)
# -------------------------
@router.delete("/{content_id}")
@db_transaction_handler("delete content", "Content deleted successfully")
@require_permissions("content.delete", workspace_scoped=True)
async def delete_content(
    content_id: UUID,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """Soft delete content"""
    user_id = user.get("identity")
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    service = ContentService(db)
    await service.delete_content(
        content_id=content_id,
        workspace_id=workspace.id
    )

    return {"content_id": str(content_id)}
