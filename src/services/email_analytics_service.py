"""
Email Analytics Service

Service for calculating email analytics and performance metrics.
Supports workspace-scoped filtering for multi-tenancy.
"""
from datetime import datetime, timedelta
from src.utils.datetime_utils import utc_now
from typing import Optional, Dict, List, Any
from uuid import UUID

from sqlalchemy import func, case, and_, or_, cast, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.api.models.email_models.email_log import EmailLog
from src.api.models.email_models.email_event import EmailEvent
from src.utils.logger import logger


class EmailAnalyticsService:
    """Service for email analytics calculations with multi-tenancy support"""

    _DATE_RANGE_DAYS = {
        "7d": 7,
        "30d": 30,
        "90d": 90,
    }

    def __init__(self, db: AsyncSession):
        self.db = db
        self.log = logger.bind(service="EmailAnalyticsService")

    def _parse_date_range(self, date_range: str) -> datetime:
        """Parse allowed date range string to start date."""
        now = utc_now()

        if date_range not in self._DATE_RANGE_DAYS:
            raise ValueError(f"Unsupported date_range: {date_range}")

        return now - timedelta(days=self._DATE_RANGE_DAYS[date_range])

    def _build_base_filters(
        self,
        start_date: datetime,
        workspace_id: Optional[UUID] = None
    ) -> List:
        """Build base query filters including optional workspace filter"""
        filters = [EmailLog.created_at >= start_date]
        if workspace_id:
            filters.append(EmailLog.workspace_id == workspace_id)
        return filters

    async def _get_event_count(
        self,
        event_type: str,
        start_date: datetime,
        workspace_id: Optional[UUID] = None
    ) -> int:
        """
        Get distinct email count for a specific event type.

        Builds the appropriate query based on whether workspace filtering is needed.
        When workspace_id is provided, joins EmailEvent with EmailLog to filter
        by workspace. Without workspace_id, queries EmailEvent directly for better
        performance.

        Args:
            event_type: Event type to count (e.g., "opened", "clicked", "complained")
            start_date: Start date for the query range
            workspace_id: Optional workspace ID for multi-tenancy filtering

        Returns:
            Count of distinct email_log_ids with the specified event type
        """
        base_query = select(
            func.count(
                func.distinct(
                    func.coalesce(
                        cast(EmailEvent.email_log_id, String),
                        func.nullif(EmailEvent.provider_message_id, '')
                    )
                )
            )
        )

        conditions = [
            or_(
                EmailEvent.received_at >= start_date,
                EmailEvent.created_at >= start_date
            ),
            EmailEvent.event_type.in_([event_type, f"email.{event_type}"])
        ]

        if workspace_id:
            base_query = base_query.select_from(EmailEvent).join(
                EmailLog,
                or_(
                    EmailEvent.email_log_id == EmailLog.id,
                    and_(
                        EmailEvent.provider_message_id.isnot(None),
                        EmailLog.provider_message_id.isnot(None),
                        EmailEvent.provider_message_id == EmailLog.provider_message_id
                    ),
                    and_(
                        EmailEvent.email_log_id.is_(None),
                        EmailLog.to_email == func.jsonb_extract_path_text(EmailEvent.event_data, 'to', '0')
                    )
                )
            )
            conditions.append(EmailLog.workspace_id == workspace_id)

        result = await self.db.execute(base_query.where(and_(*conditions)))
        return result.scalar() or 0

    def _event_flags_subquery(self, start_date: datetime):
        """
        One row per email with 0/1 flags for whether that email was
        ever opened / clicked in the window. Matches on both email_log_id and provider_message_id.
        """
        return (
            select(
                EmailEvent.email_log_id.label("email_log_id"),
                EmailEvent.provider_message_id.label("provider_message_id"),
                func.max(
                    case((EmailEvent.event_type == "opened", 1), else_=0)
                ).label("opened"),
                func.max(
                    case((EmailEvent.event_type == "clicked", 1), else_=0)
                ).label("clicked"),
            )
            .where(
                EmailEvent.received_at >= start_date
            )
            .group_by(EmailEvent.email_log_id, EmailEvent.provider_message_id)
            .subquery()
        )

    async def get_overview_stats(
        self,
        date_range: str = "30d",
        workspace_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Calculate email overview statistics

        Args:
            date_range: Date range string (e.g., "7d", "30d", "90d")
            workspace_id: Optional workspace ID to filter by workspace (multi-tenancy)

        Returns:
            Dictionary with overview statistics
        """
        start_date = self._parse_date_range(date_range)
        base_filters = self._build_base_filters(start_date, workspace_id)

        # Query total sent
        total_sent_query = select(func.count(EmailLog.id)).where(
            and_(*base_filters)
        )
        total_sent_result = await self.db.execute(total_sent_query)
        total_sent = total_sent_result.scalar() or 0

        # Query delivered count
        delivered_filters = base_filters + [
            or_(
                EmailLog.status == "delivered",
                EmailLog.delivered_at.isnot(None)
            )
        ]
        delivered_query = select(func.count(EmailLog.id)).where(
            and_(*delivered_filters)
        )
        delivered_result = await self.db.execute(delivered_query)
        delivered = delivered_result.scalar() or 0

        # For event queries, we need to join with EmailLog to filter by workspace
        # Query event counts (workspace filter applied automatically if workspace_id provided)
        opened = await self._get_event_count("opened", start_date, workspace_id)
        clicked = await self._get_event_count("clicked", start_date, workspace_id)
        complained = await self._get_event_count("complained", start_date, workspace_id)

        # Ensure delivered is at least the number of opened or clicked emails
        effective_delivered = max(delivered, opened, clicked)

        # Query bounced count
        bounced_filters = base_filters + [EmailLog.status == "bounced"]
        bounced_query = select(func.count(EmailLog.id)).where(
            and_(*bounced_filters)
        )
        bounced_result = await self.db.execute(bounced_query)
        bounced = bounced_result.scalar() or 0

        # Calculate rates
        delivery_rate = (effective_delivered / total_sent * 100) if total_sent > 0 else 0
        open_rate = (opened / effective_delivered * 100) if effective_delivered > 0 else 0
        click_rate = (clicked / effective_delivered * 100) if effective_delivered > 0 else 0
        bounce_rate = (bounced / total_sent * 100) if total_sent > 0 else 0
        complaint_rate = (complained / effective_delivered * 100) if effective_delivered > 0 else 0

        return {
            "total_sent": total_sent,
            "total_delivered": effective_delivered,
            "total_opened": opened,
            "total_clicked": clicked,
            "total_bounced": bounced,
            "total_complained": complained,
            "delivery_rate": round(delivery_rate, 2),
            "open_rate": round(open_rate, 2),
            "click_rate": round(click_rate, 2),
            "bounce_rate": round(bounce_rate, 2),
            "complaint_rate": round(complaint_rate, 2)
        }

    async def get_analytics_by_template(
        self,
        date_range: str = "30d",
        workspace_id: Optional[UUID] = None
    ) -> List[Dict[str, Any]]:
        """
        Get email performance by template type

        Args:
            date_range: Date range string
            workspace_id: Optional workspace ID to filter by workspace (multi-tenancy)

        Returns:
            List of template performance dictionaries
        """
        start_date = self._parse_date_range(date_range)
        base_filters = self._build_base_filters(start_date, workspace_id)

        # 1. Query sent and delivered counts grouped by template_type
        logs_query = select(
            EmailLog.template_type,
            func.count(EmailLog.id).label('sent'),
            func.sum(case((or_(EmailLog.status == 'delivered', EmailLog.delivered_at.isnot(None)), 1), else_=0)).label('delivered')
        ).where(
            and_(*base_filters)
        ).group_by(
            EmailLog.template_type
        ).order_by(
            func.count(EmailLog.id).desc()
        )

        logs_result = await self.db.execute(logs_query)
        logs_rows = logs_result.all()

        # 2. Query opened and clicked distinct email counts grouped by template_type
        events_query = select(
            EmailLog.template_type,
            func.count(func.distinct(case((EmailEvent.event_type.in_(['opened', 'email.opened']), EmailLog.id), else_=None))).label('opened'),
            func.count(func.distinct(case((EmailEvent.event_type.in_(['clicked', 'email.clicked']), EmailLog.id), else_=None))).label('clicked')
        ).select_from(EmailEvent).join(
            EmailLog,
            or_(
                EmailEvent.email_log_id == EmailLog.id,
                and_(
                    EmailEvent.provider_message_id.isnot(None),
                    EmailLog.provider_message_id.isnot(None),
                    EmailEvent.provider_message_id == EmailLog.provider_message_id
                ),
                and_(
                    EmailEvent.email_log_id.is_(None),
                    EmailLog.to_email == func.jsonb_extract_path_text(EmailEvent.event_data, 'to', '0')
                )
            )
        ).where(
            and_(
                EmailEvent.received_at >= start_date,
                *([EmailLog.workspace_id == workspace_id] if workspace_id else [])
            )
        ).group_by(
            EmailLog.template_type
        )

        events_result = await self.db.execute(events_query)
        events_map = {row.template_type: {"opened": row.opened or 0, "clicked": row.clicked or 0} for row in events_result.all()}

        # 3. Combine into final template performance list
        template_stats = []
        for row in logs_rows:
            ttype = row.template_type or "unknown"
            sent = row.sent or 0
            ev_data = events_map.get(ttype, {"opened": 0, "clicked": 0})
            opened = ev_data["opened"]
            clicked = ev_data["clicked"]
            delivered = max(row.delivered or 0, opened, clicked)

            template_stats.append({
                "template_type": ttype,
                "sent": sent,
                "delivered": delivered,
                "opened": opened,
                "clicked": clicked,
                "open_rate": round((opened / delivered * 100) if delivered > 0 else 0, 2),
                "click_rate": round((clicked / delivered * 100) if delivered > 0 else 0, 2)
            })

        return template_stats

    async def get_timeline(
        self,
        period: str = "daily",
        date_range: str = "30d",
        workspace_id: Optional[UUID] = None
    ) -> List[Dict[str, Any]]:
        """
        Get email volume over time

        Args:
            period: Aggregation period ("daily", "weekly", "monthly")
            date_range: Date range string
            workspace_id: Optional workspace ID to filter by workspace (multi-tenancy)

        Returns:
            List of time-series data points
        """
        start_date = self._parse_date_range(date_range)
        base_filters = self._build_base_filters(start_date, workspace_id)

        # Map periods to SQL date truncation intervals
        _PERIOD_TO_DATE_TRUNC = {
            "daily": "day",
            "weekly": "week",
            "monthly": "month",
        }

        if period not in _PERIOD_TO_DATE_TRUNC:
            # Fallback to monthly for safety, though route-level validation should prevent this
            interval = "month"
            self.log.warning(f"Unsupported period provided to get_timeline: {period}. Defaulting to monthly.")
        else:
            interval = _PERIOD_TO_DATE_TRUNC[period]

        date_trunc = func.date_trunc(interval, EmailLog.created_at)

        # Pre-aggregate events (see _event_flags_subquery) so the join is 1:1
        # and the per-bucket sent count is not fanned out by event rows.
        event_flags = self._event_flags_subquery(start_date)

        # Query for timeline
        query = select(
            date_trunc.label('date'),
            func.count(EmailLog.id).label('sent'),
            func.coalesce(func.sum(event_flags.c.opened), 0).label('opened'),
            func.coalesce(func.sum(event_flags.c.clicked), 0).label('clicked'),
            func.sum(
                case(
                    (or_(EmailLog.status == 'delivered', EmailLog.delivered_at.isnot(None)), 1),
                    else_=0
                )
            ).label('delivered'),
            func.sum(
                case(
                    (EmailLog.status.in_(('failed', 'bounced')), 1),
                    else_=0
                )
            ).label('failed')
        ).select_from(EmailLog).outerjoin(
            event_flags,
            or_(
                EmailLog.id == event_flags.c.email_log_id,
                EmailLog.provider_message_id == event_flags.c.provider_message_id
            )
        ).where(
            and_(*base_filters)
        ).group_by(
            'date'
        ).order_by(
            'date'
        )

        result = await self.db.execute(query)
        rows = result.all()

        timeline = []
        for row in rows:
            timeline.append({
                "date": row.date.isoformat() if row.date else None,
                "sent": row.sent or 0,
                "delivered": row.delivered or 0,
                "opened": row.opened or 0,
                "clicked": row.clicked or 0,
                "failed": row.failed or 0
            })

        return timeline

    async def get_recent_failures(
        self,
        limit: int = 100,
        workspace_id: Optional[UUID] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent email failures

        Args:
            limit: Maximum number of failures to return
            workspace_id: Optional workspace ID to filter by workspace (multi-tenancy)

        Returns:
            List of failed email records
        """
        filters = [
            or_(
                EmailLog.status == 'failed',
                EmailLog.status == 'bounced'
            )
        ]

        if workspace_id:
            filters.append(EmailLog.workspace_id == workspace_id)

        query = select(
            EmailLog.id,
            EmailLog.to_email,
            EmailLog.template_type,
            EmailLog.status,
            EmailLog.error_message,
            EmailLog.created_at.label('sent_at')
        ).where(
            and_(*filters)
        ).order_by(
            EmailLog.created_at.desc()
        ).limit(limit)

        result = await self.db.execute(query)
        rows = result.all()

        failures = []
        for row in rows:
            failures.append({
                "id": str(row.id),
                "to": row.to_email,
                "template_type": row.template_type or "unknown",
                "status": row.status,
                "error_message": row.error_message or "No error message",
                "sent_at": row.sent_at.isoformat() if row.sent_at else None
            })

        return failures
