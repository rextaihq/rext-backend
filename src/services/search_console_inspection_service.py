"""
Search Console Inspection Service - URL indexing status sync

Responsibilities:
- Call the URL Inspection API for a single published URL and upsert its
  current index status into ContentIndexStatus.

Does NOT:
- Manage OAuth tokens (see GoogleOAuthService.get_valid_access_token).
- Manage quota/rate limiting (see src/utils/google_quota_limiter.py) or
  decide which URLs to inspect and in what order (see
  src/api/tasks/google_index_inspection_task.py).
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.content_models.content_index_status import ContentIndexStatus
from src.api.models.content_models.publishing_result import ContentPublishingResult
from src.api.models.integrations.google_site_mapping import GoogleSiteMapping
from src.web.search_console_inspection import URLInspectionClient


class SearchConsoleInspectionService:
    """Service for Search Console URL Inspection syncing."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def inspect_and_upsert(
        self,
        publishing_result: ContentPublishingResult,
        mapping: GoogleSiteMapping,
        access_token: str,
    ) -> Optional[ContentIndexStatus]:
        """Inspect a single published URL and upsert its ContentIndexStatus row."""
        if not mapping.gsc_site_url or not publishing_result.external_url:
            return None

        async with URLInspectionClient(access_token) as client:
            data = await client.inspect_url(
                site_url=mapping.gsc_site_url,
                inspection_url=publishing_result.external_url,
            )

        index_result = (data.get("inspectionResult") or {}).get("indexStatusResult") or {}
        now = datetime.now(timezone.utc)

        last_crawl_time = None
        raw_crawl_time = index_result.get("lastCrawlTime")
        if raw_crawl_time:
            try:
                last_crawl_time = datetime.fromisoformat(raw_crawl_time.replace("Z", "+00:00"))
            except ValueError:
                last_crawl_time = None

        existing_result = await self.db.execute(
            select(ContentIndexStatus).where(
                ContentIndexStatus.publishing_result_id == publishing_result.id
            )
        )
        status = existing_result.scalar_one_or_none()

        fields = dict(
            verdict=index_result.get("verdict"),
            coverage_state=index_result.get("coverageState"),
            robots_txt_state=index_result.get("robotsTxtState"),
            indexing_state=index_result.get("indexingState"),
            page_fetch_state=index_result.get("pageFetchState"),
            last_crawl_time=last_crawl_time,
            inspected_at=now,
            raw_response=data,
        )

        if status:
            for key, value in fields.items():
                setattr(status, key, value)
        else:
            status = ContentIndexStatus(
                content_id=publishing_result.content_id,
                publishing_result_id=publishing_result.id,
                workspace_id=mapping.workspace_id,
                **fields,
            )
            self.db.add(status)

        await self.db.flush()
        return status
