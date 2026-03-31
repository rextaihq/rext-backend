"""
Shopify Integration Pydantic Schemas

Request and response models for Shopify store connection management endpoints.
"""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class ShopifyConnectRequest(BaseModel):
    """Request body for connecting a new Shopify store."""

    store_url: str = Field(
        ...,
        description=(
            "Shopify store URL.  Accepts the full myshopify domain "
            "(e.g. 'my-store.myshopify.com') or just the shop name "
            "(e.g. 'my-store')."
        ),
    )
    access_token: str = Field(
        ...,
        description="Shopify Admin API access token (private/custom app).",
    )
    is_active: bool = Field(
        default=True,
        description="Whether this connection is active immediately after creation.",
    )
    config_json: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional extra configuration (stored as JSONB).",
    )

    @field_validator("store_url")
    @classmethod
    def validate_store_url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not v:
            raise ValueError("store_url must not be empty.")
        return v

    @field_validator("access_token")
    @classmethod
    def validate_access_token(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("access_token must not be empty.")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "store_url": "my-store.myshopify.com",
                "access_token": "shpat_xxxxxxxxxxxxxxxxxxxx",
                "is_active": True,
            }
        }
    }


class ShopifyUpdateRequest(BaseModel):
    """Request body for updating an existing Shopify connection."""

    store_url: Optional[str] = Field(
        default=None,
        description="New Shopify store URL.",
    )
    access_token: Optional[str] = Field(
        default=None,
        description="New Shopify Admin API access token.",
    )
    is_active: Optional[bool] = Field(
        default=None,
        description="Toggle connection active state.",
    )
    config_json: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Updated extra configuration.",
    )

    @field_validator("store_url")
    @classmethod
    def validate_store_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip().rstrip("/")
            if not v:
                raise ValueError("store_url must not be empty if provided.")
        return v

    @field_validator("access_token")
    @classmethod
    def validate_access_token(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("access_token must not be empty if provided.")
        return v


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class ShopifyConnectionResponse(BaseModel):
    """Response schema for a single Shopify connection record."""

    id: UUID = Field(..., description="Connection UUID")
    workspace_id: UUID = Field(..., description="Workspace UUID")
    integration_type: str = Field(default="shopify", description="Always 'shopify'")
    store_url: Optional[str] = Field(None, description="Shopify store URL")
    is_active: bool = Field(..., description="Whether the connection is active")
    has_access_token: bool = Field(
        default=False,
        description="Masked indicator: True if an access token is stored.",
    )
    config_json: Optional[Dict[str, Any]] = Field(
        None, description="Extra configuration"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    model_config = {"from_attributes": True}


class ShopifyConnectionListResponse(BaseModel):
    """Response schema for listing Shopify connections."""

    connections: list[ShopifyConnectionResponse]
    total_count: int
    workspace_id: UUID


class ShopifyTestConnectionResponse(BaseModel):
    """Response schema for a connection test."""

    success: bool
    connection_id: UUID
    store_url: str
    shop_info: Optional[Dict[str, Any]] = Field(
        None, description="Basic shop details returned by Shopify (on success)"
    )
    error: Optional[str] = Field(None, description="Error message (on failure)")
