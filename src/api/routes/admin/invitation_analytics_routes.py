"""
Invitation Analytics Routes

Admin endpoints for tracking and analyzing invitation metrics.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import and_, case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import ResourceNotFoundException
from src.api.models.user_models.invitations import UserInvitations
from src.api.models.user_models.roles import Role
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.security.dependencies import get_current_user
from src.utils.auth_utils import verify_current_user
from src.utils.logger import logger
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions

router = APIRouter(prefix="/invitations", tags=["admin-analytics"])


@router.get("/analytics", summary="Get invitation analytics")
@db_transaction_handler("get invitation analytics", auto_commit=False)
@require_permissions("audit.admin", workspace_scoped=False)
async def get_invitation_analytics(
    request: Request,
    workspace_id: Optional[str] = Query(
        None, description="Filter by workspace ID (optional)"
    ),
    days: int = Query(30, description="Number of days to analyze", ge=1, le=365),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    Get comprehensive invitation analytics.

    Returns metrics including:
    - Total invitations sent
    - Acceptance/decline/expiry rates
    - Average time to acceptance
    - Most active inviters
    - Popular roles
    - Trend data over time

    Args:
        workspace_id: Optional workspace filter
        days: Number of days to analyze (default 30)
        db: Database session
        user: Current user

    Returns:
        Comprehensive invitation analytics
    """
    user_uuid = UUID(str(user.get("identity")))
    await verify_current_user(db, str(user_uuid))

    # Calculate date range
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    # Build base query
    base_query = select(UserInvitations).where(
        UserInvitations.created_at >= start_date
    )

    if workspace_id:
        base_query = base_query.where(
            UserInvitations.workspace_id == UUID(workspace_id)
        )

    # Get total invitations
    total_query = select(func.count(UserInvitations.id)).select_from(
        base_query.subquery()
    )
    total_result = await db.execute(total_query)
    total_invitations = total_result.scalar() or 0

    # Get status counts
    status_query = (
        select(
            UserInvitations.status, func.count(UserInvitations.id).label("count")
        )
        .where(UserInvitations.created_at >= start_date)
        .group_by(UserInvitations.status)
    )

    if workspace_id:
        status_query = status_query.where(
            UserInvitations.workspace_id == UUID(workspace_id)
        )

    status_result = await db.execute(status_query)
    status_counts = {row.status: row.count for row in status_result}

    # Calculate rates
    accepted = status_counts.get("accepted", 0)
    declined = status_counts.get("declined", 0) + status_counts.get("revoked", 0)
    expired = status_counts.get("expired", 0)
    pending = status_counts.get("pending", 0)

    acceptance_rate = (
        round((accepted / total_invitations) * 100, 2) if total_invitations > 0 else 0
    )
    decline_rate = (
        round((declined / total_invitations) * 100, 2) if total_invitations > 0 else 0
    )
    expiry_rate = (
        round((expired / total_invitations) * 100, 2) if total_invitations > 0 else 0
    )

    # Calculate average time to acceptance (for accepted invitations)
    avg_time_query = select(
        func.avg(
            func.extract(
                "epoch", UserInvitations.accepted_at - UserInvitations.created_at
            )
        )
    ).where(
        and_(
            UserInvitations.status == "accepted",
            UserInvitations.accepted_at.isnot(None),
            UserInvitations.created_at >= start_date,
        )
    )

    if workspace_id:
        avg_time_query = avg_time_query.where(
            UserInvitations.workspace_id == UUID(workspace_id)
        )

    avg_time_result = await db.execute(avg_time_query)
    avg_seconds = avg_time_result.scalar()
    avg_hours = round(avg_seconds / 3600, 2) if avg_seconds else 0

    # Get most active inviters (top 10)
    inviters_query = (
        select(
            UserInvitations.invited_by_user_id,
            func.count(UserInvitations.id).label("invitation_count"),
        )
        .where(UserInvitations.created_at >= start_date)
        .group_by(UserInvitations.invited_by_user_id)
        .order_by(func.count(UserInvitations.id).desc())
        .limit(10)
    )

    if workspace_id:
        inviters_query = inviters_query.where(
            UserInvitations.workspace_id == UUID(workspace_id)
        )

    inviters_result = await db.execute(inviters_query)
    top_inviters_data = inviters_result.all()

    # Load inviter details
    top_inviters = []
    for inviter_row in top_inviters_data:
        if inviter_row.invited_by_user_id:
            inviter_user = await db.get(Users, inviter_row.invited_by_user_id)
            if inviter_user:
                top_inviters.append(
                    {
                        "user_id": str(inviter_row.invited_by_user_id),
                        "name": inviter_user.display_name or inviter_user.username,
                        "email": inviter_user.email,
                        "invitation_count": inviter_row.invitation_count,
                    }
                )

    # Get popular roles
    roles_query = (
        select(UserInvitations.role_id, func.count(UserInvitations.id).label("count"))
        .where(UserInvitations.created_at >= start_date)
        .group_by(UserInvitations.role_id)
        .order_by(func.count(UserInvitations.id).desc())
        .limit(10)
    )

    if workspace_id:
        roles_query = roles_query.where(
            UserInvitations.workspace_id == UUID(workspace_id)
        )

    roles_result = await db.execute(roles_query)
    popular_roles_data = roles_result.all()

    # Load role details
    popular_roles = []
    for role_row in popular_roles_data:
        role = await db.get(Role, role_row.role_id)
        if role:
            popular_roles.append(
                {
                    "role_id": str(role_row.role_id),
                    "name": role.display_name or role.name,
                    "invitation_count": role_row.count,
                }
            )

    # Get daily trend (invitations per day)
    # Group by date for trend analysis
    daily_trend_query = (
        select(
            func.date_trunc("day", UserInvitations.created_at).label("date"),
            func.count(UserInvitations.id).label("total"),
            func.count(
                case((UserInvitations.status == "accepted", UserInvitations.id))
            ).label("accepted"),
            func.count(
                case((UserInvitations.status == "pending", UserInvitations.id))
            ).label("pending"),
        )
        .where(UserInvitations.created_at >= start_date)
        .group_by(func.date_trunc("day", UserInvitations.created_at))
        .order_by(func.date_trunc("day", UserInvitations.created_at))
    )

    if workspace_id:
        daily_trend_query = daily_trend_query.where(
            UserInvitations.workspace_id == UUID(workspace_id)
        )

    daily_trend_result = await db.execute(daily_trend_query)
    daily_trend = [
        {
            "date": row.date.strftime("%Y-%m-%d") if row.date else None,
            "total": row.total,
            "accepted": row.accepted,
            "pending": row.pending,
        }
        for row in daily_trend_result
    ]

    # Get workspace breakdown (if not filtered by workspace)
    workspace_stats = []
    if not workspace_id:
        workspace_query = (
            select(
                UserInvitations.workspace_id,
                func.count(UserInvitations.id).label("total"),
                func.count(
                    case((UserInvitations.status == "accepted", UserInvitations.id))
                ).label("accepted"),
            )
            .where(UserInvitations.created_at >= start_date)
            .group_by(UserInvitations.workspace_id)
            .order_by(func.count(UserInvitations.id).desc())
            .limit(10)
        )

        workspace_result = await db.execute(workspace_query)
        workspace_data = workspace_result.all()

        for ws_row in workspace_data:
            workspace = await db.get(WorkspaceModel, ws_row.workspace_id)
            if workspace:
                workspace_stats.append(
                    {
                        "workspace_id": str(ws_row.workspace_id),
                        "name": workspace.name,
                        "total_invitations": ws_row.total,
                        "accepted_invitations": ws_row.accepted,
                        "acceptance_rate": round(
                            (ws_row.accepted / ws_row.total) * 100, 2
                        )
                        if ws_row.total > 0
                        else 0,
                    }
                )

    logger.info(
        f"Invitation analytics generated: {total_invitations} invitations in {days} days",
        extra={
            "user_id": str(user_uuid),
            "workspace_id": workspace_id,
            "days": days,
            "total_invitations": total_invitations,
        },
    )

    return success(
        data={
            "summary": {
                "total_invitations": total_invitations,
                "accepted": accepted,
                "declined": declined,
                "expired": expired,
                "pending": pending,
                "acceptance_rate": acceptance_rate,
                "decline_rate": decline_rate,
                "expiry_rate": expiry_rate,
                "avg_time_to_acceptance_hours": avg_hours,
            },
            "top_inviters": top_inviters,
            "popular_roles": popular_roles,
            "daily_trend": daily_trend,
            "workspace_stats": workspace_stats,
            "period": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat(), "days": days},
        },
        request=request,
        message="Invitation analytics retrieved successfully",
    )
