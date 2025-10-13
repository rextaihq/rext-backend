"""
Media Service

High-level service for media management that orchestrates:
- Storage (Cloudflare R2 / Local)
- Image processing (optimization, thumbnails)
- Database operations
- Subscription limit enforcement
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, or_
from typing import List, Optional, BinaryIO, Dict, Any
from datetime import datetime
from io import BytesIO
import os
import magic

from src.api.models.media_models.media import Media
from src.services.storage_service import StorageService
from src.services.image_processing_service import ImageProcessingService
from src.config.storage_config import storage_settings
import logging

logger = logging.getLogger(__name__)


class MediaService:
    """
    Service for media management.

    Handles the complete media upload workflow:
    1. File validation (type, size)
    2. Image processing (optimization, thumbnails)
    3. Storage upload (R2 or local)
    4. Database record creation
    5. Subscription limit enforcement
    """

    def __init__(
        self,
        db: AsyncSession,
        storage_service: StorageService,
        image_service: ImageProcessingService
    ):
        """
        Initialize media service.

        Args:
            db: Database session
            storage_service: Storage service instance
            image_service: Image processing service instance
        """
        self.db = db
        self.storage = storage_service
        self.image = image_service

    async def upload_media(
        self,
        file: BinaryIO,
        filename: str,
        workspace_id: str,
        user_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        alt_text: Optional[str] = None,
        folder: Optional[str] = None,
        tags: Optional[List[str]] = None,
        is_public: bool = False
    ) -> Media:
        """
        Upload media file with full processing pipeline.

        Workflow:
        1. Detect and validate file type
        2. Check file size limits
        3. Process image (if applicable)
        4. Upload to storage (original + thumbnail)
        5. Create database record

        Args:
            file: File object to upload
            filename: Original filename
            workspace_id: Workspace UUID
            user_id: User UUID
            title: Optional title
            description: Optional description
            alt_text: Optional alt text for images
            folder: Optional folder path
            tags: Optional list of tags
            is_public: Whether file is publicly accessible

        Returns:
            Created Media object

        Raises:
            ValueError: If file validation fails
        """
        # Read file content
        file_content = file.read()
        file.seek(0)

        # Detect MIME type
        mime_type = magic.from_buffer(file_content, mime=True)

        # Validate file type
        if not self._is_allowed_file_type(mime_type):
            raise ValueError(f"File type not allowed: {mime_type}")

        # Check file size
        file_size = len(file_content)
        max_size = self._get_max_file_size(mime_type)
        if file_size > max_size:
            max_size_mb = max_size / (1024 * 1024)
            actual_size_mb = file_size / (1024 * 1024)
            raise ValueError(
                f"File size ({actual_size_mb:.2f}MB) exceeds maximum ({max_size_mb:.2f}MB)"
            )

        # TODO: Check subscription storage limits
        # await self._check_storage_limit(workspace_id, file_size)

        # Extract file extension
        _, ext = os.path.splitext(filename)
        ext = ext.lower()

        # Initialize metadata
        file_metadata = {}
        width = None
        height = None
        thumbnail_path = None
        thumbnail_url = None
        processing_status = "pending"
        processing_error = None

        try:
            # Process image if applicable
            if mime_type.startswith('image/'):
                file_io = BytesIO(file_content)

                # Validate image
                is_valid, error_msg = self.image.validate_image(
                    file_io,
                    max_size_mb=max_size / (1024 * 1024)
                )
                if not is_valid:
                    raise ValueError(error_msg)

                # Extract metadata
                file_io.seek(0)
                file_metadata = self.image.extract_metadata(file_io)
                width = file_metadata.get('width')
                height = file_metadata.get('height')

                # Optimize image
                file_io.seek(0)
                optimized = self.image.optimize_image(file_io)
                file_content = optimized.read()
                optimized.seek(0)

                # Update file size after optimization
                file_size = len(file_content)

            # Upload original file to storage
            file_io = BytesIO(file_content)
            storage_path, generated_filename = await self.storage.upload_file(
                file_io,
                filename,
                mime_type,
                workspace_id,
                user_id,
                metadata={"original_filename": filename}
            )

            # Get storage backend name
            storage_backend = storage_settings.storage_backend

            # Get bucket name if R2
            storage_bucket = None
            if storage_backend == "r2":
                storage_bucket = storage_settings.r2_bucket

            # Generate public URL
            public_url = await self.storage.get_file_url(storage_path)

            # Create thumbnail for images
            if mime_type.startswith('image/'):
                try:
                    file_io = BytesIO(file_content)
                    thumbnail = self.image.create_thumbnail(file_io, size='medium')

                    # Generate thumbnail filename
                    thumb_filename = f"thumb_{generated_filename}"
                    if not thumb_filename.endswith('.jpg'):
                        thumb_filename = os.path.splitext(thumb_filename)[0] + '.jpg'

                    # Upload thumbnail
                    thumbnail_path, _ = await self.storage.upload_file(
                        thumbnail,
                        thumb_filename,
                        'image/jpeg',
                        workspace_id,
                        user_id
                    )
                    thumbnail_url = await self.storage.get_file_url(thumbnail_path)

                except Exception as e:
                    logger.error(f"Failed to create thumbnail: {e}")
                    # Continue without thumbnail

            processing_status = "completed"

        except Exception as e:
            logger.error(f"Error processing media: {e}")
            processing_status = "failed"
            processing_error = str(e)
            # Re-raise if critical error
            if "not allowed" in str(e) or "exceeds maximum" in str(e):
                raise

        # Create media record
        media = Media(
            workspace_id=workspace_id,
            user_id=user_id,
            filename=generated_filename,
            original_filename=filename,
            file_type=mime_type,
            file_size=file_size,
            file_extension=ext,
            storage_backend=storage_backend,
            storage_path=storage_path,
            storage_bucket=storage_bucket,
            public_url=public_url,
            title=title or filename,
            description=description,
            alt_text=alt_text,
            folder=folder,
            tags=tags or [],
            is_public=is_public,
            access_level="public" if is_public else "private",
            width=width,
            height=height,
            thumbnail_path=thumbnail_path,
            thumbnail_url=thumbnail_url,
            processing_status=processing_status,
            processing_error=processing_error,
            file_metadata=file_metadata
        )

        self.db.add(media)
        await self.db.commit()
        await self.db.refresh(media)

        logger.info(f"Media uploaded: {media.id} ({media.original_filename})")
        return media

    async def get_media(
        self,
        media_id: str,
        workspace_id: str
    ) -> Optional[Media]:
        """
        Get media by ID.

        Args:
            media_id: Media UUID
            workspace_id: Workspace UUID

        Returns:
            Media object or None
        """
        result = await self.db.execute(
            select(Media).where(
                and_(
                    Media.id == media_id,
                    Media.workspace_id == workspace_id,
                    Media.deleted_at.is_(None)
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_media(
        self,
        workspace_id: str,
        folder: Optional[str] = None,
        file_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        search: Optional[str] = None,
        page: int = 1,
        per_page: int = 50
    ) -> Dict[str, Any]:
        """
        List media with filters and pagination.

        Args:
            workspace_id: Workspace UUID
            folder: Filter by folder
            file_type: Filter by type prefix (e.g., "image", "document")
            tags: Filter by tags (any match)
            search: Search in title/description
            page: Page number (1-indexed)
            per_page: Items per page

        Returns:
            Dictionary with 'items', 'total', 'page', 'per_page'
        """
        # Build base query
        query = select(Media).where(
            and_(
                Media.workspace_id == workspace_id,
                Media.deleted_at.is_(None)
            )
        )

        # Apply filters
        if folder:
            query = query.where(Media.folder == folder)

        if file_type:
            query = query.where(Media.file_type.startswith(file_type))

        if tags:
            # Match any of the provided tags
            query = query.where(Media.tags.overlap(tags))

        if search:
            # Full-text search on title and description
            search_pattern = f"%{search}%"
            query = query.where(
                or_(
                    Media.title.ilike(search_pattern),
                    Media.description.ilike(search_pattern),
                    Media.original_filename.ilike(search_pattern)
                )
            )

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        query = query.order_by(Media.created_at.desc())
        query = query.offset((page - 1) * per_page).limit(per_page)

        # Execute query
        result = await self.db.execute(query)
        items = result.scalars().all()

        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page
        }

    async def update_media(
        self,
        media_id: str,
        workspace_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        alt_text: Optional[str] = None,
        folder: Optional[str] = None,
        tags: Optional[List[str]] = None,
        is_public: Optional[bool] = None
    ) -> Optional[Media]:
        """
        Update media metadata.

        Args:
            media_id: Media UUID
            workspace_id: Workspace UUID
            title: New title
            description: New description
            alt_text: New alt text
            folder: New folder
            tags: New tags
            is_public: New public status

        Returns:
            Updated Media object or None
        """
        media = await self.get_media(media_id, workspace_id)
        if not media:
            return None

        # Update fields
        if title is not None:
            media.title = title
        if description is not None:
            media.description = description
        if alt_text is not None:
            media.alt_text = alt_text
        if folder is not None:
            media.folder = folder
        if tags is not None:
            media.tags = tags
        if is_public is not None:
            media.is_public = is_public
            media.access_level = "public" if is_public else "private"

        media.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(media)

        logger.info(f"Media updated: {media.id}")
        return media

    async def delete_media(
        self,
        media_id: str,
        workspace_id: str,
        permanent: bool = False
    ) -> bool:
        """
        Delete media (soft or hard delete).

        Args:
            media_id: Media UUID
            workspace_id: Workspace UUID
            permanent: If True, permanently delete from storage and DB

        Returns:
            True if deleted successfully
        """
        media = await self.get_media(media_id, workspace_id)
        if not media:
            return False

        if permanent:
            # Delete from storage
            try:
                await self.storage.delete_file(media.storage_path)
                if media.thumbnail_path:
                    await self.storage.delete_file(media.thumbnail_path)
            except Exception as e:
                logger.error(f"Error deleting files from storage: {e}")

            # Delete from database
            await self.db.delete(media)
        else:
            # Soft delete
            media.deleted_at = datetime.utcnow()

        await self.db.commit()

        logger.info(f"Media deleted: {media.id} (permanent={permanent})")
        return True

    async def get_workspace_storage_usage(self, workspace_id: str) -> Dict[str, Any]:
        """
        Calculate total storage usage for workspace.

        Args:
            workspace_id: Workspace UUID

        Returns:
            Dictionary with usage statistics
        """
        result = await self.db.execute(
            select(
                func.count(Media.id).label("file_count"),
                func.sum(Media.file_size).label("total_bytes"),
                func.count(Media.id).filter(Media.file_type.startswith("image/")).label("image_count"),
                func.count(Media.id).filter(Media.file_type.startswith("application/")).label("document_count"),
            ).where(
                and_(
                    Media.workspace_id == workspace_id,
                    Media.deleted_at.is_(None)
                )
            )
        )

        row = result.one()

        total_bytes = row.total_bytes or 0
        total_mb = total_bytes / (1024 * 1024)
        total_gb = total_bytes / (1024 * 1024 * 1024)

        return {
            "file_count": row.file_count or 0,
            "image_count": row.image_count or 0,
            "document_count": row.document_count or 0,
            "total_bytes": total_bytes,
            "total_mb": round(total_mb, 2),
            "total_gb": round(total_gb, 2)
        }

    def _is_allowed_file_type(self, mime_type: str) -> bool:
        """Check if MIME type is allowed."""
        allowed_types = (
            storage_settings.allowed_image_types +
            storage_settings.allowed_document_types +
            storage_settings.allowed_video_types
        )
        return mime_type in allowed_types

    def _get_max_file_size(self, mime_type: str) -> int:
        """Get maximum file size in bytes for MIME type."""
        if mime_type.startswith('image/'):
            return storage_settings.max_image_size
        elif mime_type.startswith('video/'):
            return storage_settings.max_video_size
        else:
            return storage_settings.max_file_size
