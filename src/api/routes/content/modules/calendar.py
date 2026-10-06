from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.models.content_models.content import Content
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services.cms_status_service import CMSStatusService
from src.services.user_service import UserService
from src.utils.datetime_utils import account_zone
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.workspace_utils import resolve_and_verify_workspace

router = APIRouter()


@router.get("/calendar", response_model=SuccessResponse[Dict[str, Any]])
@require_permissions("content.read", workspace_scoped=True)
@db_transaction_handler("content calendar", auto_commit=True)
async def content_calendar(
    request: Request,
    workspace_id: str,
    year: int = Query(..., ge=2000, le=2100, description="Calendar year"),
    month: int = Query(..., ge=1, le=12, description="Calendar month (1-12)"),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    Return published and scheduled content grouped by date for a given month.

    Each day key maps to a list of content items with their publishing details.
    Covers both WordPress (wordpress_published_at) and Shopify (shopify_published_at) dates.
    The month and its days are the caller's account timezone's, the one scheduling
    reads a picked time in, so an item sits on the day it was scheduled for.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    await CMSStatusService(db).bulk_sync_workspace(workspace.id)

    user_row = await UserService(db).get_user_by_id(UUID(user_id))
    user_timezone = user_row.timezone or "UTC"
    tz = account_zone(user_timezone)
    month_start = datetime(year, month, 1, tzinfo=tz)
    month_end = datetime(year + month // 12, month % 12 + 1, 1, tzinfo=tz)

    def in_month(when: Optional[datetime]) -> bool:
        return when is not None and month_start <= when < month_end

    stmt = (
        select(Content)
        .where(
            Content.workspace_id == workspace.id,
            Content.deleted_at.is_(None),
            Content.status.in_(["published", "scheduled"]),
            or_(
                (Content.wordpress_published_at >= month_start)
                & (Content.wordpress_published_at < month_end),
                (Content.shopify_published_at >= month_start)
                & (Content.shopify_published_at < month_end),
            ),
        )
        .order_by(Content.wordpress_published_at, Content.shopify_published_at)
    )

    rows = (await db.execute(stmt)).scalars().all()

    # Group by date — a content item may appear under two dates if on different platforms
    calendar: Dict[str, List[Dict[str, Any]]] = {}

    for c in rows:
        entries = []

        if in_month(c.wordpress_published_at):
            entries.append(
                {
                    "id": str(c.id),
                    "title": c.title,
                    "slug": c.slug,
                    "status": c.status,
                    "platform": "wordpress",
                    "url": c.wordpress_url,
                    "date": c.wordpress_published_at.isoformat(),
                    "day_key": c.wordpress_published_at.astimezone(tz).date().isoformat(),
                }
            )

        if in_month(c.shopify_published_at):
            entries.append(
                {
                    "id": str(c.id),
                    "title": c.title,
                    "slug": c.slug,
                    "status": c.status,
                    "platform": "shopify",
                    "url": c.shopify_article_url,
                    "date": c.shopify_published_at.isoformat(),
                    "day_key": c.shopify_published_at.astimezone(tz).date().isoformat(),
                }
            )

        for entry in entries:
            day_key = entry.pop("day_key")
            calendar.setdefault(day_key, []).append(entry)

    return success(
        data={
            "year": year,
            "month": month,
            "timezone": user_timezone,
            "total_items": sum(len(v) for v in calendar.values()),
            "calendar": calendar,
        },
        request=request,
        message="Content calendar retrieved",
    )
