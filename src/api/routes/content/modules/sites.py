from fastapi import APIRouter, Depends, Request
import requests
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID
from typing import List

from src.utils.logger import logger
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.middleware.exceptions import WrextValidationException
from src.api.schema.content_schema import (
    IntegrationCreate, 
    IntegrationUpdate, 
    IntegrationResponse,
    IntegrationListResponse,
    PublishToSiteRequest
)
from src.api.models.content_models import Integration, Content
from src.services.wordpress_publisher import WordPressPublisher
from src.utils.workspace_utils import resolve_and_verify_workspace

router = APIRouter()

#list of connected sites
@router.get("/list")
@require_permissions("content.read", workspace_scoped=True)
async def list_connected_sites(
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """List all connected sites for a workspace"""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))
    
    query = select(Integration).where(Integration.workspace_id == workspace.id)
    result = await db.execute(query)
    sites = result.scalars().all()
    
    return {
        "sites": [site.to_dict() for site in sites],
        "total_count": len(sites),
        "workspace_id": str(workspace.id)
    }

#coonect new site
@router.post("/connect")
@db_transaction_handler("connect site", "Site connected successfully")
@require_permissions("content.create", workspace_scoped=True)
async def connect_site(
    data: IntegrationCreate,
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
            wp_publisher = WordPressPublisher(
                site_url=data.site_url,
                api_endpoint=data.api_endpoint,
                api_key=data.api_key
            )
            wp_publisher.validate_plugin()
            logger.info("Rext-AI validation successful")
            
        except Exception as e:
            logger.error(f"Site connection validation failed: {str(e)}")
            raise WrextValidationException(
                message=f"Failed to connect to the Rext-AI plugin. Please check your Site URL and API Key.",
                context={"error": str(e)}
            )

    new_site = Integration(
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
    
    return {"site": new_site.to_dict()}
#details of site
@router.get("/{site_id}")
@require_permissions("content.read", workspace_scoped=True)
async def get_site_details(
    site_id: UUID,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """Get details of a specific connected site"""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))
    
    query = select(Integration).where(
        Integration.id == site_id,
        Integration.workspace_id == workspace.id
    )
    result = await db.execute(query)
    site = result.scalar_one_or_none()
    
    if not site:
        raise WrextValidationException(message="Site not found", context={"site_id": str(site_id)})
        
    return {"site": site.to_dict()}

#update the details of connected site
@router.patch("/{site_id}")
@db_transaction_handler("update site", "Site connection updated successfully")
@require_permissions("content.update", workspace_scoped=True)
async def update_site(
    site_id: UUID,
    data: IntegrationUpdate,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """Update a connected site's details"""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))
    
    query = select(Integration).where(
        Integration.id == site_id,
        Integration.workspace_id == workspace.id
    )
    result = await db.execute(query)
    site = result.scalar_one_or_none()
    
    if not site:
        raise WrextValidationException(message="Site not found", context={"site_id": str(site_id)})
    
    if data.integration_type is not None: site.integration_type = data.integration_type
    if data.is_active is not None: site.is_active = data.is_active
    if data.site_url is not None: site.site_url = data.site_url
    if data.api_endpoint is not None: site.api_endpoint = data.api_endpoint
    if data.username is not None: site.username = data.username
    if data.app_password is not None: site.app_password = data.app_password
    if data.api_key is not None: site.api_key = data.api_key
    if data.config_json is not None: site.config_json = data.config_json
    
    return {"site": site.to_dict()}
#delete a site
@router.delete("/{site_id}")
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
    
    query = select(Integration).where(
        Integration.id == site_id,
        Integration.workspace_id == workspace.id
    )
    result = await db.execute(query)
    site = result.scalar_one_or_none()
    
    if not site:
        raise WrextValidationException(message="Site not found", context={"site_id": str(site_id)})
    
    await db.delete(site)
    
    return {"site_id": str(site_id)}

@router.post("/{site_id}/activate")
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
    
    query = select(Integration).where(
        Integration.id == site_id,
        Integration.workspace_id == workspace.id
    )
    result = await db.execute(query)
    site = result.scalar_one_or_none()
    
    if not site:
        raise WrextValidationException(message="Site not found", context={"site_id": str(site_id)})
    
    site.is_active = True
    return {"site": site.to_dict()}

@router.post("/{site_id}/deactivate")
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
    
    query = select(Integration).where(
        Integration.id == site_id,
        Integration.workspace_id == workspace.id
    )
    result = await db.execute(query)
    site = result.scalar_one_or_none()
    
    if not site:
        raise WrextValidationException(message="Site not found", context={"site_id": str(site_id)})
    
    site.is_active = False
    return {"site": site.to_dict()}

@router.post("/{site_id}/publish/{content_id}")
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
    site_query = select(Integration).where(
        Integration.id == site_id,
        Integration.workspace_id == workspace.id
    )
    site_result = await db.execute(site_query)
    site = site_result.scalar_one_or_none()
    
    if not site:
        raise WrextValidationException(message="Site not found", context={"site_id": str(site_id)})
    
    # Fetch content
    content_query = select(Content).where(
        Content.id == content_id,
        Content.workspace_id == workspace.id
    )
    content_result = await db.execute(content_query)
    content = content_result.scalar_one_or_none()
    
    if not content:
        raise WrextValidationException(message="Content not found", context={"content_id": str(content_id)})
    
    if site.integration_type.lower() == "wordpress":
        wp_publisher = WordPressPublisher(
            site_url=site.site_url,
            username=site.username,
            app_password=site.app_password
        )
        
        try:
            from datetime import timezone
            result = wp_publisher.publish_post(
                title=content.title,
                content=content.body_markdown or content.body_html or "",
                status=data.status,
                excerpt=(content.metadata_json or {}).get("content_summary", ""),
                tags=(content.seo_data.content_primary_keywords if content.seo_data else [])
            )
            
            # Update content status
            content.status = "published"
            content.published_at = datetime.now(timezone.utc)
            
            return {
                "success": True,
                "wordpress_result": result,
                "content_id": str(content.id)
            }
        except Exception as e:
            logger.error(f"Failed to publish to WordPress: {e}")
            raise WrextValidationException(message=f"Publishing failed: {str(e)}")
    else:
        raise WrextValidationException(message=f"Site type {site.site_type} not supported for publishing yet")
