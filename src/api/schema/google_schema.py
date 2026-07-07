from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class GoogleConnectResponse(BaseModel):
    """Response for GET /google/connect"""
    authorization_url: str


class GoogleIntegrationStatusResponse(BaseModel):
    """Connection status for the workspace's Google account (tokens never included)."""
    model_config = ConfigDict(from_attributes=True)

    connected: bool
    google_account_email: Optional[str] = None
    scopes: Optional[str] = None
    is_active: bool = False
    connected_at: Optional[datetime] = None
    last_refreshed_at: Optional[datetime] = None


class GoogleSiteMappingUpsert(BaseModel):
    """Request schema for setting the GSC/GA4 mapping of a connected WordPress site."""
    gsc_site_url: Optional[str] = None
    ga4_property_id: Optional[str] = None
    is_active: bool = True


class GoogleSiteMappingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    site_id: UUID
    gsc_site_url: Optional[str] = None
    ga4_property_id: Optional[str] = None
    is_active: bool
    last_synced_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class SearchConsoleSiteEntry(BaseModel):
    """One entry from the Search Console sites.list API."""
    siteUrl: str
    permissionLevel: Optional[str] = None


class SearchConsoleSitesResponse(BaseModel):
    sites: List[SearchConsoleSiteEntry]


class ContentPerformanceResponse(BaseModel):
    """Stored GSC + GA4 daily metrics for a single content item."""
    content_id: UUID
    search_console: List[Dict[str, Any]]
    analytics: List[Dict[str, Any]]
