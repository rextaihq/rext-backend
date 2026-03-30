from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime, timezone

from src.utils.logger import logger
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.middleware.exceptions import RextValidationException, ResourceNotFoundException
from src.api.schema.content_schema import (
    WorkspaceIntegrationCreate, 
    WorkspaceIntegrationUpdate, 
    PublishToSiteRequest,
    ContentCreate
)
from src.api.schema.response.content_responses import (
    SiteResponse,
    SiteListResponse,
    SiteDeletedResponse,
    WordPressPublishResult
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.models import WorkspaceIntegration, Content
from src.web.wordpress import WordPressPublisher
from src.utils.workspace_utils import resolve_and_verify_workspace
from src.utils.response_utils import success

router = APIRouter()


async def _get_site_or_404(
    db: AsyncSession, site_id: UUID, workspace_id: UUID
) -> WorkspaceIntegration:
    """Fetch a WorkspaceIntegration by ID within a workspace, or raise 404."""
    query = select(WorkspaceIntegration).where(
        WorkspaceIntegration.id == site_id,
        WorkspaceIntegration.workspace_id == workspace_id,
    )
    result = await db.execute(query)
    site = result.scalar_one_or_none()
    if not site:
        raise ResourceNotFoundException(
            resource_type="Site",
            resource_id=str(site_id),
        )
    return site


@router.get("/list", response_model=SuccessResponse[SiteListResponse])
@require_permissions("content.read", workspace_scoped=True)
@db_transaction_handler("list connected sites")
async def list_connected_sites(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """List all connected sites for a workspace"""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))
    
    query = select(WorkspaceIntegration).where(WorkspaceIntegration.workspace_id == workspace.id)
    result = await db.execute(query)
    sites = result.scalars().all()
    
    return success(
        data={
            "sites": [site.to_dict() for site in sites],
            "total_count": len(sites),
            "workspace_id": str(workspace.id)
        },
        request=request,
        message="Connected sites retrieved successfully"
    )

@router.post("/connect", response_model=SuccessResponse[SiteResponse])
@db_transaction_handler("connect site", "Site connected successfully")
@require_permissions("content.create", workspace_scoped=True)
async def connect_site(
    data: WorkspaceIntegrationCreate,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """Connect a new external site"""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))
    
    # Validate connection if API Key is provided
    if data.api_key:
        try:
            logger.info(f"Validating site connection for {data.site_url} using Rext-AI plugin")
            async with WordPressPublisher(
                site_url=data.site_url,
                api_endpoint=data.api_endpoint,
                api_key=data.api_key
            ) as wp_publisher:
                await wp_publisher.validate_plugin()
            logger.info("Rext-AI validation successful")
            
        except Exception as e:
            logger.error(f"Site connection validation failed: {str(e)}")
            raise RextValidationException(
                message=f"Failed to connect to the Rext-AI plugin. Please check your Site URL and API Key.",
            )

    new_site = WorkspaceIntegration(
        workspace_id=workspace.id,
        integration_type=data.integration_type,
        is_active=data.is_active,
        site_url=data.site_url,
        api_endpoint=data.api_endpoint,
        username=data.username,
        app_password=data.app_password,
        api_key=data.api_key,
        config_json=data.config_json
    )
    
    db.add(new_site)
    await db.flush()
    
    return success(
        data={"site": new_site.to_dict()},
        request=request,
        message="Site connected successfully"
    )

@router.get("/{site_id}", response_model=SuccessResponse[SiteResponse])
@require_permissions("content.read", workspace_scoped=True)
@db_transaction_handler("get site details")
async def get_site_details(
    site_id: UUID,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """Get details of a specific connected site"""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))
    
    site = await _get_site_or_404(db, site_id, workspace.id)
        
    return success(
        data={"site": site.to_dict()},
        request=request,
        message="Site details retrieved successfully"
    )

@router.patch("/{site_id}", response_model=SuccessResponse[SiteResponse])
@db_transaction_handler("update site", "Site connection updated successfully")
@require_permissions("content.update", workspace_scoped=True)
async def update_site(
    site_id: UUID,
    data: WorkspaceIntegrationUpdate,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """Update a connected site's details"""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))
    
    site = await _get_site_or_404(db, site_id, workspace.id)
    
    if data.integration_type is not None: site.integration_type = data.integration_type
    if data.is_active is not None: site.is_active = data.is_active
    if data.site_url is not None: site.site_url = data.site_url
    if data.api_endpoint is not None: site.api_endpoint = data.api_endpoint
    if data.username is not None: site.username = data.username
    if data.app_password is not None: site.app_password = data.app_password
    if data.api_key is not None: site.api_key = data.api_key
    if data.config_json is not None: site.config_json = data.config_json
    
    return success(
        data={"site": site.to_dict()},
        request=request,
        message="Site connection updated successfully"
    )

