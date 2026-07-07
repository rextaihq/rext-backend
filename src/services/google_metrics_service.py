"""
Google Metrics Service

Handles querying and aggregating metrics from Google Search Console and GA4.
"""

import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, or_, and_, cast
from sqlalchemy.dialects.postgresql import JSONB

from src.api.models.analytics_models.google_analytics_metric import GoogleAnalyticsMetric
from src.api.models.content_models.content import Content
from src.api.models.content_models.publishing_result import ContentPublishingResult
from src.utils.url_normalizer import normalize_url


class GoogleMetricsService:
    """Service for querying Google integration metrics."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def _build_base_query(
        self,
        workspace_id: uuid.UUID,
        article_id: Optional[uuid.UUID] = None,
        source: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ):
        """Build a base query with common filters."""
        query = select(GoogleAnalyticsMetric).where(
            GoogleAnalyticsMetric.workspace_id == workspace_id
        )

        if source:
            query = query.where(GoogleAnalyticsMetric.source == source)

        if start_date:
            try:
                date_val = datetime.strptime(start_date, "%Y-%m-%d").date()
                query = query.where(GoogleAnalyticsMetric.date >= date_val)
            except ValueError:
                pass

        if end_date:
            try:
                date_val = datetime.strptime(end_date, "%Y-%m-%d").date()
                query = query.where(GoogleAnalyticsMetric.date <= date_val)
            except ValueError:
                pass

        return query

    async def get_metrics(
        self,
        workspace_id: uuid.UUID,
        article_id: Optional[uuid.UUID] = None,
        source: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Get raw metrics with pagination."""
        query = self._build_base_query(workspace_id, article_id, source, start_date, end_date)

        if article_id:
            # Need to find the external URL for this article
            stmt = select(ContentPublishingResult.external_url).where(
                ContentPublishingResult.content_id == article_id,
                ContentPublishingResult.external_url.is_not(None)
            )
            result = await self.db.execute(stmt)
            external_urls = result.scalars().all()
            
            if external_urls:
                normalized_urls = [normalize_url(u) for u in external_urls if normalize_url(u)]
                if normalized_urls:
                    query = query.where(GoogleAnalyticsMetric.article_external_url.in_(normalized_urls))

        # Default date range to last 30 days if not provided
        if not start_date and not end_date:
            thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).date()
            query = query.where(GoogleAnalyticsMetric.date >= thirty_days_ago)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        count_result = await self.db.execute(count_query)
        total_count = count_result.scalar_one_or_none() or 0

        # Get paginated data
        query = query.order_by(desc(GoogleAnalyticsMetric.date)).limit(limit).offset(offset)
        result = await self.db.execute(query)
        records = result.scalars().all()

        data = []
        for r in records:
            data.append({
                "date": r.date.isoformat(),
                "source": r.source,
                "article_external_url": r.article_external_url,
                "query_keyword": r.query_keyword,
                "metrics": r.metrics
            })

        return {
            "data": data,
            "total_count": total_count,
            "limit": limit,
            "offset": offset
        }

    async def get_article_summary(
        self,
        workspace_id: uuid.UUID,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get aggregated metrics grouped by article."""
        query = self._build_base_query(workspace_id, None, None, start_date, end_date)
        
        # We need to extract JSONB fields properly
        clicks = cast(GoogleAnalyticsMetric.metrics['clicks'].astext, sqlalchemy.Integer)
        impressions = cast(GoogleAnalyticsMetric.metrics['impressions'].astext, sqlalchemy.Integer)
        ctr = cast(GoogleAnalyticsMetric.metrics['ctr'].astext, sqlalchemy.Float)
        position = cast(GoogleAnalyticsMetric.metrics['position'].astext, sqlalchemy.Float)
        
        sessions = cast(GoogleAnalyticsMetric.metrics['sessions'].astext, sqlalchemy.Integer)
        active_users = cast(GoogleAnalyticsMetric.metrics['activeUsers'].astext, sqlalchemy.Integer)
        engagement = cast(GoogleAnalyticsMetric.metrics['engagementRate'].astext, sqlalchemy.Float)
        conversions = cast(GoogleAnalyticsMetric.metrics['conversions'].astext, sqlalchemy.Float)
        
        stmt = (
            select(
                GoogleAnalyticsMetric.article_external_url,
                ContentPublishingResult.content_id,
                Content.title,
                
                # GSC Aggregations
                func.sum(clicks).filter(GoogleAnalyticsMetric.source == 'gsc').label('total_clicks'),
                func.sum(impressions).filter(GoogleAnalyticsMetric.source == 'gsc').label('total_impressions'),
                func.avg(ctr).filter(GoogleAnalyticsMetric.source == 'gsc').label('avg_ctr'),
                func.avg(position).filter(GoogleAnalyticsMetric.source == 'gsc').label('avg_position'),
                
                # GA4 Aggregations
                func.sum(sessions).filter(GoogleAnalyticsMetric.source == 'ga4').label('total_sessions'),
                func.sum(active_users).filter(GoogleAnalyticsMetric.source == 'ga4').label('total_active_users'),
                func.avg(engagement).filter(GoogleAnalyticsMetric.source == 'ga4').label('avg_engagement_rate'),
                func.sum(conversions).filter(GoogleAnalyticsMetric.source == 'ga4').label('total_conversions'),
            )
            .outerjoin(
                ContentPublishingResult, 
                ContentPublishingResult.external_url == GoogleAnalyticsMetric.article_external_url
            )
            .outerjoin(Content, Content.id == ContentPublishingResult.content_id)
            .where(GoogleAnalyticsMetric.workspace_id == workspace_id)
        )
        
        if start_date:
            try:
                date_val = datetime.strptime(start_date, "%Y-%m-%d").date()
                stmt = stmt.where(GoogleAnalyticsMetric.date >= date_val)
            except ValueError:
                pass
                
        if end_date:
            try:
                date_val = datetime.strptime(end_date, "%Y-%m-%d").date()
                stmt = stmt.where(GoogleAnalyticsMetric.date <= date_val)
            except ValueError:
                pass

        # Group and order
        stmt = stmt.group_by(
            GoogleAnalyticsMetric.article_external_url,
            ContentPublishingResult.content_id,
            Content.title
        ).order_by(desc('total_clicks'))
        
        # Need to import sqlalchemy inside if not fully available
        import sqlalchemy

        result = await self.db.execute(stmt)
        
        summaries = []
        for row in result.all():
            summaries.append({
                "article_url": row.article_external_url,
                "article_id": str(row.content_id) if row.content_id else None,
                "title": row.title,
                "gsc_metrics": {
                    "clicks": int(row.total_clicks) if row.total_clicks is not None else 0,
                    "impressions": int(row.total_impressions) if row.total_impressions is not None else 0,
                    "avg_ctr": float(row.avg_ctr) if row.avg_ctr is not None else 0.0,
                    "avg_position": float(row.avg_position) if row.avg_position is not None else 0.0,
                },
                "ga4_metrics": {
                    "sessions": int(row.total_sessions) if row.total_sessions is not None else 0,
                    "active_users": int(row.total_active_users) if row.total_active_users is not None else 0,
                    "avg_engagement_rate": float(row.avg_engagement_rate) if row.avg_engagement_rate is not None else 0.0,
                    "conversions": float(row.total_conversions) if row.total_conversions is not None else 0.0,
                }
            })
            
        return summaries

    async def get_top_queries(
        self,
        workspace_id: uuid.UUID,
        article_id: Optional[uuid.UUID] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get top GSC queries aggregated by keyword."""
        import sqlalchemy
        
        clicks = cast(GoogleAnalyticsMetric.metrics['clicks'].astext, sqlalchemy.Integer)
        impressions = cast(GoogleAnalyticsMetric.metrics['impressions'].astext, sqlalchemy.Integer)
        ctr = cast(GoogleAnalyticsMetric.metrics['ctr'].astext, sqlalchemy.Float)
        position = cast(GoogleAnalyticsMetric.metrics['position'].astext, sqlalchemy.Float)

        stmt = (
            select(
                GoogleAnalyticsMetric.query_keyword,
                func.sum(clicks).label('total_clicks'),
                func.sum(impressions).label('total_impressions'),
                func.avg(ctr).label('avg_ctr'),
                func.avg(position).label('avg_position'),
            )
            .where(
                GoogleAnalyticsMetric.workspace_id == workspace_id,
                GoogleAnalyticsMetric.source == 'gsc',
                GoogleAnalyticsMetric.query_keyword != ''
            )
        )

        if article_id:
            # Match specific article URLs
            url_stmt = select(ContentPublishingResult.external_url).where(
                ContentPublishingResult.content_id == article_id,
                ContentPublishingResult.external_url.is_not(None)
            )
            url_result = await self.db.execute(url_stmt)
            external_urls = url_result.scalars().all()
            
            if external_urls:
                normalized_urls = [normalize_url(u) for u in external_urls if normalize_url(u)]
                if normalized_urls:
                    stmt = stmt.where(GoogleAnalyticsMetric.article_external_url.in_(normalized_urls))
            else:
                return [] # Article has no published URLs

        if start_date:
            try:
                date_val = datetime.strptime(start_date, "%Y-%m-%d").date()
                stmt = stmt.where(GoogleAnalyticsMetric.date >= date_val)
            except ValueError:
                pass
                
        if end_date:
            try:
                date_val = datetime.strptime(end_date, "%Y-%m-%d").date()
                stmt = stmt.where(GoogleAnalyticsMetric.date <= date_val)
            except ValueError:
                pass

        stmt = stmt.group_by(GoogleAnalyticsMetric.query_keyword).order_by(desc('total_clicks')).limit(limit)
        
        result = await self.db.execute(stmt)
        
        queries = []
        for row in result.all():
            queries.append({
                "keyword": row.query_keyword,
                "metrics": {
                    "clicks": int(row.total_clicks) if row.total_clicks is not None else 0,
                    "impressions": int(row.total_impressions) if row.total_impressions is not None else 0,
                    "avg_ctr": float(row.avg_ctr) if row.avg_ctr is not None else 0.0,
                    "avg_position": float(row.avg_position) if row.avg_position is not None else 0.0,
                }
            })
            
        return queries
