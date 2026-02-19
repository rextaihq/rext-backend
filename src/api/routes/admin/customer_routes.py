"""
Admin Customer Management API endpoints.

This module provides administrative operations for customer management
including listing, filtering, viewing details, performing actions, and adding notes.

All endpoints require admin permissions.
"""

from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.exceptions import RextValidationException

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.middleware.permissions import is_admin
from src.services.customer_admin_service import CustomerAdminService
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

    @model_validator(mode="after")
    def validate_action_metadata(self) -> "CustomerActionRequest":
        """Validate metadata based on action."""
        if self.action == "cancel_subscription":
            # Ensure cancel_immediately is bool if provided, default to True
            cancel_imm = self.metadata.get("cancel_immediately")
            if cancel_imm is not None and not isinstance(cancel_imm, bool):
                raise RextValidationException(
                    message="cancel_immediately must be a boolean",
                    field_errors={"metadata.cancel_immediately": ["Must be a boolean"]}
                )
        return self


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
    _: bool = Depends(is_admin)
):
    """
    List all customers with filtering and pagination.

    **Security: Requires admin or super_admin role**

    This endpoint provides access to sensitive customer billing and subscription data.
    Only platform administrators should have access.

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

    Raises:
        HTTPException: 401 if not authenticated, 403 if not admin
    """
    # Use service
    service = CustomerAdminService(db)
    result = await service.list_customers(
        page=page,
        per_page=per_page,
        search=search,
        status=status,
        plan_id=UUID(plan_id) if plan_id else None,
        sort_by=sort_by,
        sort_order=sort_order
    )

    return {
        "data": result["customers"],
        "pagination": result["pagination"],
        "message": "Customers retrieved successfully"
    }


@router.get("/{user_id}", response_model=dict)
@db_transaction_handler("get customer detail", auto_commit=False)
async def get_customer_detail(
    request: Request,
    user_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(is_admin)
):
    """
    Get detailed customer information.

    **Security: Requires admin or super_admin role**

    This endpoint exposes comprehensive customer data including billing information,
    subscription details, usage metrics, and audit logs. Access is restricted to
    platform administrators only.

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

    Raises:
        HTTPException: 401 if not authenticated, 403 if not admin
    """
    # Use service
    service = CustomerAdminService(db)
    customer_data = await service.get_customer_detail(UUID(user_id))

    return {
        "data": customer_data,
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
    _: bool = Depends(is_admin)
):
    """
    Perform admin actions on customer account.

    **Security: Requires admin or super_admin role**

    This endpoint allows critical administrative actions on customer accounts
    including deactivation, subscription cancellation, and trial extensions.
    Access is strictly limited to platform administrators.

    Path Parameters:
    - user_id: User ID

    Request Body:
    - action: deactivate, activate, reset_usage, extend_trial, cancel_subscription
    - reason: Reason for the action (required for audit trail)
    - metadata: Additional metadata
        - cancel_immediately (bool, optional): For cancel_subscription, default True.

    Returns:
    - Action result with status and state details
    - Updated user/subscription state

    Raises:
        HTTPException: 401 if not authenticated, 403 if not admin
    """
    admin_user_id = current_user.get("identity")

    # Use service
    service = CustomerAdminService(db)
    result = await service.perform_customer_action(
        user_id=UUID(user_id),
        action=action_request.action,
        reason=action_request.reason,
        metadata=action_request.metadata,
        admin_user_id=admin_user_id
    )

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
    _: bool = Depends(is_admin)
):
    """
    Add internal note to customer account.

    **Security: Requires admin or super_admin role**

    Customer notes are internal administrative records and should only be
    accessible to platform administrators.

    Path Parameters:
    - user_id: User ID

    Request Body:
    - note: Note text (max 2000 characters)
    - category: billing, support, technical, or other

    Returns:
    - Created note

    Raises:
        HTTPException: 401 if not authenticated, 403 if not admin
    """
    admin_user_id = current_user.get("identity")

    # Use service
    service = CustomerAdminService(db)
    note_data = await service.add_customer_note(
        user_id=UUID(user_id),
        admin_user_id=UUID(admin_user_id),
        note=note_request.note,
        category=note_request.category
    )

    return {
        "data": note_data,
        "message": "Note added successfully"
    }
