"""
Admin Customer Management API endpoints.

This module provides administrative operations for customer management
including listing, filtering, viewing details, performing actions, and adding notes.

All endpoints require admin permissions.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.models.subscription_models.subscriptions import UserSubscription
from src.api.models.user_models.user import User
from src.api.models.workspace_models.workspace import Workspace
from src.api.security.dependencies import get_current_user, require_permissions
from src.services.audit_log_service import AuditLogService
from src.utils.route_decorators import db_transaction_handler


router = APIRouter(prefix="/customers", tags=["Admin - Customers"])


# ============================================================================
# SCHEMAS
# ============================================================================


class CustomerNoteRequest(BaseModel):
    """Request schema for adding customer note."""
    note: str = Field(..., min_length=1, max_length=2000)
    category: str = Field(..., pattern="^(billing|support|technical|other)$")


class CustomerActionRequest(BaseModel):
    """Request schema for customer actions."""
    action: str = Field(
        ...,
        pattern="^(deactivate|activate|reset_usage|extend_trial|cancel_subscription)$"
    )
    reason: str = Field(..., min_length=1, max_length=500)
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.get("", response_model=dict)
@db_transaction_handler("list customers", auto_commit=False)
async def list_customers(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search by name or email"),
    status: Optional[str] = Query(None, description="Filter by subscription status"),
    plan_id: Optional[str] = Query(None, description="Filter by plan ID"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_permissions(["user:read"]))
):
    """
    List all customers with filtering and pagination (admin only).

    Query Parameters:
    - page: Page number (default 1)
    - per_page: Items per page (default 50, max 100)
    - search: Search by name or email
    - status: Filter by subscription status (active, trial, cancelled, free)
    - plan_id: Filter by plan ID
    - sort_by: Sort field (default created_at)
    - sort_order: asc or desc (default desc)

    Returns:
    - List of customers with subscription and workspace info
    - Pagination metadata
    """
    # Build query
    query = (
        select(
            User.id,
            User.email,
            User.display_name,
            User.created_at,
            User.is_active,
            User.last_login_at,
            UserSubscription.id.label("subscription_id"),
            func.count(Workspace.id).label("workspaces_count")
        )
        .outerjoin(UserSubscription, and_(
            UserSubscription.user_id == User.id,
            UserSubscription.status.in_(["active", "trial"])
        ))
        .outerjoin(Workspace, Workspace.created_by == User.id)
        .group_by(
            User.id,
            User.email,
            User.display_name,
            User.created_at,
            User.is_active,
            User.last_login_at,
            UserSubscription.id
        )
    )

    # Apply search filter
    if search:
        search_filter = or_(
            User.email.ilike(f"%{search}%"),
            User.display_name.ilike(f"%{search}%")
        )
        query = query.where(search_filter)

    # Apply status filter
    if status:
        if status == "free":
            query = query.where(UserSubscription.id.is_(None))
        else:
            query = query.where(UserSubscription.status == status)

    # Apply plan filter
    if plan_id:
        query = query.where(UserSubscription.plan_id == UUID(plan_id))

    # Count total before pagination
    count_query = select(func.count()).select_from(
        query.subquery()
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply sorting
    sort_column = getattr(User, sort_by, User.created_at)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # Apply pagination
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    # Execute query
    result = await db.execute(query)
    rows = result.all()

    # Format response
    customers = []
    for row in rows:
        # Get subscription details if exists
        subscription_info = None
        if row.subscription_id:
            sub_query = (
                select(UserSubscription, func.coalesce(
                    func.sum(UserSubscription.plan_id), 0
                ).label("mrr"))
                .where(UserSubscription.id == row.subscription_id)
            )
            sub_result = await db.execute(sub_query)
            sub_row = sub_result.first()

            if sub_row and sub_row[0]:
                sub = sub_row[0]
                from src.api.models.subscription_models.plans import SubscriptionPlan
                plan_query = select(SubscriptionPlan).where(SubscriptionPlan.id == sub.plan_id)
                plan_result = await db.execute(plan_query)
                plan = plan_result.scalar_one_or_none()

                mrr = 0
                if plan:
                    if sub.billing_period == "monthly":
                        mrr = float(plan.price_monthly)
                    else:
                        mrr = float(plan.price_yearly) / 12

                subscription_info = {
                    "plan_name": plan.display_name if plan else "Unknown",
                    "status": sub.status.value,
                    "mrr": round(mrr, 2)
                }

        customers.append({
            "user_id": str(row.id),
            "name": row.display_name or row.email,
            "email": row.email,
            "subscription": subscription_info,
            "workspaces_count": row.workspaces_count,
            "is_active": row.is_active,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "last_active": row.last_login_at.isoformat() if row.last_login_at else None
        })

    # Calculate pagination
    total_pages = (total + per_page - 1) // per_page

    return {
        "data": customers,
        "pagination": {
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages
        },
        "message": "Customers retrieved successfully"
    }


@router.get("/{user_id}", response_model=dict)
@db_transaction_handler("get customer detail", auto_commit=False)
async def get_customer_detail(
    request: Request,
    user_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_permissions(["user:read"]))
):
    """
    Get detailed customer information (admin only).

    Path Parameters:
    - user_id: User ID

    Returns:
    - User details
    - Subscription details
    - Workspaces list
    - Usage metrics
    - Activity summary
    - Recent audit events
    - Customer notes
    """
    # Get user
    user_query = select(User).where(User.id == UUID(user_id))
    user_result = await db.execute(user_query)
    user = user_result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get subscription
    subscription = None
    sub_query = (
        select(UserSubscription)
        .where(
            UserSubscription.user_id == user.id,
            UserSubscription.status.in_(["active", "trial"])
        )
    )
    sub_result = await db.execute(sub_query)
    sub = sub_result.scalar_one_or_none()

    if sub:
        from src.api.models.subscription_models.plans import SubscriptionPlan
        plan_query = select(SubscriptionPlan).where(SubscriptionPlan.id == sub.plan_id)
        plan_result = await db.execute(plan_query)
        plan = plan_result.scalar_one_or_none()

        subscription = {
            "id": str(sub.id),
            "plan": {
                "id": str(plan.id) if plan else None,
                "name": plan.display_name if plan else "Unknown",
                "price_monthly": float(plan.price_monthly) if plan else 0,
                "price_yearly": float(plan.price_yearly) if plan else 0
            },
            "status": sub.status.value,
            "billing_period": sub.billing_period.value if sub.billing_period else None,
            "start_date": sub.start_date.isoformat() if sub.start_date else None,
            "end_date": sub.end_date.isoformat() if sub.end_date else None,
            "trial_end_date": sub.trial_end_date.isoformat() if sub.trial_end_date else None,
            "cancelled_at": sub.cancelled_at.isoformat() if sub.cancelled_at else None
        }

    # Get workspaces
    workspaces_query = (
        select(Workspace.id, Workspace.name, Workspace.created_at)
        .where(Workspace.created_by == user.id)
        .order_by(Workspace.created_at.desc())
    )
    workspaces_result = await db.execute(workspaces_query)
    workspaces_rows = workspaces_result.all()

    workspaces = [
        {
            "id": str(ws.id),
            "name": ws.name,
            "created_at": ws.created_at.isoformat() if ws.created_at else None
        }
        for ws in workspaces_rows
    ]

    # Get usage metrics (if has subscription)
    usage = None
    if sub:
        from src.services.usage_tracking_service import UsageTrackingService
        usage_service = UsageTrackingService(db)
        usage = await usage_service.get_usage_metrics(str(user.id))

    # Activity summary
    from src.api.models.content_models.content import Content
    from src.api.models.knowledge_models.knowledge_base import KnowledgeBase

    content_count_query = select(func.count(Content.id)).join(
        Workspace, Content.workspace_id == Workspace.id
    ).where(Workspace.created_by == user.id)
    content_count_result = await db.execute(content_count_query)
    content_count = content_count_result.scalar() or 0

    kb_count_query = select(func.count(KnowledgeBase.id)).join(
        Workspace, KnowledgeBase.workspace_id == Workspace.id
    ).where(Workspace.created_by == user.id)
    kb_count_result = await db.execute(kb_count_query)
    kb_count = kb_count_result.scalar() or 0

    activity_summary = {
        "last_login": user.last_login_at.isoformat() if user.last_login_at else None,
        "total_content_created": content_count,
        "total_knowledge_items": kb_count,
        "workspaces_count": len(workspaces)
    }

    # Get recent audit events
    audit_service = AuditLogService(db)
    audit_events = await audit_service.get_recent_user_events(str(user.id), limit=10)

    # Get customer notes
    from src.api.models.admin_models.customer_note import CustomerNote
    notes_query = (
        select(CustomerNote, User.email.label("admin_email"))
        .join(User, CustomerNote.admin_id == User.id)
        .where(CustomerNote.user_id == user.id)
        .order_by(CustomerNote.created_at.desc())
        .limit(20)
    )
    notes_result = await db.execute(notes_query)
    notes_rows = notes_result.all()

    notes = [
        {
            "id": str(note.id),
            "note": note.note,
            "category": note.category,
            "admin_email": admin_email,
            "created_at": note.created_at.isoformat() if note.created_at else None
        }
        for note, admin_email in notes_rows
    ]

    return {
        "data": {
            "user": {
                "id": str(user.id),
                "email": user.email,
                "display_name": user.display_name,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None
            },
            "subscription": subscription,
            "workspaces": workspaces,
            "usage": usage,
            "activity_summary": activity_summary,
            "audit_events": audit_events,
            "notes": notes
        },
        "message": "Customer details retrieved successfully"
    }


@router.post("/{user_id}/actions", response_model=dict)
@db_transaction_handler("perform customer action", auto_commit=True)
async def perform_customer_action(
    request: Request,
    user_id: str,
    action_request: CustomerActionRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_permissions(["user:manage"]))
):
    """
    Perform admin actions on customer account (admin only).

    Path Parameters:
    - user_id: User ID

    Request Body:
    - action: deactivate, activate, reset_usage, extend_trial, cancel_subscription
    - reason: Reason for the action
    - metadata: Additional metadata

    Returns:
    - Action result
    - Updated user/subscription state
    """
    admin_user_id = current_user.get("identity")

    # Get user
    user_query = select(User).where(User.id == UUID(user_id))
    user_result = await db.execute(user_query)
    user = user_result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Perform action
    result = {}
    audit_details = {
        "reason": action_request.reason,
        "metadata": action_request.metadata
    }

    if action_request.action == "deactivate":
        if not user.is_active:
            raise HTTPException(status_code=400, detail="User is already deactivated")

        audit_details["previous_status"] = "active"
        user.is_active = False
        result = {"status": "deactivated"}

    elif action_request.action == "activate":
        if user.is_active:
            raise HTTPException(status_code=400, detail="User is already active")

        audit_details["previous_status"] = "inactive"
        user.is_active = True
        result = {"status": "activated"}

    elif action_request.action == "reset_usage":
        # Get subscription
        sub_query = (
            select(UserSubscription)
            .where(
                UserSubscription.user_id == user.id,
                UserSubscription.status.in_(["active", "trial"])
            )
        )
        sub_result = await db.execute(sub_query)
        sub = sub_result.scalar_one_or_none()

        if not sub:
            raise HTTPException(status_code=404, detail="No active subscription found")

        audit_details["previous_api_calls"] = sub.current_api_calls
        sub.current_api_calls = 0
        sub.usage_reset_date = datetime.utcnow()
        result = {"status": "usage_reset", "new_api_calls": 0}

    elif action_request.action == "extend_trial":
        # Get subscription
        sub_query = (
            select(UserSubscription)
            .where(
                UserSubscription.user_id == user.id,
                UserSubscription.status == "trial"
            )
        )
        sub_result = await db.execute(sub_query)
        sub = sub_result.scalar_one_or_none()

        if not sub:
            raise HTTPException(status_code=404, detail="No trial subscription found")

        from datetime import timedelta
        extension_days = action_request.metadata.get("days", 7)
        old_trial_end = sub.trial_end_date
        sub.trial_end_date = sub.trial_end_date + timedelta(days=extension_days)

        audit_details["old_trial_end"] = old_trial_end.isoformat() if old_trial_end else None
        audit_details["new_trial_end"] = sub.trial_end_date.isoformat()
        audit_details["extension_days"] = extension_days

        result = {
            "status": "trial_extended",
            "new_trial_end": sub.trial_end_date.isoformat()
        }

    elif action_request.action == "cancel_subscription":
        # Get subscription
        sub_query = (
            select(UserSubscription)
            .where(
                UserSubscription.user_id == user.id,
                UserSubscription.status.in_(["active", "trial"])
            )
        )
        sub_result = await db.execute(sub_query)
        sub = sub_result.scalar_one_or_none()

        if not sub:
            raise HTTPException(status_code=404, detail="No active subscription found")

        audit_details["previous_status"] = sub.status.value
        sub.status = "cancelled"
        sub.cancelled_at = datetime.utcnow()

        result = {"status": "subscription_cancelled"}

    # Log to audit
    audit_service = AuditLogService(db)
    await audit_service.log_admin_action(
        admin_id=admin_user_id,
        action=action_request.action,
        entity_type="user",
        entity_id=user_id,
        details=audit_details,
        db=db
    )

    await db.commit()

    return {
        "data": result,
        "message": f"Action '{action_request.action}' performed successfully"
    }


@router.post("/{user_id}/notes", response_model=dict)
@db_transaction_handler("add customer note", auto_commit=True)
async def add_customer_note(
    request: Request,
    user_id: str,
    note_request: CustomerNoteRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_permissions(["user:read"]))
):
    """
    Add internal note to customer account (admin only).

    Path Parameters:
    - user_id: User ID

    Request Body:
    - note: Note text (max 2000 characters)
    - category: billing, support, technical, or other

    Returns:
    - Created note
    """
    admin_user_id = current_user.get("identity")

    # Verify user exists
    user_query = select(User).where(User.id == UUID(user_id))
    user_result = await db.execute(user_query)
    user = user_result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Create note
    from src.api.models.admin_models.customer_note import CustomerNote

    note = CustomerNote(
        user_id=UUID(user_id),
        admin_id=UUID(admin_user_id),
        note=note_request.note,
        category=note_request.category
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)

    # Log to audit
    audit_service = AuditLogService(db)
    await audit_service.log_admin_action(
        admin_id=admin_user_id,
        action="add_customer_note",
        entity_type="user",
        entity_id=user_id,
        details={"category": note_request.category},
        db=db
    )

    return {
        "data": {
            "id": str(note.id),
            "note": note.note,
            "category": note.category,
            "created_at": note.created_at.isoformat() if note.created_at else None
        },
        "message": "Note added successfully"
    }
