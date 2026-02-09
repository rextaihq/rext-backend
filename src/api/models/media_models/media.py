"""
Media Model

Handles file uploads, storage, and management for the REXT platform.
Supports images, documents, videos with metadata, tagging, and organization.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, BigInteger, Boolean, DateTime, ForeignKey, ARRAY, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class Media(Base, SerializableMixin):
    """
    Media file model for managing uploaded files.

    Supports:
    - Multiple file types (images, documents, videos)
    - Multiple storage backends (S3, local)
    - Image processing (thumbnails, optimization)
    - Metadata and organization (folders, tags)
    - Access control (public, private, workspace)
    """
    __tablename__ = "media"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)

    # Foreign keys
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # File information
    filename = Column(String(255), nullable=False, comment="Generated unique filename")
    original_filename = Column(String(255), nullable=False, comment="Original upload filename")
    file_type = Column(String(100), nullable=False, index=True, comment="MIME type (e.g., image/jpeg)")
    file_size = Column(BigInteger, nullable=False, comment="File size in bytes")
    file_extension = Column(String(10), comment="File extension (e.g., .jpg)")

    # Storage
    storage_backend = Column(String(20), default="r2", comment="Storage backend: r2 (Cloudflare), local")
    storage_path = Column(String(500), nullable=False, comment="R2 key or local path")
    storage_bucket = Column(String(100), comment="R2 bucket name")
    cdn_url = Column(String(500), comment="CDN URL if available")
    public_url = Column(String(500), comment="Public access URL")

    # Metadata
    title = Column(String(255), comment="User-provided title")
    description = Column(Text, comment="User-provided description")
    alt_text = Column(String(500), comment="Alt text for images (accessibility)")
    file_metadata = Column(
        JSONB,
        default=dict,
        comment="Additional metadata: {width, height, duration, format, etc.}"
    )

    # Organization
    folder = Column(String(255), index=True, comment="Virtual folder path (e.g., /images/products)")
    tags = Column(ARRAY(String), default=list, comment="Tags for search and organization")

    # Access control
    is_public = Column(Boolean, default=False, comment="Whether file is publicly accessible")
    access_level = Column(
        String(20),
        default="private",
        comment="Access level: public, private, workspace"
    )

    # Image-specific fields (nullable for non-images)
    thumbnail_path = Column(String(500), comment="Thumbnail storage path")
    thumbnail_url = Column(String(500), comment="Thumbnail public URL")
    width = Column(Integer, comment="Image width in pixels")
    height = Column(Integer, comment="Image height in pixels")

    # Processing status
    processing_status = Column(
        String(20),
        default="pending",
        index=True,
        comment="Processing status: pending, processing, completed, failed"
    )
    processing_error = Column(Text, comment="Error message if processing failed")

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    deleted_at = Column(DateTime(timezone=True), comment="Soft delete timestamp")

    # Relationships
    workspace = relationship("WorkspaceModel", back_populates="media")
    user = relationship("Users", back_populates="media")

    def __repr__(self) -> str:
        return f"<Media(id={self.id}, filename={self.filename}, type={self.file_type})>"

    def is_image(self) -> bool:
        """Check if media is an image"""
        return self.file_type.startswith("image/")

    def is_document(self) -> bool:
        """Check if media is a document"""
        return self.file_type in [
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "text/plain",
            "text/markdown"
        ]

    def is_video(self) -> bool:
        """Check if media is a video"""
        return self.file_type.startswith("video/")

    def is_audio(self) -> bool:
        """Check if media is audio"""
        return self.file_type.startswith("audio/")

    def get_file_size_mb(self) -> float:
        """Get file size in megabytes"""
        return round(self.file_size / (1024 * 1024), 2) if self.file_size else 0.0

    def to_dict(self, **kwargs) -> dict:
        """Serialize media to dictionary"""
        data = super().to_dict(**kwargs)

        # Add computed fields
        data["file_size_mb"] = self.get_file_size_mb()
        data["is_image"] = self.is_image()
        data["is_document"] = self.is_document()
        data["is_video"] = self.is_video()
        data["is_audio"] = self.is_audio()

        return data
