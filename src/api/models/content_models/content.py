from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship

from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import (
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    WorkspaceScopedMixin,
)


class Content(
    Base,
    SerializableMixin,
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    WorkspaceScopedMixin,
    SoftDeleteMixin,
):
    """Main content table - stores core content and metadata"""

    __tablename__ = "content"

    # id, workspace_id, created_at, updated_at, deleted_at provided by mixins
    created_by_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True
    )
    # Who put it in the trash, for the trash's listing (G45).
    deleted_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Core content fields
    title = Column(Text, nullable=False)
    slug = Column(Text, nullable=False, index=True)
    introduction = Column(Text, nullable=True)
    body_markdown = Column(Text, nullable=True)
    body_html = Column(Text, nullable=True)

    # Per-workspace uniqueness. A title is unique only among the live articles written by hand:
    # a generated article (it has its thread) may repeat one, since the title step offers the same
    # titles for a keyword (G55). The slug stays unique across the trash too.
    __table_args__ = (
        Index(
            "uq_content_workspace_title_by_hand",
            "workspace_id",
            "title",
            unique=True,
            postgresql_where=text("langgraph_thread_id IS NULL AND deleted_at IS NULL"),
        ),
        UniqueConstraint("workspace_id", "slug", name="uq_content_workspace_slug"),
        # The workspace's trash, newest first, and the purge of what's been there too long (G45).
        Index(
            "ix_content_trash",
            "workspace_id",
            "deleted_at",
            postgresql_where=text("deleted_at IS NOT NULL"),
        ),
    )

    # Metadata and Status
    status = Column(Text, nullable=True, default="draft")
    content_language = Column(Text, nullable=True, default="English")
    tags = Column(ARRAY(Text), nullable=True, comment="Tags (common to content)")
    category = Column(Text, nullable=True, comment="WordPress category name")

    # LangGraph workflow tracking
    langgraph_thread_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # The author persona chosen in the content outline step. Kept on the row
    # rather than read back out of the generation thread because it outlives the
    # run: publishing (and republishing) has to name the same author months
    # later, long after the graph state is of any interest.
    persona_id = Column(
        UUID(as_uuid=True),
        ForeignKey("persona.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Author persona selected during the content outline step",
    )

    # Media and Schema (remaining on content for now)
    images_data = Column(JSONB, nullable=True, comment="Inline images data")
    links_data = Column(JSONB, nullable=True, comment="Internal and outbound links")
    schema_markup = Column(JSONB, nullable=True, comment="Structured data/schema markup")

    # WordPress publishing fields
    wordpress_post_id = Column(Integer, nullable=True)
    wordpress_url = Column(Text, nullable=True)
    wordpress_published_at = Column(DateTime(timezone=True), nullable=True)

    # Shopify publishing fields
    from sqlalchemy import BigInteger

    shopify_article_id = Column(BigInteger, nullable=True)
    shopify_article_url = Column(Text, nullable=True)
    shopify_published_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    workspace = relationship("WorkspaceModel", back_populates="content_items")
    created_by = relationship("Users", foreign_keys=[created_by_user_id])
    seo_data = relationship(
        "ContentSEOData",
        back_populates="content",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
