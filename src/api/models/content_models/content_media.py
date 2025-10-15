"""
ContentMedia Model

Junction table for tracking media used in content.
Enables finding which content uses specific media files and vice versa.
"""

from sqlalchemy import Column, String, Integer, ForeignKey, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from src.api.database.database import Base
from src.api.models.base import SerializableMixin
from datetime import datetime
import uuid


class ContentMedia(Base, SerializableMixin):
    """
    Junction table linking content to media.

    Tracks all media files used within content body (not just featured image).
    Useful for:
    - Finding all content that uses a specific media file
    - Listing all media used in a piece of content
    - Preventing deletion of media that's in use
    - Identifying orphaned media files
    """
    __tablename__ = "content_media"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)

    content_id = Column(
        UUID(as_uuid=True),
        ForeignKey("content.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    media_id = Column(
        UUID(as_uuid=True),
        ForeignKey("media.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    usage_type = Column(
        String(50),
        nullable=True,
        comment="How media is used: inline, gallery, attachment, embed, etc."
    )

    position = Column(
        Integer,
        nullable=True,
        comment="Position/order in content (for sorting)"
    )

    created_at = Column(
        TIMESTAMP(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )

    # Relationships
    content = relationship("Content", backref="media_items")
    media = relationship("Media", backref="used_in_content")

    def __repr__(self) -> str:
        return f"<ContentMedia(content_id={self.content_id}, media_id={self.media_id})>"
