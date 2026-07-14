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


class GA4PropertySummary(BaseModel):
    """One GA4 property from the Analytics Admin API accountSummaries.list."""
    property_id: str  # e.g. "properties/123456789"
    display_name: Optional[str] = None
    account_display_name: Optional[str] = None


class GA4PropertiesResponse(BaseModel):
    properties: List[GA4PropertySummary]


class ContentPerformanceResponse(BaseModel):
    """Stored GSC + GA4 daily metrics for a single content item."""
    content_id: UUID
    search_console: List[Dict[str, Any]]
    analytics: List[Dict[str, Any]]


# ============================================================================
# Onboarding flow (setup status, site selection, content selection)
# ============================================================================

class GoogleSetupStatusResponse(BaseModel):
    """Where the workspace is in the Google onboarding flow."""
    google_connected: bool
    wordpress_sites: int = 0
    selected_sites: int = 0
    tracked_content: int = 0
    last_synced_at: Optional[datetime] = None
    step: str  # connect_google | select_site | select_content | ready


class GscPropertyEntry(BaseModel):
    site_url: str
    permission_level: Optional[str] = None


class GoogleSiteOverview(BaseModel):
    """One connected WordPress site with its current GSC/GA4 mapping."""
    site_id: UUID
    site_url: Optional[str] = None
    is_active: bool
    mapping: Optional[GoogleSiteMappingResponse] = None


class GoogleSitesOverviewResponse(BaseModel):
    """Everything the site-selection screen needs in one call."""
    sites: List[GoogleSiteOverview]
    gsc_properties: List[GscPropertyEntry]
    ga4_properties: List[GA4PropertySummary]


class GoogleSiteSelectionEntry(BaseModel):
    site_id: UUID
    gsc_site_url: Optional[str] = None
    ga4_property_id: Optional[str] = None


class GoogleSiteSelectionUpsert(BaseModel):
    """Declarative site selection: listed sites get mapped, others deactivated."""
    selections: List[GoogleSiteSelectionEntry]


class GoogleSiteSelectionResponse(BaseModel):
    mappings: List[GoogleSiteMappingResponse]


class PublishedContentItem(BaseModel):
    """One published article on a site, with its tracking state."""
    content_id: UUID
    publishing_result_id: UUID
    title: Optional[str] = None
    external_url: Optional[str] = None
    published_at: Optional[datetime] = None
    tracked: bool = False


class PublishedContentResponse(BaseModel):
    site_id: UUID
    items: List[PublishedContentItem]


class TrackedContentUpdate(BaseModel):
    """Declarative tracking selection: listed content tracked, rest untracked."""
    content_ids: List[UUID]


class TrackedContentResponse(BaseModel):
    site_id: UUID
    tracked_count: int
    untracked_count: int
