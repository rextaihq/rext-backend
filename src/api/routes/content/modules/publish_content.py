from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime, timezone
from typing import List

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
    PublishToSitesResponse
)
from src.utils.workspace_utils import resolve_and_verify_workspace
from src.services.content_service import ContentService
from src.services.wordpress_publisher import WordPressPublisher
from src.api.models.content_models import Content
from src.api.models.workspace_models.workspace_integration import WorkspaceIntegration

router = APIRouter()


# -------------------------
# Helper: Publish to All Active Sites
# -------------------------
async def _publish_to_all_sites(
    db: AsyncSession,
    workspace_id: UUID,
    content_data: ContentCreate,
    status: str = "publish"
) -> List[PublishResponse]:
    """
    Publish content to all active WordPress sites in the workspace.
    Returns list of results for each site.
    """
    results = []
    
    # Fetch all active sites
    sites_query = select(WorkspaceIntegration).where(
        WorkspaceIntegration.workspace_id == workspace_id,
        WorkspaceIntegration.is_active == True
    )
    sites_result = await db.execute(sites_query)
    sites = sites_result.scalars().all()
    
    if not sites:
        logger.warning(f"No active sites found for workspace {workspace_id}")
        raise HTTPException(
            status_code=400,
            detail="No active WordPress sites found in this workspace. Please connect a site before publishing."
        )
    
    for site in sites:
        try:
            # Initialize WordPress publisher with site credentials
            wp_publisher = WordPressPublisher(
                site_url=site.site_url,
                api_endpoint=site.api_endpoint,
                username=site.username,
                app_password=site.app_password,
                api_key=site.api_key
            )
            
            # Publish to WordPress
            wp_response = wp_publisher.publish_post(
                data=content_data,
                status=status
            )
            
            results.append(PublishResponse(
                site_id=site.id,
                site_url=site.site_url,
                success=True,
                wordpress_post_id=wp_response.get("post_id"),
                wordpress_url=wp_response.get("link")
            ))
            
            logger.info(f"Published to {site.site_url}: post_id={wp_response.get('post_id')}")
            
        except Exception as e:
            logger.error(f"Failed to publish to {site.site_url}: {str(e)}")
            results.append(PublishResponse(
                site_id=site.id,
                site_url=site.site_url,
                success=False,
                error=str(e)
            ))
    
    return results


# -------------------------
# 1. Save Content (Draft Only)
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
    Save content as draft without publishing.
    
    Use this to save work in progress. To publish,
    use the /publish endpoint.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Force draft status
    data.status = "draft"

    service = ContentService(db)
    content = await service.create_content(
        workspace_id=workspace.id,
        user_id=UUID(user_id),
        data=data
    )

    return content.to_dict()


# -------------------------
# 2. Save & Publish (New Content)
# -------------------------
@router.post("/publish")
@db_transaction_handler("publish content", "Content published successfully")
@require_permissions("content.create", workspace_scoped=True)
async def save_and_publish(
    data: ContentCreate,
    request: Request,
    workspace_id: str,
    publish_status: str = "publish",
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Save content AND publish to all active WordPress sites.
    
    This is the primary endpoint for direct publishing.
    Content is saved to database and published to all active sites.
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
    
    # Publish to all active sites
    results = await _publish_to_all_sites(
        db=db,
        workspace_id=workspace.id,
        content_data=data,
        status=publish_status
    )
    
    # Update content with first successful publish info
    successful_results = [r for r in results if r.success]
    if successful_results:
        first_success = successful_results[0]
        content.wordpress_post_id = first_success.wordpress_post_id
        content.wordpress_url = first_success.wordpress_url
        content.wordpress_published_at = datetime.now(timezone.utc)
        content.status = "published"
    
    return {
        "content": content.to_dict(),
        "publish_results": {
            "total_sites": len(results),
            "successful": len(successful_results),
            "failed": len(results) - len(successful_results),
            "results": [r.model_dump() for r in results]
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
    
    Fetches content from database and publishes to all active sites.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))
    
    # Get existing content
    service = ContentService(db)
    content = await service._get_content_or_404(content_id, workspace.id, include_seo=True)
    
    # Build ContentCreate from existing content
    from src.api.schema.content_schema import ContentSEODataSchema
    
    seo_data = None
    if hasattr(content, 'seo_data') and content.seo_data:
        seo_data = ContentSEODataSchema(
            meta_title=content.seo_data.meta_title,
            meta_description=content.seo_data.meta_description,
            focus_keyphrase=content.seo_data.focus_keyphrase
        )
    
    content_data = ContentCreate(
        title=content.title,
        introduction=content.introduction,
        body_html=content.body_html,
        body_markdown=content.body_markdown,
        tags=content.tags,
        seo_data=seo_data
    )
    
    # Get publish status from request or default to "publish"
    status = "publish"
    if publish_data and publish_data.status:
        status = publish_data.status
    
    # Publish to all active sites
    results = await _publish_to_all_sites(
        db=db,
        workspace_id=workspace.id,
        content_data=content_data,
        status=status
    )
    
    # Update content with first successful publish info
    successful_results = [r for r in results if r.success]
    if successful_results:
        first_success = successful_results[0]
        content.wordpress_post_id = first_success.wordpress_post_id
        content.wordpress_url = first_success.wordpress_url
        content.wordpress_published_at = datetime.now(timezone.utc)
        content.status = "published"
    
    return {
        "content": content.to_dict(),
        "publish_results": {
            "content_id": str(content_id),
            "total_sites": len(results),
            "successful": len(successful_results),
            "failed": len(results) - len(successful_results),
            "results": [r.model_dump() for r in results]
        }
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