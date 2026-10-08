import enum

from sqlalchemy import Column, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from src.api.database.base import Base
from src.api.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, WorkspaceScopedMixin


class ContentVersionSource(str, enum.Enum):
    """What left the article as this version holds it."""

    GENERATION = "generation"
    EDIT = "edit"
    RESTORE = "restore"
    PUBLISH = "publish"


class ContentVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin):
    """An article's text as a save left it, kept so the editor can go back to it (FB2.25).

    Not a row per save: the editor saves two seconds after typing stops, so the saves of one
    sitting are one version (see `ContentVersionService`). The newest few per article are kept.
    `created_at` is when the version began; `updated_at` when a later save of the same sitting
    last wrote into it.
    """

    __tablename__ = "content_versions"
    __table_args__ = (Index("ix_content_versions_content_created", "content_id", "created_at"),)

    content_id = Column(
        UUID(as_uuid=True), ForeignKey("content.id", ondelete="CASCADE"), nullable=False
    )
    # Who made it; kept when the account goes.
    created_by_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    source = Column(Text, nullable=False, default=ContentVersionSource.EDIT.value)

    # What the editor writes, and what a restore puts back.
    title = Column(Text, nullable=False)
    introduction = Column(Text, nullable=True)
    body_markdown = Column(Text, nullable=True)
    body_html = Column(Text, nullable=True)
    images_data = Column(JSONB, nullable=True)

    # Of the introduction and the body, counted when the version is written: the list shows it
    # without reading a body.
    word_count = Column(Integer, nullable=False, default=0)
