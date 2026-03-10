from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime, timezone
from typing import List,Optional

from src.utils.logger import logger
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.schema.content_schema import (
    ContentCreate, 
    ContentUpdate, 
    ContentResponse,
    PublishToSiteRequest,
    PublishResponse,
    PublishToSitesResponse,
    ContentSEODataSchema
)
from src.utils.workspace_utils import resolve_and_verify_workspace
from src.services.content_service import ContentService
from src.web.wordpress import WordPressPublisher
from src.api.models.content_models import Content
from src.api.models.workspace_models.workspace_integration import WorkspaceIntegration

router = APIRouter()


# -------------------------
# 1. Save Only (New Content)
# -------------------------
@router.post("/save", response_model=ContentResponse)
@db_transaction_handler("save content", "Content saved successfully")
@require_permissions("content.create", workspace_scoped=True)
async def save_content(
    data: ContentCreate,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Save content as a draft WITHOUT publishing it to any WordPress sites.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Save content via service
    service = ContentService(db)
    
    # Ensure status is 'draft' for this endpoint
    data.status = "draft"
    
    content = await service.create_content(
        workspace_id=workspace.id,
        user_id=UUID(user_id),
        data=data
    )
    
    return content.to_dict(include_relationships=["seo_data"])


# -------------------------
# 2. Save & Publish (New Content)
# -------------------------
@router.post("/publish", response_model=dict)
@db_transaction_handler("publish content", "Content published successfully")
@require_permissions("content.create", workspace_scoped=True)
async def save_and_publish(
    data: ContentCreate,
    request: Request,
    workspace_id: str,
    publish_status: str = "publish",
    site_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Save content AND publish to active WordPress site(s).
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Save content first
    service = ContentService(db)
    content = await service.create_content(
        workspace_id=workspace.id,
        user_id=UUID(user_id),
        data=data
    )
    
    # Publish to active sites via service
    results = await service.publish_to_sites(
        content=content,
        workspace_id=workspace.id,
        site_id=site_id,
        publish_status=publish_status
    )
    
    successful_results = [r for r in results if r.success]
    
    return {
        "content": content.to_dict(include_relationships=["seo_data"]),
        "publish_results": {
            "total_sites": len(results),
            "successful": len(successful_results),
            "failed": len(results) - len(successful_results),
            "results": [r.model_dump() for r in results],
            "all_failed": len(successful_results) == 0
        }
    }


# -------------------------
# 3. Publish Existing Content
# -------------------------
@router.post("/{content_id}/publish")
@db_transaction_handler("publish existing content", "Content published successfully")
@require_permissions("content.create", workspace_scoped=True)
async def publish_existing_content(
    content_id: UUID,
    request: Request,
    workspace_id: str,
    publish_data: PublishToSiteRequest = None,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Publish existing content to all active WordPress sites.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))
    
    # Get existing content
    service = ContentService(db)
    content = await service._get_content_or_404(content_id, workspace.id, include_seo=True)
    
    # Get publish status and site_id from request or defaults
    status = "publish"
    site_id = None
    if publish_data:
        if publish_data.status:
            status = publish_data.status
        if publish_data.site_id:
            site_id = publish_data.site_id
    
    # Publish to active sites via service
    results = await service.publish_to_sites(
        content=content,
        workspace_id=workspace.id,
        site_id=site_id,
        publish_status=status
    )
    
    successful_results = [r for r in results if r.success]
    
    return {
        "content": content.to_dict(),
        "publish_results": {
            "content_id": str(content_id),
            "total_sites": len(results),
            "successful": len(successful_results),
            "failed": len(results) - len(successful_results),
            "results": [r.model_dump() for r in results],
            "all_failed": len(successful_results) == 0
        }
    }


# -------------------------
# Retry Content Generation/Publishing
# -------------------------
@router.post("/{content_id}/retry")
@db_transaction_handler("retry content", "Retry initiated")
@require_permissions("content.create", workspace_scoped=True)
async def retry_content(
    content_id: UUID,
    workspace_id: str,
    site_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Retry a failed content operation.
    
    If site_id is provided, retry specifically for that site.
    If it was a publishing failure, attempts to re-publish.
    If it was a generation failure, transitions back to draft/generating.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))
    
    service = ContentService(db)
    content = await service._get_content_or_404(content_id, workspace.id, include_seo=True)
    
    if content.status != "failed":
        raise HTTPException(status_code=400, detail=f"Only failed content can be retried. Current status: {content.status}")
    
    # If we have body content but no WP post ID, it likely failed at publishing
    # (Or if site_id is specified, we assume we want to retry publishing for that site)
    if (content.body_markdown and not content.wordpress_post_id) or site_id:
        logger.info(f"Retrying publishing for content {content_id} (site: {site_id or 'all'})")
        results = await service.publish_to_sites(
            content=content,
            workspace_id=workspace.id,
            site_id=site_id
        )
        successful_results = [r for r in results if r.success]
        return {
            "content_id": str(content_id),
            "status": content.status,
            "retry_type": "publishing",
            "successful_sites": len(successful_results),
            "total_sites": len(results),
            "results": [r.model_dump() for r in results]
        }
    
    # Otherwise, it might have failed at generation or some other step
    # Reset to draft for now so it can be manually re-triggered or edited
    content.status = "draft"
    content.updated_at = datetime.now(timezone.utc)
    await db.flush()
    
    return {
        "content_id": str(content_id),
        "status": content.status,
        "retry_type": "unspecified_reset_to_draft"
    }

# -------------------------
# 4. Update Content
# -------------------------
@router.patch("/{content_id}", response_model=ContentResponse)
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
    """
    Update existing content.
    
    Allows partial updates of content fields, SEO data, and media links.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Check for duplicate title if title is being updated
    if data.title:
        title_query = select(Content).where(
            Content.workspace_id == workspace.id,
            Content.title == data.title,
            Content.deleted_at == None,
            Content.id != content_id
        )
        existing_result = await db.execute(title_query)
        if existing_result.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"Content with title '{data.title}' already exists in this workspace."
            )

    service = ContentService(db)
    content = await service.update_content(
        content_id=content_id,
        workspace_id=workspace.id,
        user_id=UUID(user_id),
        data=data
    )

    return content.to_dict(include_relationships=["seo_data"])


# -------------------------
# 5. Delete Content
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
    """
    Soft-delete content.
    
    Sets deleted_at timestamp instead of permanent removal.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    service = ContentService(db)
    await service.delete_content(
        content_id=content_id,
        workspace_id=workspace.id
    )

    return {"deleted_id": str(content_id)}