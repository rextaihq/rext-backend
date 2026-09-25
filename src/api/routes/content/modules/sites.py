from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config import settings
from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import ResourceNotFoundException, RextValidationException
from src.api.models import Content, WorkspaceIntegration
from src.api.schema.content_schema import (
    ContentCreate,
    ContentSEODataSchema,
    PublishToSiteRequest,
    WorkspaceIntegrationCreate,
    WorkspaceIntegrationUpdate,
)
from src.api.schema.response.content_responses import (
    SiteDeletedResponse,
    SiteListResponse,
    SiteResponse,
    WordPressPublishResult,
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services.content_service import ContentService
from src.utils.image_placeholder import strip_unresolved_placeholders
from src.utils.integration_dedupe import ensure_no_duplicate_integration
from src.utils.logger import logger
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.wordpress_status import content_status_for_wordpress_status
from src.utils.workspace_utils import resolve_and_verify_workspace
from src.web.shopify_bridge import (
    ShopifyAppBridge,
    build_admin_app_launch_url,
    extract_store_handle,
    normalize_store_url,
)
from src.web.wordpress import WordPressPublisher

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
@require_permissions("integration.read", workspace_scoped=True)
@db_transaction_handler("list connected sites")
async def list_connected_sites(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
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
            "workspace_id": str(workspace.id),
        },
        request=request,
        message="Connected sites retrieved successfully",
    )


