"""
Trial management API endpoints.

This module provides endpoints for trial management operations including:
- Trial extension (admin)
- Trial eligibility checking
- Trial conversion analytics
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.utils.route_decorators import require_permissions
from src.services.trial_service import TrialService
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.response.trial_responses import (
    TrialEligibilityResponse,
    TrialExtensionResponse,
    TrialAnalyticsResponse,
    ExpiringTrialsResponse
)
from src.utils.logger import logger


router = APIRouter(
    prefix="/trials",
    tags=["trials"]
)


# ============================================================================
# REQUEST/RESPONSE SCHEMAS
# ============================================================================

class TrialExtensionRequest(BaseModel):
    """Schema for trial extension request."""
    extension_days: int = Field(..., ge=1, le=90, description="Days to extend trial (1-90)")
    reason: Optional[str] = Field(None, max_length=500, description="Reason for extension")

    class Config:
        json_schema_extra = {
            "example": {
                "extension_days": 7,
                "reason": "Customer requested extension to evaluate advanced features"
            }
        }


# ============================================================================
# TRIAL ELIGIBILITY ENDPOINT
# ============================================================================

@router.get("/eligibility", response_model=SuccessResponse[TrialEligibilityResponse], status_code=status.HTTP_200_OK)
@db_transaction_handler("check trial eligibility", auto_commit=False)
async def check_trial_eligibility_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Check if the current user is eligible for a trial.

    Returns:
    - eligible: Whether user can start a trial
    - has_active_trial: Whether user has an active trial
    - has_previous_trial: Whether user has had a trial before
    - previous_trials_count: Number of previous trials
    - reason: Reason for ineligibility (if not eligible)

    Raises:
    - 401: Unauthorized
    """
    user_id = current_user.get("identity")
    service = TrialService(db)

    eligibility = await service.check_trial_eligibility(user_id)

    return success(
        data=eligibility,
        request=request,
        message="Trial eligibility checked successfully"
    )


# ============================================================================
# ADMIN TRIAL EXTENSION ENDPOINT
# ============================================================================

@router.post("/extend/{subscription_id}", response_model=SuccessResponse[TrialExtensionResponse], status_code=status.HTTP_200_OK)
@db_transaction_handler("extend trial")
@require_permissions("subscription.manage", workspace_scoped=False)
async def extend_trial_endpoint(
    request: Request,
    subscription_id: str,
    extension_data: TrialExtensionRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Extend a trial period (admin only).

    This endpoint allows administrators to extend a user's trial period.

    Path Parameters:
    - subscription_id: UUID of the subscription

    Body:
    - extension_days: Number of days to extend (1-90)
    - reason: Optional reason for extension

    Returns:
    - Updated subscription with extended trial_end_date
    - Extension history in metadata

    Raises:
    - 404: Subscription not found
    - 400: Subscription is not a trial or extension invalid
    - 403: Not authorized (admin only)
    """
    admin_user_id = current_user.get("identity")
    service = TrialService(db)

    # Extend trial
    subscription = await service.extend_trial(
        subscription_id=UUID(subscription_id),
        extension_days=extension_data.extension_days,
        admin_user_id=admin_user_id,
        reason=extension_data.reason
    )

    return success(
        data={
            "id": str(subscription.id),
            "user_id": str(subscription.user_id),
            "status": subscription.status.value,
            "trial_end_date": subscription.trial_end_date.isoformat() if subscription.trial_end_date else None,
            "extension_days": extension_data.extension_days,
            "extended_by": str(admin_user_id),
            "extension_reason": extension_data.reason,
            "trial_extensions": subscription.subscription_metadata.get("trial_extensions", [])
        },
        request=request,
        message=f"Trial extended by {extension_data.extension_days} days successfully"
    )


# ============================================================================
# TRIAL ANALYTICS ENDPOINTS
# ============================================================================

@router.get("/analytics/conversions", response_model=SuccessResponse[TrialAnalyticsResponse], status_code=status.HTTP_200_OK)
@db_transaction_handler("get trial conversion analytics", auto_commit=False)
@require_permissions("audit.admin", workspace_scoped=False)
async def get_trial_conversion_analytics_endpoint(
    request: Request,
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get trial conversion statistics (admin only).

    Query Parameters:
    - start_date: Optional start date filter (ISO format)
    - end_date: Optional end date filter (ISO format)

    Returns:
    - total_conversions: Total number of trial conversions
    - average_trial_duration: Average trial length in days
    - average_conversion_time: Average days into trial when conversion happened
    - total_revenue: Total revenue from trial conversions
    - conversion_by_period: Breakdown by billing period (monthly/yearly)
    - date_range: The date range used for filtering

    Raises:
    - 403: Not authorized (admin only)
    - 400: Invalid date format
    """
    service = TrialService(db)

    # Parse dates if provided
    start_dt = None
    end_dt = None

    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid start_date format. Use ISO format (YYYY-MM-DD)"
            )

    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid end_date format. Use ISO format (YYYY-MM-DD)"
            )

    # Get statistics
    stats = await service.get_trial_conversion_stats(
        start_date=start_dt,
        end_date=end_dt
    )

    return success(
        data=stats,
        request=request,
        message="Trial conversion analytics retrieved successfully"
    )


@router.get("/expiring", response_model=SuccessResponse[ExpiringTrialsResponse], status_code=status.HTTP_200_OK)
@db_transaction_handler("get expiring trials", auto_commit=False)
@require_permissions("audit.admin", workspace_scoped=False)
async def get_expiring_trials_endpoint(
    request: Request,
    days: int = Query(3, ge=0, le=30, description="Days until expiration"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get trials expiring in N days (admin only).

    Query Parameters:
    - days: Days until expiration (0-30, default: 3)

    Returns:
    - List of subscriptions with trials expiring in N days

    Raises:
    - 403: Not authorized (admin only)
    """
    service = TrialService(db)

    trials = await service.get_expiring_trials(days_until_expiry=days)

    # Format response
    trials_data = []
    for trial in trials:
        trials_data.append({
            "id": str(trial.id),
            "user_id": str(trial.user_id),
            "plan_id": str(trial.plan_id),
            "status": trial.status.value,
            "trial_end_date": trial.trial_end_date.isoformat() if trial.trial_end_date else None,
            "created_at": trial.created_at.isoformat()
        })

    return success(
        data={
            "trials": trials_data,
            "total": len(trials_data),
            "days_until_expiry": days
        },
        request=request,
        message=f"Retrieved {len(trials_data)} trials expiring in {days} days"
    )
