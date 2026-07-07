"""
Google Analytics Integration Pydantic Schemas

Request and response models for Google Search Console and Analytics 4 integration endpoints.
"""

from datetime import datetime
from typing import Optional
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class GoogleConnectStartRequest(BaseModel):
    """Request body for starting the Google OAuth flow."""

    return_path: Optional[str] = Field(
        default=None,
        description="Optional frontend path to return to after OAuth completes.",
    )

    @field_validator("return_path")
    @classmethod
    def validate_return_path(cls, v: Optional[str]) -> Optional[str]:
        """Validate return_path is a relative frontend path."""
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        parsed = urlparse(v)
        if parsed.scheme or parsed.netloc:
            raise ValueError(
                "return_path must be a relative frontend path like '/w/my-workspace/integrations'."
            )
        if not v.startswith("/"):
            v = f"/{v}"
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "return_path": "/w/my-workspace/integrations",
            }
        }
    }


class GoogleSelectionsRequest(BaseModel):
    """Request body for saving selected GSC site and GA4 property."""

    gsc_site_url: str = Field(
        ...,
        description="Selected Google Search Console site URL (e.g., https://example.com/)",
    )
    ga4_property_id: str = Field(
        ...,
        description="Selected GA4 property ID (e.g., properties/123456789)",
    )

    @field_validator("gsc_site_url")
    @classmethod
    def validate_gsc_site_url(cls, v: str) -> str:
        """Validate GSC site URL is not empty."""
        v = v.strip()
        if not v:
            raise ValueError("gsc_site_url must not be empty.")
        return v

    @field_validator("ga4_property_id")
    @classmethod
    def validate_ga4_property_id(cls, v: str) -> str:
        """Validate GA4 property ID is not empty."""
        v = v.strip()
        if not v:
            raise ValueError("ga4_property_id must not be empty.")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "gsc_site_url": "https://example.com/",
                "ga4_property_id": "properties/123456789",
            }
        }
    }


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class GoogleConnectionStatus(BaseModel):
    """Response schema for Google integration connection status."""

    is_connected: bool = Field(
        ...,
        description="Whether the workspace has an active Google connection",
    )
    gsc_site_url: Optional[str] = Field(
        None,
        description="Selected Google Search Console site URL",
    )
    ga4_property_id: Optional[str] = Field(
        None,
        description="Selected GA4 property ID",
    )
    last_synced_at: Optional[datetime] = Field(
        None,
        description="Last successful incremental sync timestamp",
    )
    last_backfill_completed_at: Optional[datetime] = Field(
        None,
        description="Timestamp when 16-month backfill completed",
    )
    oauth_account_email: Optional[str] = Field(
        None,
        description="Email address of the connected Google account",
    )

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "is_connected": True,
                "gsc_site_url": "https://example.com/",
                "ga4_property_id": "properties/123456789",
                "last_synced_at": "2024-01-15T10:30:00Z",
                "last_backfill_completed_at": "2024-01-10T08:00:00Z",
                "oauth_account_email": "user@example.com",
            }
        }
    }


class GoogleSiteResponse(BaseModel):
    """Response schema for a single GSC site."""

    site_url: str = Field(..., description="GSC site URL")
    permission_level: str = Field(
        ...,
        description="Permission level (e.g., 'owner', 'full', 'restricted')",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "site_url": "https://example.com/",
                "permission_level": "owner",
            }
        }
    }


class GooglePropertyResponse(BaseModel):
    """Response schema for a single GA4 property."""

    property_id: str = Field(..., description="GA4 property ID")
    display_name: str = Field(..., description="Display name of the property")
    property_type: str = Field(
        ...,
        description="Property type (e.g., 'PROPERTY_TYPE_ORDINARY')",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "property_id": "properties/123456789",
                "display_name": "My Website",
                "property_type": "PROPERTY_TYPE_ORDINARY",
            }
        }
    }


class GoogleOAuthCallbackResponse(BaseModel):
    """Response schema for OAuth callback (used internally for redirects)."""

    success: bool = Field(..., description="Whether OAuth callback succeeded")
    workspace_id: Optional[UUID] = Field(None, description="Workspace UUID")
    redirect_url: str = Field(..., description="Frontend URL to redirect to")
    error: Optional[str] = Field(None, description="Error message (on failure)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "workspace_id": "550e8400-e29b-41d4-a716-446655440000",
                "redirect_url": "https://app.example.com/w/my-workspace/integrations?status=success",
                "error": None,
            }
        }
    }
