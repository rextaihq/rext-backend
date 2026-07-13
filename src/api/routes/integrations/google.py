from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config import settings
from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    RextValidationException,
)
from src.api.models import WorkspaceIntegration
from src.api.schema.google_schema import (
    ContentPerformanceResponse,
    GA4PropertiesResponse,
    GoogleConnectResponse,
    GoogleIntegrationStatusResponse,
    GoogleSetupStatusResponse,
    GoogleSiteMappingResponse,
    GoogleSiteMappingUpsert,
    GoogleSiteSelectionResponse,
    GoogleSiteSelectionUpsert,
    GoogleSitesOverviewResponse,
    PublishedContentResponse,
    SearchConsoleSitesResponse,
    TrackedContentResponse,
    TrackedContentUpdate,
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services.google_analytics_service import GoogleAnalyticsService
from src.services.google_integration_service import (
    GoogleIntegrationService,
    schedule_post_publish_sync,
    schedule_site_metrics_sync,
)
from src.services.google_oauth_service import GoogleOAuthService
from src.services.google_property_cache_service import GooglePropertyCacheService
from src.services.search_console_service import SearchConsoleService
from src.utils.logger import logger
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.workspace_utils import resolve_and_verify_workspace

router = APIRouter(prefix="/google", tags=["Google Integration"])


async def _get_wordpress_site_or_404(
    db: AsyncSession, site_id: UUID, workspace_id: UUID
) -> WorkspaceIntegration:
    query = select(WorkspaceIntegration).where(
        WorkspaceIntegration.id == site_id,
        WorkspaceIntegration.workspace_id == workspace_id,
    )
    result = await db.execute(query)
    site = result.scalar_one_or_none()
    if not site or site.integration_type.lower() != "wordpress":
        raise ResourceNotFoundException(resource_type="WordPress site", resource_id=str(site_id))
    return site


def _build_callback_url(request: Request) -> str:
    base = (settings.BACKEND_URL or str(request.base_url)).rstrip("/")
    return f"{base}{settings.GOOGLE_OAUTH_CALLBACK_PATH}"


# ============================================================================
# OAuth connection lifecycle
# ============================================================================

@router.get("/connect", response_model=SuccessResponse[GoogleConnectResponse])
@db_transaction_handler("start google connection", auto_commit=False)
@require_permissions("content.update", workspace_scoped=True)
async def start_google_connect(
    workspace_id: str,
    request: Request,
    return_path: Optional[str] = None,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Build the Google OAuth consent URL for a workspace."""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    service = GoogleOAuthService(db)
    authorization_url = service.build_authorization_url(
        workspace_id=workspace.id,
        user_id=user_id,
        callback_url=_build_callback_url(request),
        return_path=return_path,
    )

    return {"authorization_url": authorization_url}


@router.get("/callback", name="google_oauth_callback")
async def google_oauth_callback(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Handle the Google OAuth callback and redirect back to the frontend."""
    service = GoogleOAuthService(db)
    query_params = {key: value for key, value in request.query_params.items()}

    try:
        redirect_url = await service.complete_oauth(
            query_params=query_params, callback_url=_build_callback_url(request)
        )
    except Exception as exc:
        logger.error(f"Google OAuth callback failed: {exc}")
        return_path = None
        workspace_id = None
        state = query_params.get("state")
        if state:
            try:
                payload = service.decode_state(state)
                return_path = payload.get("return_path")
                workspace_id = payload.get("workspace_id")
            except Exception:
                pass
        redirect_url = service.build_error_redirect(
            message=str(exc), return_path=return_path, workspace_id=workspace_id
        )

    return RedirectResponse(url=redirect_url, status_code=302)


@router.get("/", response_model=SuccessResponse[GoogleIntegrationStatusResponse])
@db_transaction_handler("get google integration status")
@require_permissions("content.read", workspace_scoped=True)
async def get_google_integration_status(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Get the current Google connection status for a workspace."""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    oauth_service = GoogleOAuthService(db)
    integration = await oauth_service.get_integration(workspace.id)

    if not integration:
        return {"connected": False}

    return {
        "connected": True,
        "google_account_email": integration.google_account_email,
        "scopes": integration.scopes,
        "is_active": integration.is_active,
        "connected_at": integration.created_at,
        "last_refreshed_at": integration.last_refreshed_at,
    }


@router.delete("/", response_model=SuccessResponse[dict])
@db_transaction_handler("disconnect google integration", "Google account disconnected successfully")
@require_permissions("content.update", workspace_scoped=True)
async def disconnect_google_integration(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Disconnect the workspace's Google account (revokes + deactivates)."""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    oauth_service = GoogleOAuthService(db)
    await oauth_service.disconnect(workspace.id)

    return {"workspace_id": str(workspace.id)}


# ============================================================================
# Search Console site listing
# ============================================================================

@router.get("/search-console/sites", response_model=SuccessResponse[SearchConsoleSitesResponse])
@db_transaction_handler("list search console sites")
@require_permissions("content.read", workspace_scoped=True)
async def list_search_console_sites(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """List verified Search Console properties for the workspace's connected Google account."""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    oauth_service = GoogleOAuthService(db)
    integration = await oauth_service.get_active_integration(workspace.id)
    if not integration:
        raise RextValidationException(message="Google account is not connected for this workspace.")

    access_token = await oauth_service.get_valid_access_token(integration)
    sites = await SearchConsoleService(db).list_available_sites(access_token)

    return {"sites": sites}


# ============================================================================
# GA4 property listing
# ============================================================================

@router.get("/analytics/properties", response_model=SuccessResponse[GA4PropertiesResponse])
@db_transaction_handler("list ga4 properties")
@require_permissions("content.read", workspace_scoped=True)
async def list_ga4_properties(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """List GA4 properties the workspace's connected Google account can access."""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    oauth_service = GoogleOAuthService(db)
    integration = await oauth_service.get_active_integration(workspace.id)
    if not integration:
        raise RextValidationException(message="Google account is not connected for this workspace.")

    access_token = await oauth_service.get_valid_access_token(integration)
    properties = await GoogleAnalyticsService(db).list_available_properties(access_token)

    return {"properties": properties}


# ============================================================================
# Per-WordPress-site GSC/GA4 mapping
# ============================================================================

@router.get(
    "/sites/{site_id}/mapping", response_model=SuccessResponse[Optional[GoogleSiteMappingResponse]]
)
@db_transaction_handler("get google site mapping")
@require_permissions("content.read", workspace_scoped=True)
async def get_google_site_mapping(
    site_id: UUID,
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Get the GSC/GA4 mapping for a connected WordPress site, if any."""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))
    await _get_wordpress_site_or_404(db, site_id, workspace.id)

    mapping = await GoogleIntegrationService(db).get_site_mapping(site_id)
    return mapping.to_dict() if mapping else None


@router.put("/sites/{site_id}/mapping", response_model=SuccessResponse[GoogleSiteMappingResponse])
@db_transaction_handler("update google site mapping", "Google site mapping updated successfully")
@require_permissions("content.update", workspace_scoped=True)
async def upsert_google_site_mapping(
    site_id: UUID,
    data: GoogleSiteMappingUpsert,
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    Set the Search Console site URL and/or GA4 property ID for a connected
    WordPress site. The GA4 property (if provided) is validated against the
    connected Google account before saving.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))
    await _get_wordpress_site_or_404(db, site_id, workspace.id)

    if data.ga4_property_id:
        oauth_service = GoogleOAuthService(db)
        integration = await oauth_service.get_active_integration(workspace.id)
        if not integration:
            raise RextValidationException(
                message="Google account is not connected for this workspace."
            )
        access_token = await oauth_service.get_valid_access_token(integration)
        is_valid = await GoogleAnalyticsService(db).validate_property(
            access_token, data.ga4_property_id
        )
        if not is_valid:
            raise RextValidationException(
                message=(
                    "Unable to access this GA4 property with the connected Google account. "
                    "Double-check the property ID and that the account has at least Viewer access."
                )
            )

    mapping = await GoogleIntegrationService(db).upsert_site_mapping(
        workspace_id=workspace.id,
        site_id=site_id,
        gsc_site_url=data.gsc_site_url,
        ga4_property_id=data.ga4_property_id,
        is_active=data.is_active,
    )

    # Populate site-wide dashboard data immediately (best-effort, own
    # session) instead of waiting for the next scheduled sync cycle.
    schedule_site_metrics_sync(workspace.id)

    return mapping.to_dict()


@router.delete("/sites/{site_id}/mapping", response_model=SuccessResponse[dict])
@db_transaction_handler("remove google site mapping", "Google site mapping removed successfully")
@require_permissions("content.update", workspace_scoped=True)
async def delete_google_site_mapping(
    site_id: UUID,
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Remove GSC/GA4 tracking for a connected WordPress site."""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))
    await _get_wordpress_site_or_404(db, site_id, workspace.id)

    await GoogleIntegrationService(db).remove_site_mapping(site_id)

    return {"site_id": str(site_id)}


# ============================================================================
# Content performance
# ============================================================================

@router.get(
    "/content/{content_id}/performance", response_model=SuccessResponse[ContentPerformanceResponse]
)
@db_transaction_handler("get content performance")
@require_permissions("content.read", workspace_scoped=True)
async def get_content_performance(
    content_id: UUID,
    workspace_id: str,
    request: Request,
    days: int = 30,
    refresh: bool = False,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    Get stored Search Console + GA4 daily metrics for a content item.

    Pass ``refresh=true`` to trigger an on-demand sync before returning —
    safe here since it's an explicit user-initiated action, unlike the
    publish path which never makes external calls inline.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    service = GoogleIntegrationService(db)

    if refresh:
        await service.refresh_content_performance(
            content_id=content_id, workspace_id=workspace.id, lookback_days=days
        )

    performance = await service.get_content_performance(
        content_id=content_id, workspace_id=workspace.id, days=days
    )

    return {"content_id": content_id, **performance}


# ============================================================================
# Onboarding flow — setup status, site selection, content selection
# ============================================================================


@router.get("/setup-status", response_model=SuccessResponse[GoogleSetupStatusResponse])
@db_transaction_handler("get google setup status")
@require_permissions("content.read", workspace_scoped=True)
async def get_google_setup_status(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    Cheap DB-only read that tells the frontend which onboarding step the
    workspace is on: connect_google | select_site | select_content | ready.
    No Google API calls — safe to poll frequently.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    oauth_service = GoogleOAuthService(db)
    integration = await oauth_service.get_active_integration(workspace.id)
    google_connected = integration is not None

    status = await GoogleIntegrationService(db).get_setup_status(
        workspace_id=workspace.id, google_connected=google_connected
    )
    return status


@router.get("/sites", response_model=SuccessResponse[GoogleSitesOverviewResponse])
@db_transaction_handler("get google sites overview")
@require_permissions("content.read", workspace_scoped=True)
async def get_google_sites_overview(
    workspace_id: str,
    request: Request,
    force_refresh: bool = False,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    Everything the site-selection screen needs in one call:
    - Connected WordPress sites with their current GSC/GA4 mapping
    - Cached GSC properties (TTL-refreshed from Google if stale/forced)
    - Cached GA4 properties (same)

    Pass ``force_refresh=true`` to bypass the 15-minute TTL and pull a
    fresh list from Google — useful for the "Refresh" button in the UI.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    service = GoogleIntegrationService(db)
    sites = await service.list_wordpress_sites_with_mappings(workspace.id)

    # Serve properties from the local cache (refreshed if stale or forced).
    oauth_service = GoogleOAuthService(db)
    integration = await oauth_service.get_active_integration(workspace.id)
    gsc_properties: list = []
    ga4_properties: list = []

    if integration:
        access_token = await oauth_service.get_valid_access_token(integration)
        props = await GooglePropertyCacheService(db).get_properties(
            workspace_id=workspace.id,
            access_token=access_token,
            force=force_refresh,
        )
        gsc_properties = props.get("gsc", [])
        ga4_properties = props.get("ga4", [])

    return {
        "sites": sites,
        "gsc_properties": gsc_properties,
        "ga4_properties": ga4_properties,
    }


@router.post("/sites/select", response_model=SuccessResponse[GoogleSiteSelectionResponse])
@db_transaction_handler("select google sites", "Site selection saved")
@require_permissions("content.update", workspace_scoped=True)
async def select_google_sites(
    data: GoogleSiteSelectionUpsert,
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    Declarative batch site-selection: the listed sites get active GSC/GA4
    mappings, any previously mapped sites not in the list are deactivated.
    GA4 properties are validated against the connected Google account before
    saving — if any are invalid the entire request is rejected.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    selections_with_ga4 = [s for s in data.selections if s.ga4_property_id]
    if selections_with_ga4:
        oauth_service = GoogleOAuthService(db)
        integration = await oauth_service.get_active_integration(workspace.id)
        if not integration:
            raise RextValidationException(
                message="Google account is not connected for this workspace."
            )
        access_token = await oauth_service.get_valid_access_token(integration)
        analytics_service = GoogleAnalyticsService(db)
        for sel in selections_with_ga4:
            is_valid = await analytics_service.validate_property(
                access_token, sel.ga4_property_id
            )
            if not is_valid:
                raise RextValidationException(
                    message=(
                        f"Unable to access GA4 property '{sel.ga4_property_id}' with the "
                        "connected Google account. Check the property ID and that the "
                        "account has at least Viewer access."
                    )
                )

    mappings = await GoogleIntegrationService(db).select_sites(
        workspace_id=workspace.id,
        selections=[s.model_dump() for s in data.selections],
    )

    # Populate site-wide dashboard data immediately (best-effort, own
    # session) instead of waiting for the next scheduled sync cycle.
    schedule_site_metrics_sync(workspace.id)

    return {"mappings": [m.to_dict() for m in mappings]}


@router.get(
    "/sites/{site_id}/published-content",
    response_model=SuccessResponse[PublishedContentResponse],
)
@db_transaction_handler("list published content")
@require_permissions("content.read", workspace_scoped=True)
async def list_published_content(
    site_id: UUID,
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    List all published articles on one connected WordPress site, with their
    current analytics-tracking state. Powers the content-selection screen.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))
    await _get_wordpress_site_or_404(db, site_id, workspace.id)

    items = await GoogleIntegrationService(db).list_published_content(site_id)
    return {"site_id": site_id, "items": items}


@router.put(
    "/sites/{site_id}/tracked-content",
    response_model=SuccessResponse[TrackedContentResponse],
)
@db_transaction_handler("update tracked content", "Tracked content updated")
@require_permissions("content.update", workspace_scoped=True)
async def update_tracked_content(
    site_id: UUID,
    data: TrackedContentUpdate,
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    Declarative tracking selection for one site: the listed content IDs will
    be tracked, everything else on the site untracked. Returns counts.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))
    await _get_wordpress_site_or_404(db, site_id, workspace.id)

    result = await GoogleIntegrationService(db).set_tracked_content(
        site_id=site_id, content_ids=data.content_ids
    )
    return {"site_id": site_id, **result}
