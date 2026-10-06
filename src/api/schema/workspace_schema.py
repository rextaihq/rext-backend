import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator

from src.utils.name_utils import validate_workspace_name

# Mirrors the frontend's domain validation (rext-admin/schemas/workspace-schemas.ts)
# so an HttpUrl without a real TLD (e.g. "https://example") is rejected on both sides.
_DOMAIN_WITH_TLD_RE = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$"
)


def _validate_workspace_url(value: Optional[HttpUrl]) -> Optional[HttpUrl]:
    if value is None:
        return value
    if value.scheme != "https":
        raise ValueError("URL must start with https://")
    hostname = value.host or ""
    if not _DOMAIN_WITH_TLD_RE.match(hostname):
        raise ValueError("URL must contain a valid domain with a top-level domain (e.g. .com)")
    return value


class ChangeMemberRoleRequest(BaseModel):
    """Request to change a workspace member's role"""

    role_id: str = Field(..., description="UUID of the new role to assign")

    model_config = ConfigDict(
        json_schema_extra={"example": {"role_id": "123e4567-e89b-12d3-a456-426614174000"}}
    )


class AddWorkspaceMemberRequest(BaseModel):
    """Request body for adding a member to a workspace."""

    email: EmailStr = Field(..., description="Email address of the user to invite")

    model_config = ConfigDict(json_schema_extra={"example": {"email": "teammate@example.com"}})


# FIXED: Removed brand voice fields - only workspace core fields
class WorkspaceSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Workspace title")
    timezone: Optional[str] = Field(
        None, description="IANA timezone identifier (e.g., 'America/New_York', 'UTC')"
    )
    url: HttpUrl = Field(..., description="Workspace URL")

    _validate_url = field_validator("url")(_validate_workspace_url)
    _validate_name = field_validator("name")(validate_workspace_name)

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "My Workspace",
                "timezone": "America/New_York",
                "url": "https://example.com",
            }
        }
    }


class WorkspaceOwnerSummary(BaseModel):
    """Structured owner summary embedded in workspace responses."""

    id: UUID
    full_name: Optional[str] = None
    name: Optional[str] = None  # Alias for full_name for frontend compatibility
    email: str
    avatar_url: Optional[str] = None


# NEW: Separated schema for brand voice fields
class BrandVoiceSchema(BaseModel):
    """Schema for brand voice and marketing fields."""

    brand_name: Optional[str] = Field(None, description="The actual brand/product name")
    about: Optional[str] = Field(None, description="About the brand")
    customer_profile: Optional[str] = Field(None, description="Customer profile details")
    selling_position: Optional[str] = Field(None, description="Selling position of the brand")
    target_audience: Optional[List[str]] = Field(
        default_factory=list, description="Target audience details"
    )
    brand_voice: Optional[List[str]] = Field(
        default_factory=list, description="Tone and voice of the brand"
    )
    competitors: Optional[List[str]] = Field(
        default_factory=list, description="Competitors information"
    )
    content_pillar: Optional[List[str]] = Field(
        default_factory=list, description="Content strategy pillars"
    )


class BrandVoiceResponseSchema(BrandVoiceSchema):
    """Response schema for brand voice with ID"""

    id: UUID = Field(..., description="Brand voice record UUID")
    workspace_id: UUID = Field(..., description="Workspace UUID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    model_config = ConfigDict(from_attributes=True)


class WorkspaceKnowledgeStats(BaseModel):
    """Knowledge item counts for a workspace."""

    web_count: int = Field(0, description="Web knowledge items")
    file_count: int = Field(0, description="File knowledge items")
    text_count: int = Field(0, description="Text knowledge items")
    total_count: int = Field(0, description="Total knowledge items")


class WorkspaceAnalyticsSchema(BaseModel):
    """Comprehensive analytics for a workspace."""

    knowledge_stats: WorkspaceKnowledgeStats
    members_count: int = 0
    content_count: int = 0
    topics_count: int = 0
    content_metrics: Optional[Dict[str, Any]] = None  # Detailed word counts etc.


class WorkspaceResponseSchema(BaseModel):
    """Full workspace response with ID and metadata"""

    id: UUID = Field(..., description="Workspace UUID")
    user_id: UUID = Field(..., description="Owner UUID")
    name: str = Field(..., description="Workspace title")
    slug: str = Field(..., description="URL slug")
    timezone: Optional[str] = Field(None, description="Timezone")
    url: Optional[str] = Field(None, description="Website URL")
    favicon_url: Optional[str] = Field(
        None, description="The site's favicon, fetched once and kept in the media store"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    # Optional nested data
    owner: Optional[WorkspaceOwnerSummary] = Field(None, description="Owner summary")
    knowledge_stats: Optional[WorkspaceKnowledgeStats] = Field(
        None, description="Counts of knowledge items"
    )
    members_count: Optional[int] = Field(0, description="Total members")
    brand_voice: Optional[BrandVoiceResponseSchema] = None
    analytics: Optional[WorkspaceAnalyticsSchema] = None

    model_config = ConfigDict(from_attributes=True)


class WorkspaceTransferOwnershipSchema(BaseModel):
    """Schema for handing a workspace to another member."""

    new_owner_user_id: UUID = Field(..., description="User ID of the member to become owner")


class WorkspaceUpdateSchema(BaseModel):
    """Schema for updating workspace metadata."""

    name: Optional[str] = Field(
        None, min_length=1, max_length=255, description="New workspace name"
    )
    timezone: Optional[str] = Field(
        None, max_length=50, description="IANA timezone identifier (e.g., America/New_York)"
    )
    url: Optional[HttpUrl] = Field(None, description="Workspace URL")

    _validate_url = field_validator("url")(_validate_workspace_url)
    _validate_name = field_validator("name")(validate_workspace_name)
