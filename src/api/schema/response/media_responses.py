"""
Media Response Schemas

Pydantic models matching the exact dictionary structures returned
by MediaService methods in media_service.py.

Fields verified against media_service.py return statements and
Media.to_dict() (SerializableMixin + computed fields).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Media item schema  (matches Media.to_dict() + computed fields)
# ---------------------------------------------------------------------------

class MediaItemSchema(BaseModel):
    """
    Matches Media.to_dict():
    All SQLAlchemy columns from the Media model serialized via SerializableMixin,
    plus computed fields added by Media.to_dict() override.

    Columns: id, workspace_id, user_id, filename, original_filename,
             file_type, file_size, file_extension, storage_backend, storage_path,
             storage_bucket, public_url, title, description, alt_text,
             file_metadata, folder, tags, is_public, access_level,
             thumbnail_path, thumbnail_url, width, height,
             processing_status, processing_error, created_at, updated_at, deleted_at.
    Computed: file_size_mb, is_image, is_document, is_video.
    """
    id: UUID
    workspace_id: UUID
    user_id: UUID
    filename: str
    original_filename: str
    file_type: str
    file_size: int
    file_extension: Optional[str] = None
    storage_backend: Optional[str] = None
    storage_path: Optional[str] = None
    storage_bucket: Optional[str] = None
    public_url: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    alt_text: Optional[str] = None
    file_metadata: Optional[Dict[str, Any]] = None
    folder: Optional[str] = None
    tags: Optional[List[str]] = None
    is_public: bool = False
    access_level: Optional[str] = None
    thumbnail_path: Optional[str] = None
    thumbnail_url: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    processing_status: Optional[str] = None
    processing_error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    # Computed fields from Media.to_dict() override
    file_size_mb: Optional[float] = None
    is_image: Optional[bool] = None
    is_document: Optional[bool] = None
    is_video: Optional[bool] = None
    # warnings only present on upload response when processing warnings exist
    warnings: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Upload response (same as MediaItemSchema – warnings field already included)
# ---------------------------------------------------------------------------

MediaUploadData = MediaItemSchema


# ---------------------------------------------------------------------------
# List media response
# ---------------------------------------------------------------------------

class MediaPaginationSchema(BaseModel):
    """Matches pagination dict built in list_media route."""
    page: int
    per_page: int
    total: int
    total_pages: int


class MediaListData(BaseModel):
    """
    Matches the data dict built in list_media route:
    {"items": [...], "pagination": {...}}
    """
    items: List[MediaItemSchema]
    pagination: MediaPaginationSchema


# ---------------------------------------------------------------------------
# Delete media response
# ---------------------------------------------------------------------------

class DeleteMediaData(BaseModel):
    """
    Matches data dict in delete_media route:
    {"media_id": str, "permanent": bool}
    """
    media_id: UUID
    permanent: bool


# ---------------------------------------------------------------------------
# Bulk delete response
# ---------------------------------------------------------------------------

class BulkDeleteMediaData(BaseModel):
    """
    Matches MediaService.bulk_delete_media() return value:
    {"deleted": int, "failed": int, "errors": List[str]}
    """
    deleted: int
    failed: int
    errors: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Storage usage response
# ---------------------------------------------------------------------------

class StorageTypeBreakdown(BaseModel):
    count: int
    size: int


class StorageUsageData(BaseModel):
    """
    Matches MediaService.get_workspace_storage_usage() return value.
    """
    total_files: int
    total_size: int
    storage_limit: int
    storage_limit_mb: int
    subscription_tier: str
    usage_percentage: float
    by_type: Dict[str, StorageTypeBreakdown]
    # Legacy backward-compat fields also included:
    file_count: int
    image_count: int
    document_count: int
    total_bytes: int
    total_mb: float
    total_gb: float


# ---------------------------------------------------------------------------
# Media usage response
# ---------------------------------------------------------------------------

class ContentUsageItem(BaseModel):
    """A content item that uses the media file."""
    id: UUID
    title: Optional[str] = None
    slug: Optional[str] = None
    status: Optional[str] = None
    usage_type: str
    position: Optional[int] = None  # only for inline usage


class MediaUsageData(BaseModel):
    """
    Matches MediaService.get_media_usage() return value:
    {
        "is_used": bool,
        "featured_in": [...],
        "used_in_content": [...],
        "total_usages": int,
    }
    """
    is_used: bool
    featured_in: List[ContentUsageItem]
    used_in_content: List[ContentUsageItem]
    total_usages: int
