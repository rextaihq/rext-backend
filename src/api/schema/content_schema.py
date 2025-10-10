from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
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

    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        allowed_statuses = ['draft', 'generating', 'ready', 'published', 'archived']
        if v and v not in allowed_statuses:
            raise ValueError(f'Status must be one of: {", ".join(allowed_statuses)}')
        return v


class ContentMetadataSchema(BaseModel):
    """Schema for content metadata"""
    content_summary: Optional[str] = Field(None, description="Brief summary of content")
    content_type: Optional[str] = Field(None, description="Type of content (blog_post, article, etc.)")
    target_platform: Optional[str] = Field(None, description="Target platform (Medium, LinkedIn, etc.)")
    target_industry: Optional[str] = Field(None, description="Target industry")
    target_audience: Optional[List[str]] = Field(default_factory=list, description="Target audience segments")
    audience_size: Optional[str] = Field(None, description="Audience size (small, medium, large, enterprise)")
    complexity_level: Optional[str] = Field(None, description="Complexity level (beginner, intermediate, advanced, expert)")
    content_tone: Optional[List[str]] = Field(default_factory=list, description="Content tone (professional, casual, etc.)")
    target_region: Optional[str] = Field(None, description="Target geographic region")
    content_objectives: Optional[List[str]] = Field(default_factory=list, description="Content objectives (educate, persuade, etc.)")
    source_references: Optional[List[str]] = Field(default_factory=list, description="Source URLs or citations")
    content_word_count: Optional[int] = Field(None, description="Word count")
    reading_time_minutes: Optional[int] = Field(None, description="Estimated reading time in minutes")
    content_quality_scores: Optional[Dict[str, Any]] = Field(None, description="Quality metrics")
    featured_image_prompt: Optional[str] = Field(None, description="AI prompt for featured image")
    featured_image_alt_text: Optional[str] = Field(None, description="Alt text for featured image")


class ContentSEODataSchema(BaseModel):
    """Schema for SEO-specific data"""
    content_primary_keywords: List[str] = Field(..., min_length=1, description="Primary SEO keywords")
    content_secondary_keywords: Optional[List[str]] = Field(default_factory=list, description="Secondary keywords")
    content_meta_description: str = Field(..., max_length=160, description="Meta description for SEO")
    content_search_intent: Optional[List[str]] = Field(default_factory=list, description="Search intent types")
    content_seo_score: Optional[float] = Field(None, ge=0, le=100, description="SEO score (0-100)")
    content_readability_score: Optional[float] = Field(None, ge=0, le=100, description="Readability score")

    @field_validator('content_primary_keywords')
    @classmethod
    def validate_primary_keywords(cls, v):
        if not v or len(v) == 0:
            raise ValueError('At least one primary keyword is required')
        return v

    @field_validator('content_meta_description')
    @classmethod
    def validate_meta_description(cls, v):
        if not v or not v.strip():
            raise ValueError('Meta description cannot be empty')
        return v.strip()


class ContentCreate(ContentBase):
    """Schema for creating content"""
    workspace_id: UUID = Field(..., description="Workspace ID")
    topic_id: Optional[UUID] = Field(None, description="Related topic ID")
    body_markdown: Optional[str] = Field(None, description="Content body in markdown")
    content_format: Optional[str] = Field(default="Markdown", description="Content format")
    assigned_to_user_id: Optional[UUID] = Field(None, description="User assigned to this content")

    # LangGraph workflow tracking
    langgraph_thread_id: Optional[UUID] = Field(None, description="LangGraph workflow thread ID for content generation tracking")

    # Metadata fields (optional, will create related records if provided)
    metadata: Optional[ContentMetadataSchema] = Field(None, description="Content metadata")
    seo_data: Optional[ContentSEODataSchema] = Field(None, description="SEO data")


class ContentUpdate(BaseModel):
    """Schema for updating content"""
    title: Optional[str] = Field(None, min_length=1, max_length=500, description="Content title")
    body_markdown: Optional[str] = Field(None, description="Content body in markdown")
    body_html: Optional[str] = Field(None, description="Content body in HTML")
    status: Optional[str] = Field(None, description="Content status")
    content_language: Optional[str] = Field(None, description="Content language")
    assigned_to_user_id: Optional[UUID] = Field(None, description="Assigned user ID")
    topic_id: Optional[UUID] = Field(None, description="Related topic ID")

    # LangGraph workflow tracking
    langgraph_thread_id: Optional[UUID] = Field(None, description="LangGraph workflow thread ID for content generation tracking")

    # Metadata and SEO updates
    metadata: Optional[ContentMetadataSchema] = Field(None, description="Content metadata")
    seo_data: Optional[ContentSEODataSchema] = Field(None, description="SEO data")

    @field_validator('title')
    @classmethod
    def validate_title(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('Title cannot be empty')
        return v.strip() if v else v

    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        if v is not None:
            allowed_statuses = ['draft', 'generating', 'ready', 'published', 'archived']
            if v not in allowed_statuses:
                raise ValueError(f'Status must be one of: {", ".join(allowed_statuses)}')
        return v


class ContentResponse(BaseModel):
    """Schema for content response"""
    id: UUID
    workspace_id: UUID
    topic_id: Optional[UUID] = None
    created_by_user_id: UUID
    assigned_to_user_id: Optional[UUID] = None
    author_id: Optional[UUID] = None
    title: str
    slug: str
    body_markdown: Optional[str] = None
    body_html: Optional[str] = None
    content_format: str
    status: str
    content_language: str

    # LangGraph workflow tracking
    langgraph_thread_id: Optional[UUID] = None

    created_at: datetime
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None

    # Related data (optional, loaded based on query parameters)
    metadata: Optional[ContentMetadataSchema] = None
    seo_data: Optional[ContentSEODataSchema] = None

    class Config:
        from_attributes = True


class ContentListResponse(BaseModel):
    """Schema for content list response"""
    content: List[ContentResponse]
    total_count: int
    workspace_id: UUID
    limit: int
    offset: int


class ContentProgressResponse(BaseModel):
    """Schema for content progress tracking"""
    content_id: UUID
    current_step: str
    progress_percent: int = Field(..., ge=0, le=100)
    status_message: Optional[str] = None
    started_at: Optional[datetime] = None
    estimated_completion: Optional[datetime] = None
    step_details: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True
