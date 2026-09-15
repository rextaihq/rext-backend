from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.utils.wordpress_status import normalize_wordpress_post_status


class ContentBase(BaseModel):
    """Base content schema with common fields"""

    # title: str = Field(..., min_length=1, max_length=500, description="Content title")
    title: str = Field(default="", description="Content title")
    content_language: Optional[str] = Field(default="English", description="Content language")
    status: Optional[str] = Field(default="draft", description="Content status")

    # @field_validator('title')
    # @classmethod
    # def validate_title(cls, v):
    #     if not v or not v.strip():
    #         raise ValueError('Title cannot be empty')
    #     return v.strip()


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
    keyword_difficulty: Optional[int] = None
    intent_label: Optional[str] = None
    seo_details: Optional[str] = None


class ContentCreate(ContentBase):
    """Schema for creating content with nested data"""

    workspace_id: Optional[Any] = Field(None, description="Workspace ID (UUID or slug)")

    # Core content fields
    introduction: Optional[str] = None
    body_markdown: Optional[str] = None
    body_html: Optional[str] = None
    tags: Optional[List[str]] = None
    category: Optional[str] = None
    content_type: Optional[Any] = Field(None, description="content type")

    # Nested relations
    seo_data: Optional[ContentSEODataSchema] = None

    # Flow-generated structured data on content model
    images_data: Optional[Dict[str, Any]] = None
    links_data: Optional[Dict[str, Any]] = None
    schema_markup: Optional[Dict[str, Any]] = None

    # LangGraph workflow tracking (idempotency key for generated content)
    langgraph_thread_id: Optional[UUID] = None


_VALID_CONTENT_STATUSES = {
    "draft",
    "generating",
    "ready",
    "published",
    "failed",
    "archived",
    "scheduled",
    "review",
    "trashed",
    "deleted",
}


class ContentUpdate(BaseModel):
    """Schema for updating content with nested data"""

    title: Optional[str] = None
    status: Optional[str] = None

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v):
        if v is None:
            return v
        # "publish" is a WordPress action string — map it to the content status
        if v == "publish":
            return "published"
        if v not in _VALID_CONTENT_STATUSES:
            raise ValueError(
                f"Invalid content status '{v}'. Must be one of: {sorted(_VALID_CONTENT_STATUSES)}"
            )
        return v

    content_language: Optional[str] = None

    # Core content fields
    introduction: Optional[str] = None
    body_markdown: Optional[str] = None
    body_html: Optional[str] = None
    tags: Optional[List[str]] = None
    category: Optional[str] = None

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
    category: Optional[str] = None

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

    model_config = ConfigDict(from_attributes=True)


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
    config_json: Optional[Dict[str, Any]] = None


class WorkspaceIntegrationCreate(WorkspaceIntegrationBase):
    app_password: Optional[str] = None
    api_key: Optional[str] = None


class WorkspaceIntegrationUpdate(BaseModel):
    integration_type: Optional[str] = None
    is_active: Optional[bool] = None
    site_url: Optional[str] = None
    api_endpoint: Optional[str] = None
    username: Optional[str] = None
    app_password: Optional[str] = None
    api_key: Optional[str] = None
    config_json: Optional[Dict[str, Any]] = None


class WorkspaceIntegrationResponse(BaseModel):
    """Full representation of a connected site (matches to_dict() output)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    integration_type: str
    is_active: bool
    site_url: Optional[str] = None
    api_endpoint: Optional[str] = None
    username: Optional[str] = None
    config_json: Optional[Dict[str, Any]] = None
    has_app_password: bool = False
    has_api_key: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None


class WorkspaceIntegrationListResponse(BaseModel):
    sites: List[WorkspaceIntegrationResponse]
    total_count: int
    workspace_id: UUID


class PublishToSiteRequest(BaseModel):
    """Request schema for publishing content to WordPress site(s)"""

    site_id: Optional[UUID] = None  # If None, publishes to all active sites
    status: str = "publish"  # publish, draft, pending, future, private
    scheduled_at: Optional[datetime] = (
        None  # If set and future, WP schedules post with status "future"
    )

    @field_validator("status", mode="before")
    @classmethod
    def normalize_wordpress_status(cls, value):
        return normalize_wordpress_post_status(value)


class PublishResponse(BaseModel):
    """Response for publishing to a single site"""

    site_id: UUID
    site_url: str
    success: bool
    wordpress_post_id: Optional[int] = None
    wordpress_url: Optional[str] = None
    shopify_article_id: Optional[int] = None
    shopify_article_url: Optional[str] = None
    shopify_blog_id: Optional[int] = None
    error: Optional[str] = None


class PublishToSitesResponse(BaseModel):
    """Response for publishing to multiple sites"""

    content_id: UUID
    total_sites: int
    successful: int
    failed: int
    results: List[PublishResponse]
    all_failed: bool = False
