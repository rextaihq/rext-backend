"""
Google Analytics Integration Routes

OAuth and connection management endpoints for Google Search Console and Analytics 4 integration.
"""

import uuid
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config import settings
from src.api.database.async_database import get_async_db as get_db
from src.api.middleware.exceptions import RextValidationException
from src.api.middleware.permissions import PermissionChecker
from src.api.security.dependencies import get_current_user
from src.utils.response_utils import success
from src.utils.logger import logger

from src.services.google_oauth_service import GoogleOAuthService
from src.api.schema.integrations.google_schema import (
    GoogleConnectStartRequest,
    GoogleOAuthCallbackResponse,
    GoogleSelectionsRequest,
    GoogleConnectionStatus,
    GoogleSiteResponse,
    GooglePropertyResponse,
)
from src.services.google_connection_service import GoogleConnectionService
from src.services.google_metrics_service import GoogleMetricsService


router = APIRouter(prefix="/google", tags=["Google Analytics Integration"])


@router.post("/connect/start")
async def start_google_oauth(
    workspace_id: uuid.UUID,
    data: GoogleConnectStartRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(PermissionChecker(["user.read"], workspace_scoped=True)),
):
    """
    Start Google OAuth flow for GSC and GA4 integration.
    
    Returns the Google OAuth URL that the frontend should redirect the user to.
    After the user authorizes, Google will redirect back to the callback endpoint.
    """
    service = GoogleOAuthService(db)
    
    user_id = current_user.get("identity")
    if not user_id:
        raise RextValidationException(message="Authenticated user identity is missing.")
    
    try:
        user_id = uuid.UUID(user_id)
    except (ValueError, TypeError):
        raise RextValidationException(message="Invalid user identity format.")
    
    oauth_url = await service.build_oauth_url(
        workspace_id=workspace_id,
        user_id=user_id,
        return_path=data.return_path,
    )
    
    logger.info(
        f"Generated Google OAuth URL for workspace {workspace_id}",
        extra={"workspace_id": str(workspace_id), "user_id": str(user_id)}
    )
    
    return success(
        data={"oauth_url": oauth_url},
        message="Google OAuth URL generated successfully",
    )


@router.get("/connect/callback", name="google_oauth_callback")
async def google_oauth_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(..., description="JWT-signed state parameter"),
    error: str = Query(None, description="Error from Google OAuth"),
    db: AsyncSession = Depends(get_db),
):
    """
    Handle Google OAuth callback and redirect back to the frontend.
    
    This endpoint receives the authorization code from Google, exchanges it for
    access and refresh tokens, stores them in the database, and redirects the
    user back to the frontend with a status message.
    
    This is called by Google's OAuth service, not directly by the frontend.
    """
    service = GoogleOAuthService(db)
    
    # Handle OAuth errors from Google
    if error:
        logger.error(f"Google OAuth error: {error}")
        redirect_url = f"{settings.FRONTEND_URL}{settings.GOOGLE_INTEGRATION_RETURN_PATH}?status=error&message={error}"
        return RedirectResponse(url=redirect_url, status_code=302)
    
    try:
        # Handle OAuth callback and store tokens
        result = await service.handle_oauth_callback(code=code, state=state)
        await db.commit()
        
        workspace_id = result["workspace_id"]
        return_path = result["return_path"]
        
        # Build success redirect URL
        redirect_url = f"{settings.FRONTEND_URL}{return_path}?status=success&workspace_id={workspace_id}"
        
        logger.info(
            f"Google OAuth completed successfully for workspace {workspace_id}",
            extra={"workspace_id": str(workspace_id)}
        )
        
    except Exception as exc:
        logger.error(f"Google OAuth callback error: {str(exc)}", exc_info=True)
        # Build error redirect URL
        error_message = str(exc)
        redirect_url = f"{settings.FRONTEND_URL}{settings.GOOGLE_INTEGRATION_RETURN_PATH}?status=error&message={error_message}"
    
    return RedirectResponse(url=redirect_url, status_code=302)


