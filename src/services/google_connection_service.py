"""
Google Connection Service

Manages workspace connections to Google Search Console and GA4 properties.
"""

import uuid
from typing import List, Dict, Any, Optional
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.api.models.integrations.workspace_google_connection import WorkspaceGoogleConnection
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.user_models.oauth_accounts import OAuthAccount
from src.services.google_oauth_service import GoogleOAuthService
from src.utils.url_normalizer import normalize_url
from src.api.middleware.exceptions import RextValidationException, ResourceNotFoundException
from src.utils.logger import logger


class GoogleConnectionService:
    """Service for managing workspace connections to Google."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.oauth_service = GoogleOAuthService(db)

    async def list_gsc_sites(self, workspace_id: uuid.UUID) -> List[Dict[str, Any]]:
        """List available Google Search Console sites for the workspace's connected account."""
        token = await self.oauth_service.get_valid_token(workspace_id)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://www.googleapis.com/webmasters/v3/sites",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
                
                sites = data.get("siteEntry", [])
                return [
                    {
                        "site_url": site.get("siteUrl"),
                        "permission_level": site.get("permissionLevel"),
                    }
                    for site in sites
                ]
        except httpx.HTTPStatusError as e:
            logger.error(f"GSC API error: {e.response.text}")
            raise RextValidationException(f"Failed to fetch GSC sites: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Failed to list GSC sites: {str(e)}")
            raise RextValidationException(f"Error fetching GSC sites: {str(e)}")

    async def list_ga4_properties(self, workspace_id: uuid.UUID) -> List[Dict[str, Any]]:
        """List available GA4 properties for the workspace's connected account."""
        token = await self.oauth_service.get_valid_token(workspace_id)

        try:
            async with httpx.AsyncClient() as client:
                # GA4 Admin API requires account summaries to find properties efficiently
                response = await client.get(
                    "https://analyticsadmin.googleapis.com/v1beta/accountSummaries",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
                
                properties = []
                for summary in data.get("accountSummaries", []):
                    for prop in summary.get("propertySummaries", []):
                        properties.append({
                            "property_id": prop.get("property"),
                            "display_name": prop.get("displayName"),
                            "property_type": prop.get("propertyType"),
                        })
                return properties
        except httpx.HTTPStatusError as e:
            logger.error(f"GA4 Admin API error: {e.response.text}")
            raise RextValidationException(f"Failed to fetch GA4 properties: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Failed to list GA4 properties: {str(e)}")
            raise RextValidationException(f"Error fetching GA4 properties: {str(e)}")

    async def auto_suggest_gsc_site(self, workspace_id: uuid.UUID) -> Optional[str]:
        """Auto-suggest GSC site URL based on workspace URL."""
        # Get workspace URL
        workspace_result = await self.db.execute(
            select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)
        )
        workspace = workspace_result.scalar_one_or_none()
        
        if not workspace or not workspace.url:
            return None

        normalized_workspace_url = normalize_url(workspace.url)
        if not normalized_workspace_url:
            return None

        # Get available sites
        try:
            sites = await self.list_gsc_sites(workspace_id)
            for site in sites:
                site_url = site.get("site_url")
                if site_url:
                    normalized_site = normalize_url(site_url)
                    if normalized_site == normalized_workspace_url or normalized_site.startswith(normalized_workspace_url):
                        return site_url
        except Exception as e:
            logger.warning(f"Failed to auto-suggest GSC site for workspace {workspace_id}: {str(e)}")

        return None

    async def save_selections(
        self,
        workspace_id: uuid.UUID,
        gsc_site_url: str,
        ga4_property_id: str,
    ) -> WorkspaceGoogleConnection:
        """Save selected GSC site and GA4 property for the workspace."""
        # Check if connection exists
        result = await self.db.execute(
            select(WorkspaceGoogleConnection).where(
                WorkspaceGoogleConnection.workspace_id == workspace_id
            )
        )
        connection = result.scalar_one_or_none()

        if not connection:
            raise ResourceNotFoundException(
                resource_type="GoogleConnection",
                resource_id=str(workspace_id),
                message="No Google connection found. Please authenticate first."
            )

        # Update connection
        connection.gsc_site_url = gsc_site_url
        connection.ga4_property_id = ga4_property_id

        await self.db.flush()
        
        # Trigger background job for historical backfill if first connection
        if not connection.last_backfill_completed_at:
            from src.tasks.scheduled_tasks import task_manager
            from src.tasks.google_backfill_task import run_google_backfill_task
            
            if task_manager.scheduler:
                task_manager.scheduler.add_job(
                    run_google_backfill_task,
                    args=[workspace_id],
                    id=f"google_backfill_{workspace_id}",
                    name=f"Google Analytics Backfill for {workspace_id}",
                    replace_existing=True,
                )
                logger.info(f"Scheduled backfill job for workspace {workspace_id}")
        
        logger.info(
            f"Saved Google selections for workspace {workspace_id}",
            extra={
                "workspace_id": str(workspace_id),
                "gsc_site_url": gsc_site_url,
                "ga4_property_id": ga4_property_id
            }
        )
        
        return connection

    async def get_connection_status(self, workspace_id: uuid.UUID) -> Dict[str, Any]:
        """Get the Google integration connection status for a workspace."""
        result = await self.db.execute(
            select(WorkspaceGoogleConnection)
            .options(selectinload(WorkspaceGoogleConnection.oauth_account))
            .where(WorkspaceGoogleConnection.workspace_id == workspace_id)
        )
        connection = result.scalar_one_or_none()

        if not connection:
            return {
                "is_connected": False,
                "gsc_site_url": None,
                "ga4_property_id": None,
                "last_synced_at": None,
                "last_backfill_completed_at": None,
                "oauth_account_email": None,
            }

        return {
            "is_connected": True,
            "gsc_site_url": connection.gsc_site_url,
            "ga4_property_id": connection.ga4_property_id,
            "last_synced_at": connection.last_synced_at,
            "last_backfill_completed_at": connection.last_backfill_completed_at,
            "oauth_account_email": connection.oauth_account.provider_account_email if connection.oauth_account else None,
        }

    async def disconnect(self, workspace_id: uuid.UUID) -> bool:
        """Disconnect Google integration for a workspace."""
        result = await self.db.execute(
            select(WorkspaceGoogleConnection).where(
                WorkspaceGoogleConnection.workspace_id == workspace_id
            )
        )
        connection = result.scalar_one_or_none()

        if connection:
            # We keep the OAuthAccount in case it's used elsewhere or they reconnect
            # Delete only the WorkspaceGoogleConnection
            await self.db.delete(connection)
            await self.db.flush()
            
            logger.info(
                f"Disconnected Google integration for workspace {workspace_id}",
                extra={"workspace_id": str(workspace_id)}
            )
            return True
            
        return False
