"""
Shared filter for the Google modules' opt-in content tracking.

The onboarding flow has users explicitly select which published articles to
track (ContentPublishingResult.tracking_enabled). Every Google-module read
surface (dashboard, inventory, health, opportunities) must scope its content
set to that selection — this subquery is the single definition of "tracked".
"""

from sqlalchemy import select

from src.api.models.content_models.publishing_result import (
    ContentPublishingResult,
    PublishingStatus,
)


def tracked_content_ids_subquery():
    """Content ids with at least one published, tracking-enabled publishing result."""
    return (
        select(ContentPublishingResult.content_id)
        .where(
            ContentPublishingResult.status == PublishingStatus.PUBLISHED,
            ContentPublishingResult.tracking_enabled.is_(True),
        )
        .scalar_subquery()
    )
