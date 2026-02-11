from pydantic import BaseModel, HttpUrl, Field, EmailStr
from typing import Optional, Dict, Any
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
    id: str = Field(..., description="Membership UUID")
    workspace_id: str = Field(..., description="Workspace UUID")
    user_id: str = Field(..., description="User UUID")
    email: str = Field(..., description="User email")
    full_name: Optional[str] = Field(None, description="User full name")
    role_id: str = Field(..., description="Role UUID")
    role_name: str = Field(..., description="Role name (slug)")
    role_display_name: str = Field(..., description="Role display name")
    status: str = Field(..., description="Membership status")
    joined_at: str = Field(..., description="When user joined workspace")

    class Config:
        from_attributes = True


# FIXED: Removed brand voice fields - only workspace core fields
class WorkspaceSchema(BaseModel):
    """Schema for workspace core fields only."""
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
    owner: Optional[Dict[str, Any]] = Field(None, description="Owner summary")
    knowledge_stats: Optional[Dict[str, Any]] = Field(None, description="Counts of knowledge items")
    members_count: Optional[int] = Field(0, description="Total members")

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


# NEW: Separated schema for brand voice fields
class BrandVoiceSchema(BaseModel):
    """Schema for brand voice and marketing fields."""
    about: Optional[str] = Field(None, description="About the brand")
    customer_profile: Optional[str] = Field(None, description="Customer profile details")
    selling_position: Optional[str] = Field(None, description="Selling position of the brand")
    target_audience: Optional[str] = Field(None, description="Target audience details")
    brand_voice: Optional[str] = Field(None, description="Tone and voice of the brand")
    competitors: Optional[str] = Field(None, description="Competitors information")
    content_strategy: Optional[str] = Field(None, description="Content strategy pillars")

    model_config = {
        "json_schema_extra": {
            "example": {
                "about": "We are a sustainable fashion brand...",
                "customer_profile": "Eco-conscious millennials",
                "selling_position": "Premium sustainable clothing",
                "target_audience": "Ages 25-40, urban professionals",
                "brand_voice": "Friendly, authentic, inspiring",
                "competitors": "Brand A, Brand B",
                "content_strategy": "Sustainability, Fashion Tips, Behind-the-Scenes"
            }
        }
    }


class BrandVoiceResponseSchema(BrandVoiceSchema):
    """Response schema for brand voice with ID"""
    id: UUID = Field(..., description="Brand voice record UUID")
    workspace_id: UUID = Field(..., description="Workspace UUID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    class Config:
        from_attributes = True


class WorkspaceUpdateSchema(BaseModel):
    """Request body for updating workspace details."""
    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="New workspace name",
    )
    timezone: Optional[str] = Field(
        None,
        max_length=50,
        description="IANA timezone identifier (e.g., 'America/New_York', 'UTC')",
    )
    url: Optional[HttpUrl] = Field(
        None,
        description="Workspace website URL",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "My Workspace",
                "timezone": "America/New_York",
                "url": "https://example.com",
            }
        }
    }


# NEW: Schema for updating brand voice separately
class BrandVoiceUpdateSchema(BaseModel):
    """Request body for updating brand voice details."""
    about: Optional[str] = Field(None, max_length=2000, description="About the brand")
    customer_profile: Optional[str] = Field(None, max_length=1000, description="Customer profile details")
    selling_position: Optional[str] = Field(None, max_length=500, description="Selling position of the brand")
    target_audience: Optional[str] = Field(None, max_length=1000, description="Target audience details")
    brand_voice: Optional[str] = Field(None, max_length=500, description="Tone and voice of the brand")
    competitors: Optional[str] = Field(None, max_length=1000, description="Competitors information")
    content_strategy: Optional[str] = Field(None, max_length=2000, description="Content strategy pillars")

    model_config = {
        "json_schema_extra": {
            "example": {
                "about": "We are a sustainable fashion brand...",
                "customer_profile": "Eco-conscious millennials",
                "selling_position": "Premium sustainable clothing",
                "target_audience": "Ages 25-40, urban professionals",
                "brand_voice": "Friendly, authentic, inspiring",
                "competitors": "Brand A, Brand B",
                "content_strategy": "Sustainability, Fashion Tips, Behind-the-Scenes"
            }
        }
    }