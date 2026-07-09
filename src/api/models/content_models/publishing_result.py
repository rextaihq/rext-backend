import enum
from sqlalchemy import Boolean, Column, String, Text, DateTime, ForeignKey, BigInteger, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from src.api.database.base import Base
from src.api.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class PublishingStatus(str, enum.Enum):
    PUBLISHED = "published"
    SCHEDULED = "scheduled"
    DRAFT = "draft"
    TRASHED = "trashed"
    DELETED = "deleted"
    UNKNOWN = "unknown"

# ContentPublishingResult model is used to track the publishing state of content to different platforms.
# It is used to track the publishing state of content to different platforms.
class ContentPublishingResult(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Tracks per-site publishing state for content.
    Identity is by platform-native integer IDs — never by URL (mutable).
    One row per (content, site) pair enforced at DB level.
    """
    __tablename__ = "content_publishing_results"
    __table_args__ = (
        UniqueConstraint("content_id", "site_id", name="uq_content_publishing_result_content_site"),
    )

    content_id = Column(
        UUID(as_uuid=True),
        ForeignKey("content.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site_id = Column(
        UUID(as_uuid=True),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- Immutable platform-native IDs (source of truth for CMS identity) ---
    wp_post_id = Column(Integer, nullable=True)
    shopify_article_id = Column(BigInteger, nullable=True)
    # Needed to query Shopify article status without guessing the blog
    shopify_blog_id = Column(BigInteger, nullable=True)

    # Cached URL — informational only, may go stale, never used for identity
    external_url = Column(String, nullable=True)

    # Status tracking
    status = Column(String, nullable=False, default=PublishingStatus.UNKNOWN)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    sync_error = Column(Text, nullable=True)
    scheduled_publish_at = Column(DateTime(timezone=True), nullable=True)

    # GSC/GA4 analytics tracking is opt-in per (content, site): only articles
    # the user explicitly selected are synced/scored by the Google modules.
    tracking_enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    tracking_enabled_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return (
            f"<ContentPublishingResult("
            f"content_id={self.content_id}, site_id={self.site_id}, "
            f"wp_post_id={self.wp_post_id}, shopify_article_id={self.shopify_article_id}, "
            f"status={self.status})>"
        )