@router.post("/connect", response_model=SuccessResponse[SiteResponse])
@db_transaction_handler("connect site", "Site connected successfully")
@require_permissions("integration.create", workspace_scoped=True)
async def connect_site(
    data: WorkspaceIntegrationCreate,
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Connect a new external site"""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    config_json = dict(data.config_json or {})
    site_url = data.site_url

    if data.integration_type.lower() == "shopify":
        if not site_url:
            raise RextValidationException(message="Shopify store URL is required.")

        site_url = normalize_store_url(site_url)
        store_handle = extract_store_handle(site_url)
        app_slug = (config_json.get("app_slug") or settings.SHOPIFY_APP_SLUG).strip()
        app_entry_path = config_json.get("app_entry_path") or settings.SHOPIFY_APP_ENTRY_PATH
        app_launch_url = build_admin_app_launch_url(
            store_handle=store_handle,
            app_slug=app_slug,
            entry_path=app_entry_path,
        )
        config_json.update(
            {
                "connection_mode": "app_bridge",
                "app_slug": app_slug,
                "app_launch_url": app_launch_url,
            }
        )

    # The same site must not be connected twice in one workspace. Runs after
    # Shopify URL normalization so the comparison uses the final site URL.
    await ensure_no_duplicate_integration(
        db, workspace.id, data.integration_type, site_url
    )

    # Validate WordPress plugin connection if API Key is provided
    if data.integration_type.lower() != "shopify" and data.api_key:
        try:
            logger.info(f"Validating site connection for {site_url} using Rext-AI plugin")
            async with WordPressPublisher(
                site_url=site_url, api_endpoint=data.api_endpoint, api_key=data.api_key
            ) as wp_publisher:
                await wp_publisher.validate_plugin()
            logger.info("Rext-AI validation successful")

        except Exception as e:
            logger.error(f"Site connection validation failed: {str(e)}")
            raise RextValidationException(
                message=(
                    "Failed to connect to the Rext-AI plugin. "
                    "Please check your Site URL and API Key."
                ),
            )

    new_site = WorkspaceIntegration(
        workspace_id=workspace.id,
        integration_type=data.integration_type,
        is_active=data.is_active,
        site_url=site_url,
        api_endpoint=data.api_endpoint,
        username=data.username,
        app_password=data.app_password,
        api_key=data.api_key,
        config_json=config_json or data.config_json,
    )

    db.add(new_site)
    await db.flush()

    response_data = {"site": new_site.to_dict()}
    if data.integration_type.lower() == "shopify":
        response_data["app_launch_url"] = (new_site.config_json or {}).get("app_launch_url")

    return success(data=response_data, request=request, message="Site connected successfully")


@router.get("/{site_id}", response_model=SuccessResponse[SiteResponse])
@require_permissions("integration.read", workspace_scoped=True)
@db_transaction_handler("get site details")
async def get_site_details(
    site_id: UUID,
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Get details of a specific connected site"""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    site = await _get_site_or_404(db, site_id, workspace.id)

    return success(
        data={"site": site.to_dict()},
        request=request,
        message="Site details retrieved successfully",
    )


@router.patch("/{site_id}", response_model=SuccessResponse[SiteResponse])
@db_transaction_handler("update site", "Site connection updated successfully")
@require_permissions("integration.update", workspace_scoped=True)
async def update_site(
    site_id: UUID,
    data: WorkspaceIntegrationUpdate,
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Update a connected site's details"""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    site = await _get_site_or_404(db, site_id, workspace.id)

    if data.integration_type is not None:
        site.integration_type = data.integration_type
    if data.is_active is not None:
        site.is_active = data.is_active
    if data.site_url is not None:
        if (data.integration_type or site.integration_type).lower() == "shopify":
            site.site_url = normalize_store_url(data.site_url)
        else:
            site.site_url = data.site_url
    if data.api_endpoint is not None:
        site.api_endpoint = data.api_endpoint
    if data.username is not None:
        site.username = data.username
    if data.app_password is not None:
        site.app_password = data.app_password
    if data.api_key is not None:
        site.api_key = data.api_key
    if data.config_json is not None:
        site.config_json = data.config_json

    if site.integration_type.lower() == "shopify":
        config_json = dict(site.config_json or {})
        app_slug = (config_json.get("app_slug") or settings.SHOPIFY_APP_SLUG).strip()
        app_entry_path = config_json.get("app_entry_path") or settings.SHOPIFY_APP_ENTRY_PATH
        store_handle = extract_store_handle(site.site_url)
        config_json.update(
            {
                "connection_mode": "app_bridge",
                "app_slug": app_slug,
                "app_launch_url": build_admin_app_launch_url(
                    store_handle=store_handle,
                    app_slug=app_slug,
                    entry_path=app_entry_path,
                ),
            }
        )
        site.config_json = config_json

    return success(
        data={"site": site.to_dict()},
        request=request,
        message="Site connection updated successfully",
    )


@router.delete("/{site_id}", response_model=SuccessResponse[SiteDeletedResponse])
@db_transaction_handler("disconnect site", "Site disconnected successfully")
@require_permissions("integration.delete", workspace_scoped=True)
async def delete_site(
    site_id: UUID,
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Disconnect and delete a site connection"""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    site = await _get_site_or_404(db, site_id, workspace.id)

    await db.delete(site)

    return success(
        data={"site_id": str(site_id)}, request=request, message="Site disconnected successfully"
    )


@router.post("/{site_id}/activate", response_model=SuccessResponse[SiteResponse])
@db_transaction_handler("activate site", "Site activated successfully")
@require_permissions("integration.update", workspace_scoped=True)
async def activate_site(
    site_id: UUID,
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Activate a connected site"""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    site = await _get_site_or_404(db, site_id, workspace.id)

    site.is_active = True
    return success(
        data={"site": site.to_dict()}, request=request, message="Site activated successfully"
    )


@router.post("/{site_id}/deactivate", response_model=SuccessResponse[SiteResponse])
@db_transaction_handler("deactivate site", "Site deactivated successfully")
@require_permissions("integration.update", workspace_scoped=True)
async def deactivate_site(
    site_id: UUID,
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Deactivate a connected site"""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    site = await _get_site_or_404(db, site_id, workspace.id)

    site.is_active = False
    return success(
        data={"site": site.to_dict()}, request=request, message="Site deactivated successfully"
    )


@router.post(
    "/{site_id}/publish/{content_id}",
    response_model=SuccessResponse[WordPressPublishResult],
)
@db_transaction_handler("publish to site", "Content published successfully")
@require_permissions("content.publish", workspace_scoped=True)
async def publish_to_site(
    site_id: UUID,
    content_id: UUID,
    request: Request,
    data: PublishToSiteRequest,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Publish a specific content item to a connected site"""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Fetch site
    site = await _get_site_or_404(db, site_id, workspace.id)

    # Fetch content
    content_query = select(Content).where(
        Content.id == content_id, Content.workspace_id == workspace.id
    )
    content_result = await db.execute(content_query)
    content = content_result.scalar_one_or_none()

    if not content:
        raise RextValidationException(
            message="Content not found", context={"content_id": str(content_id)}
        )

    if site.integration_type.lower() == "wordpress":
        try:
            logger.info(
                "[PUBLISH STATUS] endpoint=site_publish content_id=%s "
                "site_id=%s selected_status=%s",
                content_id,
                site_id,
                data.status,
            )
            # Create a ContentCreate object for the publisher
            seo_data = None
            if content.seo_data:
                seo_data = ContentSEODataSchema(
                    meta_title=content.seo_data.meta_title,
                    meta_description=content.seo_data.meta_description,
                    focus_keyphrase=content.seo_data.focus_keyphrase,
                    trust_score=content.seo_data.trust_score,
                )

            content_data = ContentCreate(
                title=content.title,
                body_markdown=content.body_markdown,
                body_html=content.body_html,
                tags=(content.seo_data.content_primary_keywords if content.seo_data else []),
                category=content.category,
                seo_data=seo_data,
                images_data=content.images_data,
            )

            # Publishing this article again must edit the post it already has
            # on this site, and credit the author persona chosen for it.
            publish_context = await ContentService(db).wordpress_publish_context(content, site)

            async with WordPressPublisher(
                site_url=site.site_url,
                api_endpoint=site.api_endpoint,
                username=site.username,
                app_password=site.app_password,
                api_key=site.api_key,
            ) as wp_publisher:
                result = await wp_publisher.publish_post(
                    data=content_data,
                    status=data.status,
                    post_id=await wp_publisher.confirm_existing_post(publish_context["post_id"]),
                    author_name=publish_context["author_name"],
                    author_email=publish_context["author_email"],
                )

            # Update content status and persistence
            if result.get("success"):
                content.status = content_status_for_wordpress_status(data.status)
                content.wordpress_post_id = result.get("post_id")
                content.wordpress_url = result.get("link")
                content.wordpress_published_at = (
                    datetime.now(timezone.utc) if data.status == "publish" else None
                )
                await db.flush()

            return success(
                data={"wordpress_result": result, "content_id": str(content.id)},
                request=request,
                message="Content published successfully",
            )
        except Exception as e:
            logger.error(f"Failed to publish to WordPress: {e}")
            raise RextValidationException(message=f"Publishing failed: {str(e)}")

    elif site.integration_type.lower() == "shopify":
        try:
            config_json = site.config_json or {}
            connection_mode = str(config_json.get("connection_mode") or "").lower()
            use_bridge = connection_mode == "app_bridge" or not site.api_key

            is_published = data.status == "publish"
            # Manual-upload image placeholders that were never resolved or
            # dismissed in the editor must never reach a live Shopify page as a
            # broken image — strip them here, same as the WordPress path.
            body_to_use = (
                strip_unresolved_placeholders(content.body_html or content.body_markdown or "")
                or ""
            )
            tags = content.tags or (
                content.seo_data.content_primary_keywords if content.seo_data else []
            )

            if use_bridge:
                bridge = ShopifyAppBridge(
                    shared_secret=settings.SHOPIFY_BRIDGE_SHARED_SECRET,
                    base_url=settings.SHOPIFY_BRIDGE_BASE_URL,
                    publish_endpoint=settings.SHOPIFY_BRIDGE_PUBLISH_ENDPOINT,
                    fallback_secret_seed=settings.SECRET_KEY,
                )
                shop_resp = await bridge.publish_blog_post(
                    store_url=site.site_url,
                    title=content.title,
                    body=body_to_use,
                    tags=tags,
                    published=is_published,
                    handle=content.slug,
                    feature_image_url=None,
                    content_id=str(content.id),
                    workspace_id=str(workspace.id),
                    config_json=config_json,
                )
            else:
                from src.web.shopify import ShopifyConnector

                async with ShopifyConnector(
                    store_url=site.site_url, access_token=site.api_key
                ) as shopify:
                    shop_resp = await shopify.publish_blog_post(
                        title=content.title,
                        body_html=body_to_use,
                        tags=tags,
                        published=is_published,
                        handle=content.slug,
                    )

            # Update content status
            content.status = "published"
            content.shopify_article_id = shop_resp.get("article_id")
            content.shopify_article_url = shop_resp.get("article_url")
            content.shopify_published_at = datetime.now(timezone.utc)

            return success(
                data={"shopify_result": shop_resp, "content_id": str(content.id)},
                request=request,
                message="Content published successfully",
            )
        except Exception as e:
            logger.error(f"Failed to publish to Shopify: {e}")
            raise RextValidationException(message=f"Shopify publishing failed: {str(e)}")

    else:
        raise RextValidationException(
            message=f"Site type {site.integration_type} not supported for publishing yet"
        )
