"""
Invitation Analytics Routes

Admin endpoints for tracking and analyzing invitation metrics.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import RextAuthorizationException
from src.api.models.user_models.invitations import UserInvitations
from src.api.models.user_models.roles import Role
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.schema.invitation_analytics_schema import InvitationAnalyticsResponseSchema
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_active_user, get_current_user
from src.utils.logger import logger
from src.utils.rbac_utils import check_all_permissions
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions

router = APIRouter(prefix="/invitations", tags=["admin-analytics"])


@router.get(
    "/analytics",
    summary="Get invitation analytics",
    response_model=SuccessResponse[InvitationAnalyticsResponseSchema],
)
@db_transaction_handler("get invitation analytics", auto_commit=False)
@require_permissions("audit.read", workspace_scoped=False)
async def get_invitation_analytics(
    request: Request,
    workspace_id: Optional[str] = Query(None, description="Filter by workspace ID (optional)"),
    days: int = Query(30, description="Number of days to analyze", ge=1, le=365),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
    current_db_user: Users = Depends(get_current_active_user),
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
        current_db_user: Current authenticated user row

    Returns:
        Comprehensive invitation analytics
    """
    user_uuid = current_db_user.id

    # Add explicit workspace authorization guard if workspace_id is provided
    if workspace_id:
        workspace_uuid = UUID(workspace_id)
        has_workspace_audit_access = await check_all_permissions(
            db,
            user_uuid,
            ["audit.read"],
            workspace_uuid,
        )
        if not has_workspace_audit_access:
            raise RextAuthorizationException(
                message="Missing required permission: audit.read",
                context={
                    "workspace_id": str(workspace_uuid),
                    "required_permissions": ["audit.read"],
                },
            )

    # Calculate date range
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    # Build base query
    base_query = select(UserInvitations).where(UserInvitations.created_at >= start_date)

    if workspace_id:
        base_query = base_query.where(UserInvitations.workspace_id == UUID(workspace_id))

    # Get total invitations
    total_query = select(func.count(UserInvitations.id)).select_from(base_query.subquery())
    total_result = await db.execute(total_query)
    total_invitations = total_result.scalar() or 0

    # Get status counts
    status_query = (
        select(UserInvitations.status, func.count(UserInvitations.id).label("count"))
        .where(UserInvitations.created_at >= start_date)
        .group_by(UserInvitations.status)
    )

    if workspace_id:
        status_query = status_query.where(UserInvitations.workspace_id == UUID(workspace_id))

    status_result = await db.execute(status_query)
    status_counts = {row.status: row.count for row in status_result}

    # Calculate rates
    accepted = status_counts.get("accepted", 0)
    declined = status_counts.get("declined", 0) + status_counts.get("revoked", 0)
    expired = status_counts.get("expired", 0)
    pending = status_counts.get("pending", 0)

    acceptance_rate = round((accepted / total_invitations) * 100, 2) if total_invitations > 0 else 0
    decline_rate = round((declined / total_invitations) * 100, 2) if total_invitations > 0 else 0
    expiry_rate = round((expired / total_invitations) * 100, 2) if total_invitations > 0 else 0

    # Calculate average time to acceptance (for accepted invitations)
    avg_time_query = select(
        func.avg(func.extract("epoch", UserInvitations.accepted_at - UserInvitations.created_at))
    ).where(
        and_(
            UserInvitations.status == "accepted",
            UserInvitations.accepted_at.isnot(None),
            UserInvitations.created_at >= start_date,
        )
    )

    if workspace_id:
        avg_time_query = avg_time_query.where(UserInvitations.workspace_id == UUID(workspace_id))

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
        inviters_query = inviters_query.where(UserInvitations.workspace_id == UUID(workspace_id))

    inviters_result = await db.execute(inviters_query)
    top_inviters_data = inviters_result.all()

    # Batch load all inviter users in one query
    inviter_user_ids = [
        row.invited_by_user_id for row in top_inviters_data if row.invited_by_user_id
    ]
    inviter_users_map = {}
    if inviter_user_ids:
        users_result = await db.execute(select(Users).where(Users.id.in_(inviter_user_ids)))
        inviter_users_map = {u.id: u for u in users_result.scalars().all()}

    top_inviters = []
    for inviter_row in top_inviters_data:
        if inviter_row.invited_by_user_id:
            inviter_user = inviter_users_map.get(inviter_row.invited_by_user_id)
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
        roles_query = roles_query.where(UserInvitations.workspace_id == UUID(workspace_id))

    roles_result = await db.execute(roles_query)
    popular_roles_data = roles_result.all()

    # Batch load all roles in one query
    role_ids = [row.role_id for row in popular_roles_data if row.role_id]
    roles_map = {}
    if role_ids:
        roles_query_batch = select(Role).where(Role.id.in_(role_ids))
        roles_batch_result = await db.execute(roles_query_batch)
        roles_map = {r.id: r for r in roles_batch_result.scalars().all()}

    popular_roles = []
    for role_row in popular_roles_data:
        role = roles_map.get(role_row.role_id)
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
    date_expr = func.date_trunc("day", UserInvitations.created_at)
    daily_trend_query = (
        select(
            date_expr.label("date"),
            func.count(UserInvitations.id).label("total"),
            func.count(case((UserInvitations.status == "accepted", UserInvitations.id))).label(
                "accepted"
            ),
            func.count(case((UserInvitations.status == "pending", UserInvitations.id))).label(
                "pending"
            ),
        )
        .where(UserInvitations.created_at >= start_date)
        .group_by(date_expr)
        .order_by(date_expr)
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
                func.count(case((UserInvitations.status == "accepted", UserInvitations.id))).label(
                    "accepted"
                ),
            )
            .where(UserInvitations.created_at >= start_date)
            .group_by(UserInvitations.workspace_id)
            .order_by(func.count(UserInvitations.id).desc())
            .limit(10)
        )

        workspace_result = await db.execute(workspace_query)
        workspace_data = workspace_result.all()

        # Batch load all workspaces in one query
        ws_ids = [row.workspace_id for row in workspace_data if row.workspace_id]
        workspaces_map = {}
        if ws_ids:
            ws_batch_result = await db.execute(
                select(WorkspaceModel).where(WorkspaceModel.id.in_(ws_ids))
            )
            workspaces_map = {w.id: w for w in ws_batch_result.scalars().all()}

        for ws_row in workspace_data:
            workspace = workspaces_map.get(ws_row.workspace_id)
            if workspace:
                workspace_stats.append(
                    {
                        "workspace_id": str(ws_row.workspace_id),
                        "name": workspace.name,
                        "total_invitations": ws_row.total,
                        "accepted_invitations": ws_row.accepted,
                        "acceptance_rate": round((ws_row.accepted / ws_row.total) * 100, 2)
                        if ws_row.total > 0
                        else 0,
                    }
                )

    logger.info(
        f"Invitation analytics generated: {total_invitations} invitations in {days} days",
        extra={
            "user_id": str(current_db_user.id),
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
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": days,
            },
        },
        request=request,
        message="Invitation analytics retrieved successfully",
    )
