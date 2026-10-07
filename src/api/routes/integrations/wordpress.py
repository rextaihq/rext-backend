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
from src.api.models import WorkspaceIntegration
from src.api.schema.content_schema import (
    WorkspaceIntegrationCreate,
    WorkspaceIntegrationUpdate,
)
from src.api.schema.response.content_responses import (
    SiteDeletedResponse,
    SiteListResponse,
    SiteResponse,
    WordPressConnectionTest,
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.utils.integration_dedupe import ensure_no_duplicate_integration
from src.utils.integration_urls import ensure_public_site_urls
from src.utils.logger import logger
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.url_validator import SSRFValidationError, validate_url_for_ssrf
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
    await ensure_public_site_urls(site_url, data.api_endpoint)

    # The same WordPress site must not be connected twice in one workspace.
    await ensure_no_duplicate_integration(db, workspace.id, "wordpress", site_url)

    if data.api_key:
        # The key is tested as the Test button tests a stored connection: the plugin's
        # authenticated /verify has to accept it. (Its namespace index, checked before,
        # answers anyone, and a missing plugin let any key through.)
        logger.info(f"Testing the Rext AI plugin's key for {site_url} before connecting")
        try:
            async with WordPressPublisher(
                site_url=site_url,
                api_endpoint=data.api_endpoint,
                api_key=data.api_key,
            ) as wp_publisher:
                result = await wp_publisher.check_connection()
        except SSRFValidationError:
            raise RextValidationException(
                message="The site's address points to a private or reserved network."
            ) from None

        if result["status"] != "connected":
            validation_error = RextValidationException(message=result["message"])
            if result["status"] in ("unreachable", "error"):
                # The site failed, not the customer's input: the operator sees it at
                # its true severity, since the response is a routine 4xx.
                from src.services.monitoring_service import MonitoringService

                await MonitoringService.report_third_party_failure(
                    service="WordPress",
                    message=f"WordPress site connection failed for {site_url}: {result['message']}",
                    metadata={
                        "site_url": site_url,
                        "api_endpoint": data.api_endpoint,
                        "stage": "connect_validation",
                        "status": result["status"],
                    },
                    # Each connection attempt is a distinct user action, so every
                    # one is recorded rather than collapsed into the first.
                    throttle=False,
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

    await ensure_public_site_urls(data.site_url, data.api_endpoint)

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