@router.get("/gsc/sites", response_model=dict)
async def list_gsc_sites(
    workspace_id: uuid.UUID = Query(..., description="Workspace UUID"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(PermissionChecker(["user.read"], workspace_scoped=True)),
):
    """List available Google Search Console sites for the workspace."""
    service = GoogleConnectionService(db)
    sites = await service.list_gsc_sites(workspace_id)
    return success(data={"sites": sites})


@router.get("/ga4/properties", response_model=dict)
async def list_ga4_properties(
    workspace_id: uuid.UUID = Query(..., description="Workspace UUID"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(PermissionChecker(["user.read"], workspace_scoped=True)),
):
    """List available GA4 properties and optionally auto-suggest a GSC site."""
    service = GoogleConnectionService(db)
    properties = await service.list_ga4_properties(workspace_id)
    suggested_site = await service.auto_suggest_gsc_site(workspace_id)
    
    return success(data={
        "properties": properties,
        "suggested_gsc_site": suggested_site
    })


@router.post("/connect/select", response_model=dict)
async def save_google_selections(
    workspace_id: uuid.UUID = Query(..., description="Workspace UUID"),
    data: GoogleSelectionsRequest = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(PermissionChecker(["user.update"], workspace_scoped=True)),
):
    """Save selected GSC site and GA4 property for the workspace."""
    service = GoogleConnectionService(db)
    await service.save_selections(
        workspace_id=workspace_id,
        gsc_site_url=data.gsc_site_url,
        ga4_property_id=data.ga4_property_id
    )
    await db.commit()
    return success(message="Google selections saved successfully")


@router.get("/status", response_model=dict)
async def get_google_connection_status(
    workspace_id: uuid.UUID = Query(..., description="Workspace UUID"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(PermissionChecker(["user.read"], workspace_scoped=True)),
):
    """Get the current Google connection status for the workspace."""
    service = GoogleConnectionService(db)
    status = await service.get_connection_status(workspace_id)
    return success(data=status)


@router.delete("/disconnect", response_model=dict)
async def disconnect_google(
    workspace_id: uuid.UUID = Query(..., description="Workspace UUID"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(PermissionChecker(["user.update"], workspace_scoped=True)),
):
    """Disconnect Google integration for the workspace."""
    service = GoogleConnectionService(db)
    disconnected = await service.disconnect(workspace_id)
    await db.commit()
    
    if disconnected:
        return success(message="Google integration disconnected successfully")
    return success(message="No Google connection found to disconnect")


@router.get("/metrics", response_model=dict)
async def get_google_metrics(
    workspace_id: uuid.UUID = Query(..., description="Workspace UUID"),
    article_id: uuid.UUID = Query(None, description="Filter by specific article"),
    source: str = Query(None, description="Filter by source (gsc or ga4)"),
    start_date: str = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(50, description="Pagination limit"),
    offset: int = Query(0, description="Pagination offset"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(PermissionChecker(["user.read"], workspace_scoped=True)),
):
    """Get paginated Google Analytics and Search Console metrics."""
    service = GoogleMetricsService(db)
    result = await service.get_metrics(
        workspace_id=workspace_id,
        article_id=article_id,
        source=source,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset
    )
    return success(data=result)


@router.get("/articles/summary", response_model=dict)
async def get_google_article_summary(
    workspace_id: uuid.UUID = Query(..., description="Workspace UUID"),
    start_date: str = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(None, description="End date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(PermissionChecker(["user.read"], workspace_scoped=True)),
):
    """Get aggregated metrics grouped by article."""
    service = GoogleMetricsService(db)
    summary = await service.get_article_summary(
        workspace_id=workspace_id,
        start_date=start_date,
        end_date=end_date
    )
    return success(data={"summaries": summary})


@router.get("/articles/{article_id}/queries", response_model=dict)
async def get_google_article_queries(
    article_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(..., description="Workspace UUID"),
    start_date: str = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(20, description="Pagination limit"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(PermissionChecker(["user.read"], workspace_scoped=True)),
):
    """Get top Google Search Console queries for a specific article."""
    service = GoogleMetricsService(db)
    queries = await service.get_top_queries(
        workspace_id=workspace_id,
        article_id=article_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit
    )
    return success(data={"queries": queries})
