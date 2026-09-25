import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator

# Mirrors the frontend's domain validation (rext-admin/schemas/workspace-schemas.ts)
# so an HttpUrl without a real TLD (e.g. "https://example") is rejected on both sides.
_DOMAIN_WITH_TLD_RE = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$"
)

FORBIDDEN_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
FORBIDDEN_IP_PREFIXES = (
    "10.",
    "172.16.",
    "172.17.",
    "172.18.",
    "172.19.",
    "172.20.",
    "172.21.",
    "172.22.",
    "172.23.",
    "172.24.",
    "172.25.",
    "172.26.",
    "172.27.",
    "172.28.",
    "172.29.",
    "172.30.",
    "172.31.",
    "192.168.",
)


def _validate_workspace_url(value: Any) -> Any:
    if value is None or value == "":
        return value

    val_str = str(value).strip()
    if not val_str:
        return value

    # Prepend https:// if missing scheme
    if not re.match(r"^https?://", val_str, re.IGNORECASE):
        val_str = f"https://{val_str}"

    from urllib.parse import urlparse
    parsed = urlparse(val_str)
    hostname = (parsed.hostname or "").lower()

    if not hostname:
        raise ValueError("URL must contain a valid domain name")

    if hostname in FORBIDDEN_HOSTS or any(hostname.startswith(p) for p in FORBIDDEN_IP_PREFIXES):
        raise ValueError("Localhost and private IP addresses are not permitted for workspace URLs")

    if not _DOMAIN_WITH_TLD_RE.match(hostname):
        raise ValueError("URL must contain a valid domain with a top-level domain (e.g. .com)")

    return val_str


def _validate_competitors_list(v: Any) -> List[str]:
    if not v:
        return []
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list):
        raise ValueError("Competitors must be a list of strings")

    sanitized_list: List[str] = []
    seen_lower = set()

    for item in v:
        if not item or not isinstance(item, str):
            continue
        item_str = item.strip()
        if not item_str:
            continue

        # If user entered a full URL, clean/extract domain
        if re.match(r"^https?://", item_str, re.IGNORECASE) or item_str.startswith("www."):
            try:
                url_to_parse = item_str if re.match(r"^https?://", item_str, re.IGNORECASE) else f"https://{item_str}"
                from urllib.parse import urlparse
                parsed = urlparse(url_to_parse)
                if parsed.hostname:
                    item_str = re.sub(r"^www\.", "", parsed.hostname, flags=re.IGNORECASE)
            except Exception:
                pass

        # Strip script blocks completely
        item_str = re.sub(r"<script.*?>.*?</script>", "", item_str, flags=re.IGNORECASE | re.DOTALL)
        # Strip remaining HTML / script tags
        item_str = re.sub(r"<[^>]*>", "", item_str).strip()

        if len(item_str) < 2:
            continue
        if len(item_str) > 100:
            item_str = item_str[:100].strip()

        lower = item_str.lower()
        if lower not in seen_lower:
            seen_lower.add(lower)
            sanitized_list.append(item_str)

    if len(sanitized_list) > 20:
        raise ValueError("Maximum of 20 competitors allowed per workspace")

    return sanitized_list


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


class WorkspaceMemberResponse(BaseModel):
    """Schema for workspace member response"""

    id: UUID = Field(..., description="Membership UUID")
    workspace_id: UUID = Field(..., description="Workspace UUID")
    user_id: UUID = Field(..., description="User UUID")
    email: str = Field(..., description="User email")
    full_name: Optional[str] = Field(None, description="User full name")
    role_id: UUID = Field(..., description="Role UUID")
    role_name: str = Field(..., description="Role name (slug)")
    role_display_name: str = Field(..., description="Role display name")
    status: str = Field(..., description="Membership status")
    joined_at: datetime = Field(..., description="When user joined workspace")

    model_config = ConfigDict(from_attributes=True)


# FIXED: Removed brand voice fields - only workspace core fields
class WorkspaceSchema(BaseModel):
    name: Optional[str] = Field(None, description="Optional workspace title")
    timezone: Optional[str] = Field(
        None, description="IANA timezone identifier (e.g., 'America/New_York', 'UTC')"
    )
    url: HttpUrl = Field(..., description="Workspace URL")

    _validate_url = field_validator("url", mode="before")(_validate_workspace_url)

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

    _validate_competitors = field_validator("competitors", mode="before")(_validate_competitors_list)


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
    status: str = Field(default="active", description="Workspace status")
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


class SidebarWorkspaceSchema(BaseModel):
    """Condensed schema for workspace sidebar selection."""

    id: UUID = Field(..., description="Workspace UUID")
    name: str = Field(..., description="Workspace title")
    slug: str = Field(..., description="URL slug")
    status: str = Field(default="active", description="Workspace status")

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

    _validate_url = field_validator("url", mode="before")(_validate_workspace_url)
