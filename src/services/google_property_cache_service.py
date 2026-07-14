"""
Google Property Cache Service

Keeps a per-workspace local cache of the Google-side properties the connected
account can access (Search Console sites + GA4 properties), so selection
screens read from the DB instead of hitting Google on every open.

Refresh policy:
- Synced once right after OAuth completes (best-effort).
- TTL-refreshed on read: if the cache is older than ``_CACHE_TTL`` (or
  ``force=True``), fetch from Google and reconcile (insert new, update
  changed, delete vanished).
- If the Google fetch fails, the stale cache is returned instead of erroring
  — a property list that's minutes old beats a broken selection screen.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.integrations.google_cached_property import (
    GoogleGa4Property,
    GoogleGscProperty,
)
from src.services.google_analytics_service import GoogleAnalyticsService
from src.services.search_console_service import SearchConsoleService
from src.utils.logger import logger

_CACHE_TTL = timedelta(minutes=15)


class GooglePropertyCacheService:
    """Reads and refreshes the cached GSC/GA4 property lists for a workspace."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_properties(
        self, workspace_id: uuid.UUID, access_token: str, force: bool = False
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Return ``{"gsc": [...], "ga4": [...]}`` from the cache, refreshing
        from Google first when stale/forced. Never raises on Google errors —
        falls back to whatever is cached.
        """
        gsc_rows = await self._cached_gsc(workspace_id)
        ga4_rows = await self._cached_ga4(workspace_id)

        if force or self._is_stale(gsc_rows) or self._is_stale(ga4_rows):
            try:
                await self.refresh_from_google(workspace_id, access_token)
                gsc_rows = await self._cached_gsc(workspace_id)
                ga4_rows = await self._cached_ga4(workspace_id)
            except Exception:
                logger.warning(
                    f"Google property refresh failed for workspace {workspace_id}; "
                    "serving cached properties.",
                    exc_info=True,
                )

        return {
            "gsc": [
                {
                    "site_url": row.site_url,
                    "permission_level": row.permission_level,
                    "synced_at": row.synced_at,
                }
                for row in gsc_rows
            ],
            "ga4": [
                {
                    "property_id": row.property_id,
                    "display_name": row.display_name,
                    "account_display_name": row.account_display_name,
                    "synced_at": row.synced_at,
                }
                for row in ga4_rows
            ],
        }

    async def refresh_from_google(
        self, workspace_id: uuid.UUID, access_token: str
    ) -> None:
        """Fetch both property lists from Google and reconcile the cache."""
        now = datetime.now(timezone.utc)

        sites = await SearchConsoleService(self.db).list_available_sites(access_token)
        await self._reconcile_gsc(workspace_id, sites, now)

        properties = await GoogleAnalyticsService(self.db).list_available_properties(
            access_token
        )
        await self._reconcile_ga4(workspace_id, properties, now)

        await self.db.flush()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _is_stale(rows: list) -> bool:
        if not rows:
            return True
        newest = max((r.synced_at for r in rows if r.synced_at), default=None)
        if newest is None:
            return True
        return datetime.now(timezone.utc) - newest > _CACHE_TTL

    async def _cached_gsc(self, workspace_id: uuid.UUID) -> List[GoogleGscProperty]:
        result = await self.db.execute(
            select(GoogleGscProperty)
            .where(GoogleGscProperty.workspace_id == workspace_id)
            .order_by(GoogleGscProperty.site_url)
        )
        return list(result.scalars().all())

    async def _cached_ga4(self, workspace_id: uuid.UUID) -> List[GoogleGa4Property]:
        result = await self.db.execute(
            select(GoogleGa4Property)
            .where(GoogleGa4Property.workspace_id == workspace_id)
            .order_by(GoogleGa4Property.display_name)
        )
        return list(result.scalars().all())

    async def _reconcile_gsc(
        self, workspace_id: uuid.UUID, sites: List[Dict[str, Any]], now: datetime
    ) -> None:
        existing = {row.site_url: row for row in await self._cached_gsc(workspace_id)}
        seen = set()
        for site in sites:
            site_url = site.get("siteUrl")
            if not site_url:
                continue
            seen.add(site_url)
            row = existing.get(site_url)
            if row:
                row.permission_level = site.get("permissionLevel")
                row.synced_at = now
            else:
                self.db.add(GoogleGscProperty(
                    workspace_id=workspace_id,
                    site_url=site_url,
                    permission_level=site.get("permissionLevel"),
                    synced_at=now,
                ))
        for site_url, row in existing.items():
            if site_url not in seen:
                await self.db.delete(row)

    async def _reconcile_ga4(
        self, workspace_id: uuid.UUID, properties: List[Dict[str, Any]], now: datetime
    ) -> None:
        existing = {row.property_id: row for row in await self._cached_ga4(workspace_id)}
        seen = set()
        for prop in properties:
            property_id = prop.get("property_id")
            if not property_id:
                continue
            seen.add(property_id)
            row = existing.get(property_id)
            if row:
                row.display_name = prop.get("display_name")
                row.account_display_name = prop.get("account_display_name")
                row.synced_at = now
            else:
                self.db.add(GoogleGa4Property(
                    workspace_id=workspace_id,
                    property_id=property_id,
                    display_name=prop.get("display_name"),
                    account_display_name=prop.get("account_display_name"),
                    synced_at=now,
                ))
        for property_id, row in existing.items():
            if property_id not in seen:
                await self.db.delete(row)
