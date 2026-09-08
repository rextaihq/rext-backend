from calendar import monthrange
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.models.content_models.content import Content
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services.cms_status_service import CMSStatusService
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
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    await CMSStatusService(db).bulk_sync_workspace(workspace.id)

    last_day = monthrange(year, month)[1]
    month_start = datetime(year, month, 1, tzinfo=timezone.utc)
    month_end = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)

    stmt = (
        select(Content)
        .where(
            Content.workspace_id == workspace.id,
            Content.deleted_at.is_(None),
            Content.status.in_(["published", "scheduled"]),
            or_(
                Content.wordpress_published_at.between(month_start, month_end),
                Content.shopify_published_at.between(month_start, month_end),
            ),
        )
        .order_by(Content.wordpress_published_at, Content.shopify_published_at)
    )

    rows = (await db.execute(stmt)).scalars().all()

    # Group by date — a content item may appear under two dates if on different platforms
    calendar: Dict[str, List[Dict[str, Any]]] = {}

    for c in rows:
        entries = []

        if c.wordpress_published_at and month_start <= c.wordpress_published_at <= month_end:
            entries.append({
                "id": str(c.id),
                "title": c.title,
                "slug": c.slug,
                "status": c.status,
                "platform": "wordpress",
                "url": c.wordpress_url,
                "date": c.wordpress_published_at.isoformat(),
                "day_key": c.wordpress_published_at.date().isoformat(),
            })

        if c.shopify_published_at and month_start <= c.shopify_published_at <= month_end:
            entries.append({
                "id": str(c.id),
                "title": c.title,
                "slug": c.slug,
                "status": c.status,
                "platform": "shopify",
                "url": c.shopify_article_url,
                "date": c.shopify_published_at.isoformat(),
                "day_key": c.shopify_published_at.date().isoformat(),
            })

        for entry in entries:
            day_key = entry.pop("day_key")
            calendar.setdefault(day_key, []).append(entry)

    return success(
        data={
            "year": year,
            "month": month,
            "total_items": sum(len(v) for v in calendar.values()),
            "calendar": calendar,
        },
        request=request,
        message="Content calendar retrieved",
    )
