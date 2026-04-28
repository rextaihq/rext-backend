"""
Response schemas for Content domain API endpoints.

All schemas here are the inner type T used in SuccessResponse[T] route
response_model declarations. They mirror the exact dict shapes returned
by ContentService and WorkspaceIntegration.to_dict().

Base/input schemas (ContentCreate, ContentUpdate, etc.) live in
src/api/schema/content_schema.py. Reuse them here via import.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel

from src.api.schema.content_schema import ContentResponse, PublishToSitesResponse


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

    Used by: GET /{id}, POST /connect, PATCH /{id},
             POST /{id}/activate, POST /{id}/deactivate.
    """
    site: SiteItemResponse


class SiteListResponse(BaseModel):
    """
    Response for GET /sites/list.

    Matches: {"sites": [...], "total_count": N, "workspace_id": "..."}
    """
    sites: List[SiteItemResponse]
    total_count: int
    workspace_id: UUID


class SiteDeletedResponse(BaseModel):
    """
    Response for DELETE /sites/{id}.

    Matches: {"site_id": "..."}
    """
    site_id: UUID


class WordPressPublishResult(BaseModel):
    """
    Response for POST /sites/{site_id}/publish/{content_id}.

    Matches: {"wordpress_result": {...}, "content_id": "..."}
    """
    wordpress_result: Dict[str, Any]
    content_id: UUID
