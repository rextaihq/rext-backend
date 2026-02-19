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
from datetime import datetime, timezone
from io import BytesIO
import os
import uuid 
import filetype
import asyncio
from functools import partial

from src.api.models.media_models.media import Media
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.subscription_models.subscriptions import (
    UserSubscription,
    SubscriptionStatus
)
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.services.storage_service import StorageService
from src.services.image_processing_service import ImageProcessingService
from src.config.storage_config import storage_settings
from src.utils.file_security import validate_file_upload
from src.api.config import get_settings
import logging
from src.api.cache.decorators import cached

logger = logging.getLogger(__name__)
settings = get_settings()


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

    @cached(
        key_prefix="user:subscription_tier",
        ttl=300,
        key_builder=lambda self, user_id: str(user_id),
    )
    async def _get_user_subscription_tier(self, user_id: str) -> str:
        """
        Get user's subscription tier for limit enforcement.

        Results are cached in Redis for 5 minutes to avoid redundant
        database queries during batch uploads.

        Args:
            user_id: User UUID

        Returns:
            Subscription tier: 'free', 'pro', or 'enterprise'
        """
        result = await self.db.execute(
            select(UserSubscription, SubscriptionPlan)
            .join(SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id)
            .where(
                UserSubscription.user_id == uuid.UUID(user_id) if isinstance(user_id, str) else user_id,
                UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
            )
        )
        subscription_data = result.first()

        if not subscription_data:
            return "free"

        _, plan = subscription_data

        # Map plan name to tier (case-insensitive)
        plan_name_lower = plan.name.lower()
        if "enterprise" in plan_name_lower:
            return "enterprise"
        elif "pro" in plan_name_lower or "premium" in plan_name_lower:
            return "pro"
        else:
            return "free"

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

        # Detect MIME type using filetype (cross-platform)
        kind = filetype.guess(file_content)
        if kind is None:
            # Fallback to checking file extension
            _, ext = os.path.splitext(filename)
            mime_type = self._get_mime_from_extension(ext.lower())
        else:
            mime_type = kind.mime

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

        # Comprehensive security validation (MIME type, storage quota, virus scanning)
        # Get user's subscription tier
        subscription_tier = await self._get_user_subscription_tier(user_id)

        validation_result = await validate_file_upload(
            db=self.db,
            settings=settings,
            file_bytes=file_content,
            filename=filename,
            user_id=user_id,
            workspace_id=workspace_id,
            subscription_tier=subscription_tier
        )

        if not validation_result.is_valid:
            logger.warning(f"File security validation failed: {validation_result.error_message}")
            raise ValueError(validation_result.error_message)

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
        processing_warnings = []

        try:
            # Process image if applicable
            if mime_type.startswith('image/'):
                file_io = BytesIO(file_content)

                # Validate image (CPU-bound, offload to thread)
                loop = asyncio.get_event_loop()
                is_valid, error_msg = await loop.run_in_executor(
                    None,
                    partial(
                        self.image.validate_image,
                        file_io,
                        max_size_mb=max_size / (1024 * 1024)
                    )
                )
                if not is_valid:
                    raise ValueError(error_msg)

                # Extract metadata (CPU-bound, offload to thread)
                file_io.seek(0)
                file_metadata = await loop.run_in_executor(
                    None,
                    partial(self.image.extract_metadata, file_io)
                )
                width = file_metadata.get('width')
                height = file_metadata.get('height')

                # Optimize image (CPU-bound, offload to thread)
                file_io.seek(0)
                optimized = await loop.run_in_executor(
                    None,
                    partial(self.image.optimize_image, file_io)
                )
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
                    thumbnail = await loop.run_in_executor(
                        None,
                        partial(self.image.create_thumbnail, file_io, size='medium')
                    )
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
                    processing_warnings.append(
                        f"Thumbnail generation failed: {type(e).__name__}"
                    )

            processing_status = "completed_with_warnings" if processing_warnings else "completed"

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
            file_metadata={
                **file_metadata,
                **({"processing_warnings": processing_warnings} if processing_warnings else {})
            }
        )

        self.db.add(media)
        await self.db.flush()
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
        if is_public is not None and is_public != media.is_public:
            media.is_public = is_public
            media.access_level = "public" if is_public else "private"
            
            # Update storage ACL
            try:
                await self.storage.update_file_acl(media.storage_path, is_public)
                if media.thumbnail_path:
                    await self.storage.update_file_acl(media.thumbnail_path, is_public)
                
                # Update public_url with permanent URL or presigned URL
                if is_public:
                    media.public_url = await self.storage.get_public_file_url(media.storage_path)
                    if media.thumbnail_path:
                        media.thumbnail_url = await self.storage.get_public_file_url(media.thumbnail_path)
                else:
                    media.public_url = await self.storage.get_file_url(media.storage_path)
                    if media.thumbnail_path:
                        media.thumbnail_url = await self.storage.get_file_url(media.thumbnail_path)
            except Exception as e:
                logger.error(f"Failed to update storage ACL for {media.id}: {e}")
                # We still update the DB record, but log the storage error

        media.updated_at = datetime.now(timezone.utc)

        await self.db.flush()
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
            media.deleted_at = datetime.now(timezone.utc)

        await self.db.flush()

        logger.info(f"Media deleted: {media.id} (permanent={permanent})")
        return True

    async def bulk_delete_media(
        self,
        media_ids: list[str],
        workspace_id: str,
        permanent: bool = False
    ) -> Dict[str, Any]:
        """
        Delete multiple media files.

        Args:
            media_ids: List of media UUIDs to delete
            workspace_id: Workspace UUID
            permanent: If True, permanently delete from storage and DB

        Returns:
            Dictionary with deleted and failed counts
        """
        deleted_count = 0
        failed_count = 0
        errors = []

        for media_id in media_ids:
            try:
                success = await self.delete_media(media_id, workspace_id, permanent)
                if success:
                    deleted_count += 1
                else:
                    failed_count += 1
                    errors.append(f"Media {media_id} not found")
            except Exception as e:
                failed_count += 1
                errors.append(f"Media {media_id}: {str(e)}")
                logger.error(f"Error deleting media {media_id}: {e}")

        logger.info(f"Bulk delete: {deleted_count} deleted, {failed_count} failed")
        return {
            "deleted": deleted_count,
            "failed": failed_count,
            "errors": errors
        }

    async def get_workspace_storage_usage(
        self,
        workspace_id: str
    ) -> Dict[str, Any]:
        """
        Calculate total storage usage for workspace with subscription limits.

        Args:
            workspace_id: Workspace UUID

        Returns:
            Dictionary with usage statistics including:
            - total_files: Total number of files
            - total_size: Total size in bytes
            - storage_limit: Storage limit from subscription plan (bytes)
            - usage_percentage: Percentage of storage used
            - by_type: Breakdown by file type (image, document, video)
        """

        # Get media usage
        result = await self.db.execute(
            select(
                func.count(Media.id).label("file_count"),
                func.sum(Media.file_size).label("total_bytes"),
                func.count(Media.id).filter(Media.file_type.startswith("image/")).label("image_count"),
                func.sum(Media.file_size).filter(Media.file_type.startswith("image/")).label("image_bytes"),
                func.count(Media.id).filter(
                    or_(
                        Media.file_type.startswith("application/"),
                        Media.file_type.startswith("text/")
                    )
                ).label("document_count"),
                func.sum(Media.file_size).filter(
                    or_(
                        Media.file_type.startswith("application/"),
                        Media.file_type.startswith("text/")
                    )
                ).label("document_bytes"),
                func.count(Media.id).filter(Media.file_type.startswith("video/")).label("video_count"),
                func.sum(Media.file_size).filter(Media.file_type.startswith("video/")).label("video_bytes"),
            ).where(
                and_(
                    Media.workspace_id == workspace_id,
                    Media.deleted_at.is_(None)
                )
            )
        )

        row = result.one()

        # Convert Decimal to int/float for JSON serialization
        total_bytes = int(row.total_bytes or 0)
        total_mb = float(total_bytes) / (1024 * 1024)
        total_gb = float(total_bytes) / (1024 * 1024 * 1024)

        # Query workspace owner's subscription tier for accurate storage limit
        workspace_result = await self.db.execute(
            select(WorkspaceModel.user_id).where(
                WorkspaceModel.id == workspace_id,
                WorkspaceModel.deleted_at.is_(None)
            )
        )
        owner_id = workspace_result.scalar_one_or_none()

        if owner_id:
            tier = await self._get_user_subscription_tier(str(owner_id))
        else:
            tier = "free"

        # Get storage limit from settings based on tier (returns MB)
        storage_limit_mb = settings.get_tier_storage_limit(tier)
        storage_limit_bytes = storage_limit_mb * 1024 * 1024

        # Calculate usage percentage
        usage_percentage = (total_bytes / storage_limit_bytes * 100) if storage_limit_bytes > 0 else 0

        return {
            "total_files": int(row.file_count or 0),
            "total_size": total_bytes,
            "storage_limit": storage_limit_bytes,
            "storage_limit_mb": storage_limit_mb,
            "subscription_tier": tier,
            "usage_percentage": round(usage_percentage, 2),
            "by_type": {
                "image": {
                    "count": int(row.image_count or 0),
                    "size": int(row.image_bytes or 0)
                },
                "document": {
                    "count": int(row.document_count or 0),
                    "size": int(row.document_bytes or 0)
                },
                "video": {
                    "count": int(row.video_count or 0),
                    "size": int(row.video_bytes or 0)
                }
            },
            # Legacy fields for backward compatibility
            "file_count": int(row.file_count or 0),
            "image_count": int(row.image_count or 0),
            "document_count": int(row.document_count or 0),
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

    def _get_mime_from_extension(self, ext: str) -> str:
        """
        Get MIME type from file extension.
        Fallback when filetype.guess() cannot detect the type.

        Args:
            ext: File extension (with or without dot)

        Returns:
            MIME type string
        """
        ext = ext.lstrip('.')

        # Common MIME type mappings
        mime_map = {
            # Images
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'gif': 'image/gif',
            'webp': 'image/webp',
            'svg': 'image/svg+xml',
            'bmp': 'image/bmp',
            'ico': 'image/x-icon',

            # Documents
            'pdf': 'application/pdf',
            'doc': 'application/msword',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'xls': 'application/vnd.ms-excel',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'ppt': 'application/vnd.ms-powerpoint',
            'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'txt': 'text/plain',
            'md': 'text/markdown',
            'csv': 'text/csv',
            'json': 'application/json',
            'xml': 'application/xml',

            # Videos
            'mp4': 'video/mp4',
            'webm': 'video/webm',
            'mov': 'video/quicktime',
            'avi': 'video/x-msvideo',
            'mkv': 'video/x-matroska',

            # Audio
            'mp3': 'audio/mpeg',
            'wav': 'audio/wav',
            'ogg': 'audio/ogg',
        }

        return mime_map.get(ext, 'application/octet-stream')

    async def get_media_usage(
        self,
        media_id: str,
        workspace_id: str
    ) -> Dict[str, Any]:
        """
        Get information about where a media file is being used.

        Args:
            media_id: Media UUID
            workspace_id: Workspace UUID

        Returns:
            Dictionary with usage information:
            - is_used: Whether media is used anywhere
            - featured_in: List of content using this as featured image
            - used_in_content: List of content using this media inline
            - total_usages: Total number of usages
        """
        from src.api.models.content_models.content import Content
        from src.api.models.content_models.content_media import ContentMedia

        # Check if media exists and belongs to workspace
        media = await self.get_media(media_id, workspace_id)
        if not media:
            return {
                "is_used": False,
                "featured_in": [],
                "used_in_content": [],
                "total_usages": 0
            }

        # Find content using this as featured image
        featured_result = await self.db.execute(
            select(Content.id, Content.title, Content.slug, Content.status)
            .where(
                and_(
                    Content.featured_image_id == media_id,
                    Content.workspace_id == workspace_id,
                    Content.deleted_at.is_(None)
                )
            )
        )
        featured_content = [
            {
                "id": str(row.id),
                "title": row.title,
                "slug": row.slug,
                "status": row.status,
                "usage_type": "featured_image"
            }
            for row in featured_result.all()
        ]

        # Find content using this media inline (via content_media junction)
        inline_result = await self.db.execute(
            select(
                Content.id,
                Content.title,
                Content.slug,
                Content.status,
                ContentMedia.usage_type,
                ContentMedia.position
            )
            .join(ContentMedia, ContentMedia.content_id == Content.id)
            .where(
                and_(
                    ContentMedia.media_id == media_id,
                    Content.workspace_id == workspace_id,
                    Content.deleted_at.is_(None)
                )
            )
            .order_by(Content.title)
        )
        inline_content = [
            {
                "id": str(row.id),
                "title": row.title,
                "slug": row.slug,
                "status": row.status,
                "usage_type": row.usage_type or "inline",
                "position": row.position
            }
            for row in inline_result.all()
        ]

        total_usages = len(featured_content) + len(inline_content)

        return {
            "is_used": total_usages > 0,
            "featured_in": featured_content,
            "used_in_content": inline_content,
            "total_usages": total_usages
        }
