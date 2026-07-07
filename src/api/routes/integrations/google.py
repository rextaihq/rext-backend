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
    GoogleConnectResponse,
    GoogleIntegrationStatusResponse,
    GoogleSiteMappingResponse,
    GoogleSiteMappingUpsert,
    SearchConsoleSitesResponse,
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services.google_analytics_service import GoogleAnalyticsService
from src.services.google_integration_service import GoogleIntegrationService
from src.services.google_oauth_service import GoogleOAuthService
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
