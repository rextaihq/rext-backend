"""
Media API endpoints.

This module provides media management operations for workspaces.
Routes handle HTTP concerns and delegate business logic to MediaService.
"""

from fastapi import APIRouter, Depends, status, Request, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.services.media_service import MediaService
from src.services.storage_service import create_storage_service
from src.services.image_processing_service import ImageProcessingService
from src.config.storage_config import storage_settings
from src.utils.response_utils import success, created, error_response
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.logger import logger


router = APIRouter(
    prefix="/workspaces/{workspace_id}/media",
    tags=["media"]
)


def get_media_service(db: AsyncSession) -> MediaService:
    """
    Dependency to create MediaService instance.

    Args:
        db: Database session

    Returns:
        MediaService instance
    """
    # Create storage service based on config
    storage_service = create_storage_service(
        backend_type=storage_settings.storage_backend,
        # R2 config
        bucket=storage_settings.r2_bucket,
        account_id=storage_settings.r2_account_id,
        access_key_id=storage_settings.r2_access_key_id,
        secret_access_key=storage_settings.r2_secret_access_key,
        public_domain=storage_settings.r2_public_domain,
        # Local config
        base_path=storage_settings.local_storage_path,
        public_url_base=storage_settings.local_storage_url_base
    )

    # Create image processing service
    image_service = ImageProcessingService(
        thumbnail_size=storage_settings.thumbnail_size,
        max_width=storage_settings.max_image_width,
        max_height=storage_settings.max_image_height,
        quality=storage_settings.image_quality
    )

    return MediaService(db, storage_service, image_service)


@router.post("/upload", response_model=dict, status_code=status.HTTP_201_CREATED)
@db_transaction_handler("upload media")
@require_permissions("media.create")
async def upload_media(
    request: Request,
    workspace_id: str,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    alt_text: Optional[str] = Form(None),
    folder: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),  # Comma-separated
    is_public: bool = Form(False),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload media file to workspace.

    Supports:
    - Images: JPEG, PNG, GIF, WEBP, SVG
    - Documents: PDF, DOCX, TXT, Markdown
    - Videos: MP4, WEBM, MOV

    Features:
    - Automatic image optimization
    - Thumbnail generation for images
    - Metadata extraction
    - Folder organization
    - Tag support

    Args:
        workspace_id: Workspace UUID
        file: File to upload (max size varies by type)
        title: Optional title (defaults to filename)
        description: Optional description
        alt_text: Optional alt text for images
        folder: Optional folder path (e.g., /images/products)
        tags: Optional comma-separated tags
        is_public: Whether file is publicly accessible

    Returns:
        Created media object with URLs
    """
    user_id = current_user.get("identity")

    # Parse tags
    tag_list = [t.strip() for t in tags.split(',')] if tags else []

    try:
        # Get service
        service = get_media_service(db)

        # Upload media
        media = await service.upload_media(
            file=file.file,
            filename=file.filename,
            workspace_id=workspace_id,
            user_id=user_id,
            title=title,
            description=description,
            alt_text=alt_text,
            folder=folder,
            tags=tag_list,
            is_public=is_public
        )

        logger.info(f"Media uploaded successfully: {media.id}")

        return created(
            data=media.to_dict(),
            request=request,
            message=f"File '{file.filename}' uploaded successfully"
        )

    except ValueError as e:
        logger.error(f"Media upload validation error: {e}")
        return error_response(
            message=str(e),
            status_code=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"Media upload error: {e}")
        return error_response(
            message="Failed to upload file",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@router.get("", response_model=dict)
@db_transaction_handler("list media")
@require_permissions("media.view")
async def list_media(
    request: Request,
    workspace_id: str,
    folder: Optional[str] = Query(None, description="Filter by folder"),
    file_type: Optional[str] = Query(None, description="Filter by type: image, document, video"),
    tags: Optional[str] = Query(None, description="Filter by tags (comma-separated)"),
    search: Optional[str] = Query(None, description="Search in title/description/filename"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List media files in workspace.

    Supports:
    - Filtering by folder, file type, tags
    - Full-text search
    - Pagination

    Args:
        workspace_id: Workspace UUID
        folder: Filter by folder path
        file_type: Filter by type (image, document, video)
        tags: Filter by tags (comma-separated)
        search: Search query
        page: Page number (1-indexed)
        per_page: Items per page (1-100)

    Returns:
        Paginated list of media objects
    """
    # Parse tags
    tag_list = [t.strip() for t in tags.split(',')] if tags else None

    # Get service
    service = get_media_service(db)

    # List media
    result = await service.list_media(
        workspace_id=workspace_id,
        folder=folder,
        file_type=file_type,
        tags=tag_list,
        search=search,
        page=page,
        per_page=per_page
    )

    # Serialize items
    items = [item.to_dict() for item in result["items"]]

    return success(
        data={
            "items": items,
            "pagination": {
                "page": result["page"],
                "per_page": result["per_page"],
                "total": result["total"],
                "total_pages": result["total_pages"]
            }
        },
        message=f"Found {result['total']} media files"
    )


