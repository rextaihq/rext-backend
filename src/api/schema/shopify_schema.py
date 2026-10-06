"""
Shopify Integration Pydantic Schemas

Request and response models for Shopify store connection management endpoints.
"""

from typing import Any, Dict, Optional
from urllib.parse import urlparse

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
    access_token: Optional[str] = Field(
        default=None,
        description="Optional Shopify Admin API access token (legacy token flow).",
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
    def validate_access_token(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("access_token must not be empty if provided.")
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


class ShopifyInstallStartRequest(BaseModel):
    """Request body for starting the Shopify app installation flow."""

    store_url: str = Field(
        ...,
        description="Shopify store URL or bare store handle.",
    )
    return_path: Optional[str] = Field(
        default=None,
        description="Optional frontend path to return to after installation.",
    )

    @field_validator("store_url")
    @classmethod
    def validate_install_store_url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not v:
            raise ValueError("store_url must not be empty.")
        return v

    @field_validator("return_path")
    @classmethod
    def validate_return_path(cls, v: Optional[str]) -> Optional[str]:
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


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------
