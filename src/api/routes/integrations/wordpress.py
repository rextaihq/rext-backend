import asyncio
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    RextValidationException,
)
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
    WordPressConnectionTest,
    WordPressPublishResult,
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services.content_service import ContentService
from src.utils.integration_dedupe import ensure_no_duplicate_integration
from src.utils.logger import logger
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.url_validator import SSRFValidationError, validate_url_for_ssrf
from src.utils.wordpress_status import content_status_for_wordpress_status
from src.utils.workspace_utils import resolve_and_verify_workspace
from src.web.wordpress import WordPressPublisher

router = APIRouter(prefix="/wordpress", tags=["WordPress Integration"])


async def _get_site_or_404(
    db: AsyncSession, site_id: UUID, workspace_id: UUID
) -> WorkspaceIntegration:
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


@router.get("/", response_model=SuccessResponse[SiteListResponse])
@require_permissions("integration.read", workspace_scoped=True)
@db_transaction_handler("list wordpress sites")
async def list_connected_sites(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    query = select(WorkspaceIntegration).where(
        WorkspaceIntegration.workspace_id == workspace.id,
        WorkspaceIntegration.integration_type == "wordpress",
    )
    result = await db.execute(query)
    sites = result.scalars().all()

    return success(
        data={
            "sites": [site.to_dict() for site in sites],
            "total_count": len(sites),
            "workspace_id": str(workspace.id),
        },
        request=request,
        message="WordPress sites retrieved successfully",
    )


@router.post("/", response_model=SuccessResponse[SiteResponse])
@db_transaction_handler("connect wordpress site", "WordPress site connected successfully")
@require_permissions("integration.create", workspace_scoped=True)
async def connect_site(
    data: WorkspaceIntegrationCreate,
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    integration_type = (data.integration_type or "wordpress").lower()
    if integration_type != "wordpress":
        raise RextValidationException(message="This endpoint only accepts WordPress integrations.")

    config_json = dict(data.config_json or {})
    site_url = data.site_url

    # The same WordPress site must not be connected twice in one workspace.
    await ensure_no_duplicate_integration(db, workspace.id, "wordpress", site_url)

    if data.api_key:
        try:
            logger.info(f"Validating WordPress site connection for {site_url} using Rext-AI plugin")
            async with WordPressPublisher(
                site_url=site_url,
                api_endpoint=data.api_endpoint,
                api_key=data.api_key,
            ) as wp_publisher:
                await wp_publisher.validate_plugin()
        except Exception as e:
            logger.error(f"WordPress site connection validation failed: {str(e)}")

            # The caller gets a message they can act on; the operator gets the
            # real one. Converting the vendor failure into a validation error
            # for the response also buried it in the Error Logs as a routine
            # 4xx, indistinguishable from a mistyped field, so the underlying
            # failure is recorded here at its true severity first.
            from src.services.monitoring_service import MonitoringService

            await MonitoringService.report_third_party_failure(
                service="WordPress",
                message=f"WordPress site connection failed for {site_url}: {e}",
                error=e,
                metadata={
                    "site_url": site_url,
                    "api_endpoint": data.api_endpoint,
                    "stage": "connect_validation",
                },
                # Each connection attempt is a distinct user action, so every
                # one is recorded rather than collapsed into the first.
                throttle=False,
            )

            validation_error = RextValidationException(
                message=(
                    "Failed to connect to the Rext-AI plugin. "
                    "Please check your Site URL and API Key."
                ),
            )
            # Already recorded above, at critical rather than warning.
            validation_error.suppress_error_log = True
            raise validation_error

    new_site = WorkspaceIntegration(
        workspace_id=workspace.id,
        integration_type="wordpress",
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

    return success(
        data={"site": new_site.to_dict()},
        request=request,
        message="WordPress site connected successfully",
    )


@router.get("/{site_id}", response_model=SuccessResponse[SiteResponse])
@require_permissions("integration.read", workspace_scoped=True)
@db_transaction_handler("get wordpress site details")
async def get_site_details(
    site_id: UUID,
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    site = await _get_site_or_404(db, site_id, workspace.id)
    if site.integration_type.lower() != "wordpress":
        raise RextValidationException(message="Requested site is not a WordPress site.")

    return success(
        data={"site": site.to_dict()},
        request=request,
        message="WordPress site details retrieved successfully",
    )


@router.patch("/{site_id}", response_model=SuccessResponse[SiteResponse])
@db_transaction_handler("update wordpress site", "WordPress site updated successfully")
@require_permissions("integration.update", workspace_scoped=True)
async def update_site(
    site_id: UUID,
    data: WorkspaceIntegrationUpdate,
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    site = await _get_site_or_404(db, site_id, workspace.id)
    if site.integration_type.lower() != "wordpress":
        raise RextValidationException(message="Requested site is not a WordPress site.")

    if data.integration_type is not None and data.integration_type.lower() != "wordpress":
        raise RextValidationException(message="This endpoint only accepts WordPress integrations.")

    site.integration_type = "wordpress"
    if data.is_active is not None:
        site.is_active = data.is_active
    if data.site_url is not None:
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

    return success(
        data={"site": site.to_dict()},
        request=request,
        message="WordPress site updated successfully",
    )


@router.delete("/{site_id}", response_model=SuccessResponse[SiteDeletedResponse])
@db_transaction_handler("disconnect wordpress site", "WordPress site disconnected successfully")
@require_permissions("integration.delete", workspace_scoped=True)
async def delete_site(
    site_id: UUID,
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    site = await _get_site_or_404(db, site_id, workspace.id)
    if site.integration_type.lower() != "wordpress":
        raise RextValidationException(message="Requested site is not a WordPress site.")

    await db.delete(site)

    return success(
        data={"site_id": str(site_id)},
        request=request,
        message="WordPress site disconnected successfully",
    )


@router.post("/{site_id}/activate", response_model=SuccessResponse[SiteResponse])
@db_transaction_handler("activate wordpress site", "WordPress site activated successfully")
@require_permissions("integration.update", workspace_scoped=True)
async def activate_site(
    site_id: UUID,
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    site = await _get_site_or_404(db, site_id, workspace.id)
    if site.integration_type.lower() != "wordpress":
        raise RextValidationException(message="Requested site is not a WordPress site.")

    site.is_active = True
    return success(
        data={"site": site.to_dict()},
        request=request,
        message="WordPress site activated successfully",
    )


@router.post("/{site_id}/deactivate", response_model=SuccessResponse[SiteResponse])
@db_transaction_handler("deactivate wordpress site", "WordPress site deactivated successfully")
@require_permissions("integration.update", workspace_scoped=True)
async def deactivate_site(
    site_id: UUID,
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    site = await _get_site_or_404(db, site_id, workspace.id)
    if site.integration_type.lower() != "wordpress":
        raise RextValidationException(message="Requested site is not a WordPress site.")

    site.is_active = False
    return success(
        data={"site": site.to_dict()},
        request=request,
        message="WordPress site deactivated successfully",
    )


async def _check_connection(site: WorkspaceIntegration) -> dict:
    """Run the connection check on a stored site, or say why it cannot run."""
    if not (site.api_key or (site.username and site.app_password)):
        # Never build a publisher without the site's own credentials: it would
        # fall back to the server's WORDPRESS_* settings.
        return {
            "status": "no_credentials",
            "message": "This connection has no API key. Add the key from the Rext AI plugin.",
            "authors_available": None,
        }

    # The test sends the stored credentials to the stored addresses: refuse
    # private and reserved networks, as the site scraper does.
    try:
        for url in filter(None, (site.site_url, site.api_endpoint)):
            await asyncio.to_thread(validate_url_for_ssrf, url)
    except SSRFValidationError as exc:
        logger.warning(f"WordPress connection test refused for site {site.id}: {exc}")
        return {
            "status": "blocked_address",
            "message": "The site's address points to a private or reserved network.",
            "authors_available": None,
        }

    async with WordPressPublisher(
        site_url=site.site_url,
        api_endpoint=site.api_endpoint,
        username=site.username,
        app_password=site.app_password,
        api_key=site.api_key,
    ) as wp_publisher:
        return await wp_publisher.check_connection()


@router.post("/{site_id}/test", response_model=SuccessResponse[WordPressConnectionTest])
@require_permissions("integration.read", workspace_scoped=True)
@db_transaction_handler("test wordpress connection", auto_commit=False)
async def check_site_connection(
    site_id: UUID,
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Test a connected site's stored credentials again; nothing changes on either side.

    A failed test is an answer, not an error: the response is 200 with `ok`
    false, a `status` and a message the user can act on.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    site = await _get_site_or_404(db, site_id, workspace.id)
    if site.integration_type.lower() != "wordpress":
        raise RextValidationException(message="Requested site is not a WordPress site.")

    result = await _check_connection(site)

    return success(
        data={
            "site_id": str(site.id),
            "ok": result["status"] == "connected",
            "checked_at": datetime.now(timezone.utc),
            **result,
        },
        request=request,
        message=result["message"],
    )


@router.post(
    "/{site_id}/publish/{content_id}", response_model=SuccessResponse[WordPressPublishResult]
)
@db_transaction_handler(
    "publish content to wordpress", "Content published to WordPress successfully"
)
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
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    site = await _get_site_or_404(db, site_id, workspace.id)
    if site.integration_type.lower() != "wordpress":
        raise RextValidationException(message="Requested site is not a WordPress site.")

    content_query = select(Content).where(
        Content.id == content_id,
        Content.workspace_id == workspace.id,
    )
    content_result = await db.execute(content_query)
    content = content_result.scalar_one_or_none()

    if not content:
        raise RextValidationException(
            message="Content not found",
            context={"content_id": str(content_id)},
        )

    try:
        logger.info(
            "[PUBLISH STATUS] endpoint=wordpress_site_publish content_id=%s site_id=%s selected_status=%s",
            content_id,
            site_id,
            data.status,
        )
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

        # Publishing this article again must edit the post it already has on
        # this site, and credit the author persona chosen for it.
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

        if result.get("success"):
            content.status = content_status_for_wordpress_status(data.status)
            content.wordpress_post_id = result.get("post_id")
            content.wordpress_url = result.get("link")
            content.wordpress_published_at = (
                datetime.now(timezone.utc) if data.status == "publish" else None
            )
            await db.flush()

        return success(
            data={
                "wordpress_result": result,
                "content_id": str(content.id),
            },
            request=request,
            message="Content published successfully",
        )
    except Exception as e:
        logger.error(f"Failed to publish to WordPress: {e}")
        raise RextValidationException(message=f"Publishing failed: {str(e)}")