@router.get("/{media_id}", response_model=dict)
@db_transaction_handler("get media")
@require_permissions("media.view")
async def get_media_detail(
    request: Request,
    workspace_id: str,
    media_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get media file details.

    Args:
        workspace_id: Workspace UUID
        media_id: Media UUID

    Returns:
        Media object with all details
    """
    # Get service
    service = get_media_service(db)

    # Get media
    media = await service.get_media(media_id, workspace_id)

    if not media:
        return error_response(
            message="Media not found",
            status_code=status.HTTP_404_NOT_FOUND
        )

    return success(
        data=media.to_dict(),
        message="Media retrieved successfully"
    )


@router.patch("/{media_id}", response_model=dict)
@db_transaction_handler("update media")
@require_permissions("media.update")
async def update_media_metadata(
    request: Request,
    workspace_id: str,
    media_id: str,
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    alt_text: Optional[str] = Form(None),
    folder: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    is_public: Optional[bool] = Form(None),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Update media metadata.

    Only metadata is updated - the file itself is not replaced.

    Args:
        workspace_id: Workspace UUID
        media_id: Media UUID
        title: New title
        description: New description
        alt_text: New alt text
        folder: New folder
        tags: New tags (comma-separated)
        is_public: New public status

    Returns:
        Updated media object
    """
    # Parse tags
    tag_list = [t.strip() for t in tags.split(',')] if tags else None

    # Get service
    service = get_media_service(db)

    # Update media
    media = await service.update_media(
        media_id=media_id,
        workspace_id=workspace_id,
        title=title,
        description=description,
        alt_text=alt_text,
        folder=folder,
        tags=tag_list,
        is_public=is_public
    )

    if not media:
        return error_response(
            message="Media not found",
            status_code=status.HTTP_404_NOT_FOUND
        )

    return success(
        data=media.to_dict(),
        message="Media updated successfully"
    )


@router.delete("/{media_id}", response_model=dict)
@db_transaction_handler("delete media")
@require_permissions("media.delete")
async def delete_media(
    request: Request,
    workspace_id: str,
    media_id: str,
    permanent: bool = Query(False, description="Permanently delete from storage"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Delete media file.

    By default, performs soft delete (sets deleted_at).
    Use permanent=true to remove from storage and database.

    Args:
        workspace_id: Workspace UUID
        media_id: Media UUID
        permanent: If true, permanently delete

    Returns:
        Success message
    """
    # Get service
    service = get_media_service(db)

    # Delete media
    deleted = await service.delete_media(
        media_id=media_id,
        workspace_id=workspace_id,
        permanent=permanent
    )

    if not deleted:
        return error_response(
            message="Media not found",
            status_code=status.HTTP_404_NOT_FOUND
        )

    delete_type = "permanently deleted" if permanent else "moved to trash"
    return success(
        data={"media_id": media_id, "permanent": permanent},
        message=f"Media {delete_type} successfully"
    )


@router.post("/bulk-delete", response_model=dict)
@db_transaction_handler("bulk delete media")
@require_permissions("media.delete")
async def bulk_delete_media(
    request: Request,
    workspace_id: str,
    media_ids: list[str],
    permanent: bool = Query(False, description="Permanently delete from storage"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Delete multiple media files at once.

    By default, performs soft delete (sets deleted_at).
    Use permanent=true to remove from storage and database.

    Args:
        workspace_id: Workspace UUID
        media_ids: List of media UUIDs to delete
        permanent: If true, permanently delete

    Returns:
        Bulk delete results with counts
    """
    # Get service
    service = get_media_service(db)

    # Bulk delete media
    result = await service.bulk_delete_media(
        media_ids=media_ids,
        workspace_id=workspace_id,
        permanent=permanent
    )

    delete_type = "permanently deleted" if permanent else "moved to trash"
    message = f"{result['deleted']} media files {delete_type}"
    if result['failed'] > 0:
        message += f", {result['failed']} failed"

    return success(
        data=result,
        message=message
    )


@router.get("/{media_id}/usage", response_model=dict)
@db_transaction_handler("get media usage")
@require_permissions("media.view")
async def get_media_usage_info(
    request: Request,
    workspace_id: str,
    media_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get information about where a media file is being used.

    Returns which content uses this media as featured image or inline.
    Useful for preventing deletion of media that's in use.

    Args:
        workspace_id: Workspace UUID
        media_id: Media UUID

    Returns:
        Usage information including content list
    """
    # Get service
    service = get_media_service(db)

    # Get usage info
    usage = await service.get_media_usage(media_id, workspace_id)

    return success(
        data=usage,
        message="Media usage retrieved successfully"
    )


@router.get("/usage/stats", response_model=dict)
@db_transaction_handler("get storage usage")
@require_permissions("media.view")
async def get_storage_usage(
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get storage usage statistics for workspace.

    Returns:
        Usage statistics including file counts and storage size
    """
    # Get service
    service = get_media_service(db)

    # Get usage stats
    usage = await service.get_workspace_storage_usage(workspace_id)

    return success(
        data=usage,
        message="Storage usage retrieved successfully"
    )