@router.delete("/{site_id}", response_model=SuccessResponse[SiteDeletedResponse])
@db_transaction_handler("disconnect site", "Site disconnected successfully")
@require_permissions("content.delete", workspace_scoped=True)
async def delete_site(
    site_id: UUID,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """Disconnect and delete a site connection"""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))
    
    site = await _get_site_or_404(db, site_id, workspace.id)
    
    await db.delete(site)
    
    return success(
        data={"site_id": str(site_id)},
        request=request,
        message="Site disconnected successfully"
    )

@router.post("/{site_id}/activate", response_model=SuccessResponse[SiteResponse])
@db_transaction_handler("activate site", "Site activated successfully")
@require_permissions("content.update", workspace_scoped=True)
async def activate_site(
    site_id: UUID,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """Activate a connected site"""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))
    
    site = await _get_site_or_404(db, site_id, workspace.id)
    
    site.is_active = True
    return success(
        data={"site": site.to_dict()},
        request=request,
        message="Site activated successfully"
    )

@router.post("/{site_id}/deactivate", response_model=SuccessResponse[SiteResponse])
@db_transaction_handler("deactivate site", "Site deactivated successfully")
@require_permissions("content.update", workspace_scoped=True)
async def deactivate_site(
    site_id: UUID,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """Deactivate a connected site"""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))
    
    site = await _get_site_or_404(db, site_id, workspace.id)
    
    site.is_active = False
    return success(
        data={"site": site.to_dict()},
        request=request,
        message="Site deactivated successfully"
    )

@router.post("/{site_id}/publish/{content_id}", response_model=SuccessResponse[WordPressPublishResult])
@db_transaction_handler("publish to site", "Content published successfully")
@require_permissions("content.publish", workspace_scoped=True)
async def publish_to_site(
    site_id: UUID,
    content_id: UUID,
    data: PublishToSiteRequest,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """Publish a specific content item to a connected site"""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))
    
    # Fetch site
    site = await _get_site_or_404(db, site_id, workspace.id)
    
    # Fetch content
    content_query = select(Content).where(
        Content.id == content_id,
        Content.workspace_id == workspace.id
    )
    content_result = await db.execute(content_query)
    content = content_result.scalar_one_or_none()
    
    if not content:
        raise RextValidationException(message="Content not found", context={"content_id": str(content_id)})
    
    if site.integration_type.lower() == "wordpress":
        try:
            # Create a ContentCreate object for the publisher
            content_data = ContentCreate(
                title=content.title,
                body_markdown=content.body_markdown,
                body_html=content.body_html,
                tags=(content.seo_data.content_primary_keywords if content.seo_data else []),
                seo_data=content.seo_data
            )
            
            async with WordPressPublisher(
                site_url=site.site_url,
                api_endpoint=site.api_endpoint,
                username=site.username,
                app_password=site.app_password,
                api_key=site.api_key
            ) as wp_publisher:
                result = await wp_publisher.publish_post(
                    data=content_data,
                    status=data.status
                )
            
            # Update content status and persistence
            if result.get("success"):
                content.status = "published"
                content.wordpress_post_id = result.get("post_id")
                content.wordpress_url = result.get("link")
                content.wordpress_published_at = datetime.now(timezone.utc)
                await db.flush()
            
            return success(
                data={
                    "wordpress_result": result,
                    "content_id": str(content.id)
                },
                request=request,
                message="Content published successfully"
            )
        except Exception as e:
            logger.error(f"Failed to publish to WordPress: {e}")
            raise RextValidationException(message=f"Publishing failed: {str(e)}")
            
    elif site.integration_type.lower() == "shopify":
        try:
            from src.web.shopify import ShopifyConnector
            async with ShopifyConnector(
                store_url=site.site_url,
                access_token=site.api_key
            ) as shopify:
                is_published = data.status == "publish"
                body_to_use = content.body_html or content.body_markdown or ""
                
                shop_resp = await shopify.publish_blog_post(
                    title=content.title,
                    body_html=body_to_use,
                    tags=(content.seo_data.content_primary_keywords if content.seo_data else []),
                    published=is_published,
                    handle=content.slug
                )
                
            # Update content status
            content.status = "published"
            content.shopify_article_id = shop_resp.get("article_id")
            content.shopify_article_url = shop_resp.get("article_url")
            content.shopify_published_at = datetime.now(timezone.utc)
            
            return {
                "shopify_result": shop_resp,
                "content_id": str(content.id)
            }
        except Exception as e:
            logger.error(f"Failed to publish to Shopify: {e}")
            raise RextValidationException(message=f"Shopify publishing failed: {str(e)}")
            
    else:
        raise RextValidationException(message=f"Site type {site.integration_type} not supported for publishing yet")
