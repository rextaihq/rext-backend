from pydantic import BaseModel, HttpUrl, Field, EmailStr
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime


class ChangeMemberRoleRequest(BaseModel):
    """Request to change a workspace member's role"""
    role_id: str = Field(..., description="UUID of the new role to assign")

    class Config:
        json_schema_extra = {
            "example": {
                "role_id": "123e4567-e89b-12d3-a456-426614174000"
            }
        }


class AddWorkspaceMemberRequest(BaseModel):
    """Request body for adding a member to a workspace."""
    email: EmailStr = Field(..., description="Email address of the user to invite")

    class Config:
        json_schema_extra = {
            "example": {
                "email": "teammate@example.com"
            }
        }


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

    class Config:
        from_attributes = True


# FIXED: Removed brand voice fields - only workspace core fields
class WorkspaceSchema(BaseModel):
    name: Optional[str] = Field(None, description="Optional workspace title")
    timezone: Optional[str] = Field(None, description="IANA timezone identifier (e.g., 'America/New_York', 'UTC')")
    url: Optional[HttpUrl] = Field(None, description="Workspace URL")

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "My Workspace",
                "timezone": "America/New_York",
                "url": "https://example.com"
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
    about: Optional[str] = Field(None, description="About the brand")
    customer_profile: Optional[str] = Field(None, description="Customer profile details")
    selling_position: Optional[str] = Field(None, description="Selling position of the brand")
    target_audience: Optional[List[str]] = Field(default_factory=list, description="Target audience details")
    brand_voice: Optional[List[str]] = Field(default_factory=list, description="Tone and voice of the brand")
    competitors: Optional[List[str]] = Field(default_factory=list, description="Competitors information")
    content_pillar: Optional[List[str]] = Field(default_factory=list, description="Content strategy pillars")


class BrandVoiceResponseSchema(BrandVoiceSchema):
    """Response schema for brand voice with ID"""
    id: UUID = Field(..., description="Brand voice record UUID")
    workspace_id: UUID = Field(..., description="Workspace UUID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    class Config:
        from_attributes = True


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
    content_metrics: Optional[Dict[str, Any]] = None # Detailed word counts etc.


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
    knowledge_stats: Optional[WorkspaceKnowledgeStats] = Field(None, description="Counts of knowledge items")
    members_count: Optional[int] = Field(0, description="Total members")
    brand_voice: Optional[BrandVoiceResponseSchema] = None
    analytics: Optional[WorkspaceAnalyticsSchema] = None

    class Config:
        from_attributes = True


class SidebarWorkspaceSchema(BaseModel):
    """Condensed schema for workspace sidebar selection."""
    id: UUID = Field(..., description="Workspace UUID")
    name: str = Field(..., description="Workspace title")
    slug: str = Field(..., description="URL slug")
    status: str = Field(default="active", description="Workspace status")

    class Config:
        from_attributes = True


class WorkspaceUpdateSchema(BaseModel):
    """Schema for updating workspace metadata."""
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="New workspace name")
    timezone: Optional[str] = Field(None, max_length=50, description="IANA timezone identifier (e.g., America/New_York)")
    url: Optional[str] = Field(None, max_length=2048, description="Workspace website URL")
    