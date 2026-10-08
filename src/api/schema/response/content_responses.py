"""
Response schemas for Content domain API endpoints.

All schemas here are the inner type T used in SuccessResponse[T] route
response_model declarations. They mirror the exact dict shapes returned
by ContentService and WorkspaceIntegration.to_dict().

Base/input schemas (ContentCreate, ContentUpdate, etc.) live in
src/api/schema/content_schema.py. Reuse them here via import.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from src.api.schema.content_schema import ContentResponse, PublishToSitesResponse


class BlogImageUploadData(BaseModel):
    """Image stored in MinIO for use inside a blog post."""

    filename: str
    original_filename: str
    file_type: str
    file_size: int
    storage_backend: str
    storage_path: str
    storage_bucket: str
    public_url: str
    width: Optional[int] = None
    height: Optional[int] = None


# ---------------------------------------------------------------------------
# Content retrieval
# ---------------------------------------------------------------------------


class ContentListResponse(BaseModel):
    """
    Response for GET /content/ (paginated list).

    Matches the dict returned by list_content endpoint:
      {"content": [...], "total_count": N, "workspace_id": "...", "limit": N, "offset": N}
    """

    content: List[ContentResponse]
    total_count: int
    workspace_id: UUID
    limit: int
    offset: int


class ContentHealthResponse(BaseModel):
    """
    Response for GET /content/health: counts over the workspace's published articles.
    """

    published: int
    missing_meta_description: int = Field(description="Published articles with no meta description")
    no_internal_links: Optional[int] = Field(
        None,
        description=(
            "Published articles that link to none of the workspace's own sites; "
            "null when the workspace has no website and no connected site"
        ),
    )


class ContentDetailResponse(BaseModel):
    """
    Response for GET /content/{content_id}.

    Matches: {"content": <ContentResponse>}
    """

    content: ContentResponse


# ---------------------------------------------------------------------------
# Content publishing / mutation
# ---------------------------------------------------------------------------


class SaveAndPublishResponse(BaseModel):
    """
    Response for POST /content/publish and POST /content/{id}/publish.

    Matches: {"content": <ContentResponse>, "publish_results": <PublishToSitesResponse>}
    """

    content: ContentResponse
    publish_results: PublishToSitesResponse


class RetryContentResponse(BaseModel):
    """
    Response for POST /content/{id}/retry.

    Both code paths (publish-retry and draft-reset) return content_id,
    status, and retry_type. The `successful` field is only present on the
    publish-retry path; it is Optional here to cover both branches.
    """

    content_id: UUID
    status: str
    retry_type: str
    successful: Optional[bool] = None


class DeletedContentResponse(BaseModel):
    """
    Response for DELETE /content/{id}.

    Matches: {"deleted_id": "..."}
    """

    deleted_id: UUID


# ---------------------------------------------------------------------------
# Site (WorkspaceIntegration) responses
# ---------------------------------------------------------------------------


class SiteItemResponse(BaseModel):
    """
    Safe public view of a WorkspaceIntegration row.

    Matches the dict produced by WorkspaceIntegration.to_dict() (credentials
    are always excluded; presence flags are included instead).
    """

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


class SiteResponse(BaseModel):
    """
    Response wrapping a single site — {"site": <SiteItemResponse>}.

    Used by /integrations/wordpress/: POST /, GET /{id}, PATCH /{id},
    POST /{id}/activate, POST /{id}/deactivate.
    """

    site: SiteItemResponse


class SiteListResponse(BaseModel):
    """
    Response for GET /integrations/wordpress/.

    Matches: {"sites": [...], "total_count": N, "workspace_id": "..."}
    """

    sites: List[SiteItemResponse]
    total_count: int
    workspace_id: UUID


class SiteDeletedResponse(BaseModel):
    """
    Response for DELETE /integrations/wordpress/{id}.

    Matches: {"site_id": "..."}
    """

    site_id: UUID


class WordPressConnectionTest(BaseModel):
    """Response for POST /integrations/wordpress/{site_id}/test."""

    site_id: str
    ok: bool
    status: str = Field(
        description=(
            "connected, invalid_credentials, plugin_missing, plugin_disabled, rate_limited, "
            "unreachable, invalid_url, rest_api_missing, redirected, no_credentials, "
            "blocked_address or error"
        )
    )
    message: str
    authors_available: Optional[bool] = Field(
        None, description="Whether the plugin's author list answers (plugin key connections only)"
    )
    checked_at: datetime


class ContentVersionMaker(BaseModel):
    """Who made a version."""

    id: UUID
    name: Optional[str] = None


class ContentVersionSummary(BaseModel):
    """A version in the editor's history: the article's text as a save left it."""

    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = Field(
        None, description="When a later save of the same sitting last wrote into it"
    )
    created_by: Optional[ContentVersionMaker] = Field(
        None, description="null when the account is gone"
    )
    source: str = Field(description="generation, edit, restore or publish")
    title: str
    word_count: int = Field(description="Words of the introduction and the body")


class ContentVersionListResponse(BaseModel):
    """Response for GET /content/{content_id}/versions: newest first, without bodies."""

    versions: List[ContentVersionSummary]


class ContentVersionDetailResponse(ContentVersionSummary):
    """Response for GET /content/{content_id}/versions/{version_id}."""

    introduction: Optional[str] = None
    body_markdown: Optional[str] = None
    body_html: Optional[str] = None
    images_data: Optional[Any] = None
