from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from uuid import UUID


class ContentBase(BaseModel):
    """Base content schema with common fields"""
    title: str = Field(..., min_length=1, max_length=500, description="Content title")
    content_language: Optional[str] = Field(default="English", description="Content language")
    status: Optional[str] = Field(default="draft", description="Content status")

    @field_validator('title')
    @classmethod
    def validate_title(cls, v):
        if not v or not v.strip():
            raise ValueError('Title cannot be empty')
        return v.strip()


class ContentSEODataSchema(BaseModel):
    """SEO data schema for separate table"""
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    focus_keyphrase: Optional[str] = None
    keyphrase_density: Optional[float] = None
    secondary_keywords: Optional[List[str]] = None
    search_intent: Optional[List[str]] = None
    seo_score: Optional[float] = None
    readability_score: Optional[float] = None
    trust_score: Optional[float] = None
    seo_details: Optional[str] = None


class ContentMediaSchema(BaseModel):
    """Media usage schema for content"""
    media_id: UUID
    usage_type: Optional[str] = "inline"
    position: Optional[int] = 0


class ContentCreate(ContentBase):
    """Schema for creating content with nested data"""
    workspace_id: Optional[Any] = Field(None, description="Workspace ID (UUID or slug)")
    
    # Core content fields
    introduction: Optional[str] = None
    body_markdown: Optional[str] = None
    body_html: Optional[str] = None
    tags: Optional[List[str]] = None
    
    # Nested relations
    seo_data: Optional[ContentSEODataSchema] = None
    media_items: Optional[List[ContentMediaSchema]] = None

    # Flow-generated structured data on content model
    images_data: Optional[Dict[str, Any]] = None
    links_data: Optional[Dict[str, Any]] = None
    schema_markup: Optional[Dict[str, Any]] = None


class ContentUpdate(BaseModel):
    """Schema for updating content with nested data"""
    title: Optional[str] = None
    status: Optional[str] = None
    content_language: Optional[str] = None
    
    # Core content fields
    introduction: Optional[str] = None
    body_markdown: Optional[str] = None
    body_html: Optional[str] = None
    tags: Optional[List[str]] = None
    
    # Nested relations
    seo_data: Optional[ContentSEODataSchema] = None
    media_items: Optional[List[ContentMediaSchema]] = None

    # Flow-generated structured data
    images_data: Optional[Dict[str, Any]] = None
    links_data: Optional[Dict[str, Any]] = None
    schema_markup: Optional[Dict[str, Any]] = None

    # LangGraph workflow tracking
    langgraph_thread_id: Optional[UUID] = None
    
    # WordPress fields
    wordpress_post_id: Optional[int] = None
    wordpress_url: Optional[str] = None
    wordpress_published_at: Optional[datetime] = None



class ContentResponse(BaseModel):
    """Schema for content response"""
    id: UUID
    workspace_id: UUID
    created_by_user_id: UUID
    title: str
    slug: str
    status: str
    content_language: str
    
    # Core content fields
    introduction: Optional[str] = None
    body_markdown: Optional[str] = None
    body_html: Optional[str] = None
    tags: Optional[List[str]] = None
    
    # Nested relations
    seo_data: Optional[ContentSEODataSchema] = None
    
    # Flow-generated structured data
    images_data: Optional[Dict[str, Any]] = None
    links_data: Optional[Dict[str, Any]] = None
    schema_markup: Optional[Dict[str, Any]] = None

    # LangGraph workflow tracking
    langgraph_thread_id: Optional[UUID] = None

    # WordPress fields
    wordpress_post_id: Optional[int] = None
    wordpress_url: Optional[str] = None
    wordpress_published_at: Optional[datetime] = None

    created_at: datetime
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ContentListResponse(BaseModel):
    """Schema for content list response"""
    content: List[ContentResponse]
    total_count: int
    workspace_id: UUID
    limit: int
    offset: int


class WorkspaceIntegrationBase(BaseModel):
    """Base schema for connected sites."""
    integration_type: str = "wordpress"
    is_active: bool = True
    site_url: Optional[str] = None
    api_endpoint: Optional[str] = None
    username: Optional[str] = None
    app_password: Optional[str] = None
    api_key: Optional[str] = None
    config_json: Optional[Dict[str, Any]] = None


class WorkspaceIntegrationCreate(WorkspaceIntegrationBase):
    pass


class WorkspaceIntegrationUpdate(BaseModel):
    integration_type: Optional[str] = None
    is_active: Optional[bool] = None
    site_url: Optional[str] = None
    api_endpoint: Optional[str] = None
    username: Optional[str] = None
    app_password: Optional[str] = None
    api_key: Optional[str] = None
    config_json: Optional[Dict[str, Any]] = None


class WorkspaceIntegrationResponse(WorkspaceIntegrationBase):
    id: UUID
    workspace_id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WorkspaceIntegrationListResponse(BaseModel):
    sites: List[WorkspaceIntegrationResponse]
    total_count: int
    workspace_id: UUID


class PublishToSiteRequest(BaseModel):
    """Request schema for publishing content to WordPress site(s)"""
    site_id: Optional[UUID] = None  # If None, publishes to all active sites
    status: Optional[str] = "publish"  # publish, draft, pending, private


class PublishResponse(BaseModel):
    """Response for publishing to a single site"""
    site_id: UUID
    site_url: str
    success: bool
    wordpress_post_id: Optional[int] = None
    wordpress_url: Optional[str] = None
    error: Optional[str] = None


class PublishToSitesResponse(BaseModel):
    """Response for publishing to multiple sites"""
    content_id: UUID
    total_sites: int
    successful: int
    failed: int
    results: List[PublishResponse]
    all_failed: bool = False
