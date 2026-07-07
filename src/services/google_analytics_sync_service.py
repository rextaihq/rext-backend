"""
Google Analytics Synchronization Service

Handles fetching and storing metrics from Google Search Console and GA4.
"""

import uuid
from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta, timezone
import httpx
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, String, cast
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from src.api.models.integrations.workspace_google_connection import WorkspaceGoogleConnection
from src.api.models.content_models.publishing_result import ContentPublishingResult
from src.api.models.content_models.content import Content
from src.api.models.analytics_models.google_analytics_metric import GoogleAnalyticsMetric
from src.services.google_oauth_service import GoogleOAuthService
from src.utils.url_normalizer import normalize_url
from src.utils.logger import logger


class GoogleAnalyticsSyncService:
    """Service for syncing data from GSC and GA4."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.oauth_service = GoogleOAuthService(db)

    async def get_published_articles(self, workspace_id: uuid.UUID) -> List[str]:
        """Get list of published article external URLs for a workspace."""
        stmt = (
            select(ContentPublishingResult.external_url)
            .join(Content, ContentPublishingResult.content_id == Content.id)
            .where(
                Content.workspace_id == workspace_id,
                ContentPublishingResult.external_url.is_not(None)
            )
            .distinct()
        )
        result = await self.db.execute(stmt)
        urls = result.scalars().all()
        
        # Normalize URLs
        return [normalize_url(url) for url in urls if normalize_url(url)]

    async def fetch_gsc_metrics(
        self,
        site_url: str,
        urls: List[str],
        start_date: str,
        end_date: str,
        token: str,
    ) -> List[Dict[str, Any]]:
        """Fetch metrics from Google Search Console API."""
        if not urls:
            return []

        all_rows = []
        # Batch URLs to avoid hitting API limits (max 2000 in regex, but let's be safe with 100)
        batch_size = 100
        for i in range(0, len(urls), batch_size):
            batch_urls = urls[i:i + batch_size]
            
            # Create regex pattern for URLs
            url_pattern = "|".join(batch_urls)
            
            request_body = {
                "startDate": start_date,
                "endDate": end_date,
                "dimensions": ["page", "query", "date"],
                "dimensionFilterGroups": [
                    {
                        "filters": [
                            {
                                "dimension": "page",
                                "operator": "includingRegex",
                                "expression": url_pattern
                            }
                        ]
                    }
                ],
                "rowLimit": 25000
            }

            try:
                # Exponential backoff for rate limits
                for attempt in range(3):
                    async with httpx.AsyncClient() as client:
                        response = await client.post(
                            f"https://www.googleapis.com/webmasters/v3/sites/{httpx.URL(site_url)}/searchAnalytics/query",
                            headers={"Authorization": f"Bearer {token}"},
                            json=request_body,
                            timeout=60.0,
                        )
                        
                        if response.status_code == 429:
                            await asyncio.sleep(2 ** attempt)
                            continue
                            
                        response.raise_for_status()
                        data = response.json()
                        rows = data.get("rows", [])
                        all_rows.extend(rows)
                        break
                        
            except Exception as e:
                logger.error(f"Failed to fetch GSC metrics for site {site_url}: {str(e)}")
                # Continue with next batch instead of failing completely
                continue

        return all_rows

    async def fetch_ga4_metrics(
        self,
        property_id: str,
        urls: List[str],
        start_date: str,
        end_date: str,
        token: str,
    ) -> List[Dict[str, Any]]:
        """Fetch metrics from Google Analytics 4 API."""
        if not urls:
            return []

        all_rows = []
        batch_size = 100
        
        # Ensure property_id has correct format (e.g., "properties/12345")
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"
            
        for i in range(0, len(urls), batch_size):
            batch_urls = urls[i:i + batch_size]
            
            # We want exact matches on page paths
            # Since GA4 pagePath doesn't include the domain, we might need a more complex match
            # But the plan specifies using inListFilter, we assume URLs are mapped to paths
            paths = [url.replace("https://", "").replace("http://", "").split("/", 1)[-1] for url in batch_urls]
            paths = ["/" + p if not p.startswith("/") else p for p in paths]
            
            request_body = {
                "dateRanges": [{"startDate": start_date, "endDate": end_date}],
                "dimensions": [{"name": "date"}, {"name": "pagePath"}],
                "metrics": [
                    {"name": "sessions"},
                    {"name": "activeUsers"},
                    {"name": "engagementRate"},
                    {"name": "conversions"}
                ],
                "dimensionFilter": {
                    "filter": {
                        "fieldName": "pagePath",
                        "inListFilter": {"values": paths}
                    }
                },
                "limit": 100000
            }

            try:
                for attempt in range(3):
                    async with httpx.AsyncClient() as client:
                        response = await client.post(
                            f"https://analyticsdata.googleapis.com/v1beta/{property_id}:runReport",
                            headers={"Authorization": f"Bearer {token}"},
                            json=request_body,
                            timeout=60.0,
                        )
                        
                        if response.status_code == 429:
                            await asyncio.sleep(2 ** attempt)
                            continue
                            
                        response.raise_for_status()
                        data = response.json()
                        rows = data.get("rows", [])
                        all_rows.extend(rows)
                        break
                        
            except Exception as e:
                logger.error(f"Failed to fetch GA4 metrics for property {property_id}: {str(e)}")
                continue

        return all_rows

    async def store_metrics(
        self,
        workspace_id: uuid.UUID,
        metrics_data: List[Dict[str, Any]],
        source: str
    ) -> int:
        """Store metrics with UPSERT logic."""
        if not metrics_data:
            return 0
            
        inserted_count = 0
        batch_size = 1000
        
        # Prepare records
        records = []
        if source == 'gsc':
            for row in metrics_data:
                keys = row.get("keys", [])
                if len(keys) < 3:
                    continue
                    
                page, query, date_str = keys[0], keys[1], keys[2]
                
                # Format date YYYY-MM-DD to datetime
                try:
                    date_val = datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    continue
                    
                metrics = {
                    "clicks": row.get("clicks", 0),
                    "impressions": row.get("impressions", 0),
                    "ctr": row.get("ctr", 0),
                    "position": row.get("position", 0)
                }
                
                records.append({
                    "workspace_id": workspace_id,
                    "article_external_url": normalize_url(page),
                    "date": date_val,
                    "source": "gsc",
                    "metrics": metrics,
                    "query_keyword": query
                })
        elif source == 'ga4':
            for row in metrics_data:
                dimension_values = [d.get("value") for d in row.get("dimensionValues", [])]
                metric_values = [m.get("value") for m in row.get("metricValues", [])]
                
                if len(dimension_values) < 2 or len(metric_values) < 4:
                    continue
                    
                date_str, page_path = dimension_values[0], dimension_values[1]
                
                try:
                    date_val = datetime.strptime(date_str, "%Y%m%d").date()
                except ValueError:
                    continue
                    
                # We need the full URL, but GA4 gives us pagePath. We'll store it as is and 
                # normalization logic will handle matching it during queries.
                
                metrics = {
                    "sessions": int(metric_values[0]) if metric_values[0] else 0,
                    "activeUsers": int(metric_values[1]) if metric_values[1] else 0,
                    "engagementRate": float(metric_values[2]) if metric_values[2] else 0.0,
                    "conversions": float(metric_values[3]) if metric_values[3] else 0.0
                }
                
                records.append({
                    "workspace_id": workspace_id,
                    "article_external_url": page_path,
                    "date": date_val,
                    "source": "ga4",
                    "metrics": metrics,
                    "query_keyword": ""  # GA4 doesn't have query keyword at this level
                })

        # Insert records in batches
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            
            stmt = insert(GoogleAnalyticsMetric).values(batch)
            
            # On conflict update metrics
            update_dict = {
                "metrics": stmt.excluded.metrics
            }
            
            stmt = stmt.on_conflict_do_update(
                index_elements=["workspace_id", "article_external_url", "date", "source", "query_keyword"],
                set_=update_dict
            )
            
            try:
                result = await self.db.execute(stmt)
                inserted_count += result.rowcount
            except IntegrityError as e:
                logger.error(f"Database integrity error storing metrics: {str(e)}")
                await self.db.rollback()
                continue
                
        await self.db.flush()
        return inserted_count

    async def sync_workspace(self, workspace_id: uuid.UUID, backfill: bool = False) -> Dict[str, Any]:
        """Orchestrate sync for a workspace."""
        # Get connection
        result = await self.db.execute(
            select(WorkspaceGoogleConnection).where(
                WorkspaceGoogleConnection.workspace_id == workspace_id
            )
        )
        connection = result.scalar_one_or_none()
        
        if not connection or (not connection.gsc_site_url and not connection.ga4_property_id):
            return {"status": "skipped", "reason": "No active Google connection or missing properties"}

        # Get token
        try:
            token = await self.oauth_service.get_valid_token(workspace_id)
        except Exception as e:
            return {"status": "error", "reason": f"Authentication failed: {str(e)}"}

        # Calculate date range
        end_date = datetime.now(timezone.utc).date() - timedelta(days=1)  # Yesterday
        
        if backfill:
            # 16 months (approx 480 days)
            start_date = end_date - timedelta(days=480)
        else:
            if connection.last_synced_at:
                start_date = connection.last_synced_at.date()
            else:
                start_date = end_date - timedelta(days=3)  # Just a few days if no sync history

        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")

        urls = await self.get_published_articles(workspace_id)
        if not urls:
            return {"status": "skipped", "reason": "No published articles found"}

        summary = {"status": "success", "gsc_records": 0, "ga4_records": 0}

        # Fetch and store GSC data
        if connection.gsc_site_url:
            gsc_data = await self.fetch_gsc_metrics(
                connection.gsc_site_url, urls, start_date_str, end_date_str, token
            )
            gsc_inserted = await self.store_metrics(workspace_id, gsc_data, "gsc")
            summary["gsc_records"] = gsc_inserted

        # Fetch and store GA4 data
        if connection.ga4_property_id:
            ga4_data = await self.fetch_ga4_metrics(
                connection.ga4_property_id, urls, start_date_str, end_date_str, token
            )
            ga4_inserted = await self.store_metrics(workspace_id, ga4_data, "ga4")
            summary["ga4_records"] = ga4_inserted

        # Update sync timestamps
        connection.last_synced_at = datetime.now(timezone.utc)
        if backfill:
            connection.last_backfill_completed_at = datetime.now(timezone.utc)
            
        await self.db.flush()
        
        logger.info(f"Completed Google Analytics sync for workspace {workspace_id}: {summary}")
        return summary
