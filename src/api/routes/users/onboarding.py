"""Onboarding routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from langgraph_sdk import Auth

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user, get_current_user_optional
from src.api.schema.onboarding_schemas import (
    OnboardingReset,
    OnboardingResponse,
    OnboardingStepUpdate,
    OnboardingMarketingData,
)
from src.api.middleware.exceptions import RextValidationException, RextAuthenticationException
from src.services.onboarding_service import OnboardingService
from src.utils.logger import logger
from src.utils.route_decorators import require_permissions, db_transaction_handler

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("", response_model=OnboardingResponse, status_code=status.HTTP_200_OK)
@db_transaction_handler("get onboarding status", auto_commit=False)
async def get_onboarding_status(
    db: Annotated[AsyncSession, Depends(get_async_db)],
    current_user: Annotated[Auth.types.MinimalUserDict | None, Depends(get_current_user_optional)],
):
    """
    Get current user's onboarding status.

    Returns the user's onboarding progress including current step,
    completed steps, and skipped steps.
    Requires authentication.
    """
    if not current_user:
        raise RextAuthenticationException(
            message="Authentication required"
        )

    user_id = current_user.get("identity")
    onboarding = await OnboardingService.get_or_create_onboarding(db, user_id)
    return onboarding


@router.post("/update", response_model=OnboardingResponse, status_code=status.HTTP_200_OK)
@require_permissions("user.update", workspace_scoped=False)
@db_transaction_handler("update onboarding step", auto_commit=True)
async def update_onboarding_step(
    step_update: OnboardingStepUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    current_user: Annotated[Auth.types.MinimalUserDict, Depends(get_current_user)],
):
    """
    Update onboarding step.

    Actions:
    - complete: Mark step as completed
    - skip: Mark step as skipped (not allowed for required steps)
    - set_current: Set current step for navigation
    """
    user_id = UUID(current_user["identity"])

    if step_update.action == "complete":
        onboarding = await OnboardingService.complete_step(db, user_id, step_update.step)
    elif step_update.action == "skip":
        onboarding = await OnboardingService.skip_step(db, user_id, step_update.step)
    elif step_update.action == "set_current":
        onboarding = await OnboardingService.set_current_step(db, user_id, step_update.step)
    else:
        raise RextValidationException(
            message=f"Invalid action: {step_update.action}. Must be 'complete', 'skip', or 'set_current'",
            validation_errors={"action": "Invalid action value"}
        )

    return onboarding


@router.post("/complete", response_model=OnboardingResponse, status_code=status.HTTP_200_OK)
@require_permissions("user.update", workspace_scoped=False)
@db_transaction_handler("complete onboarding", auto_commit=True)
async def complete_onboarding(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    current_user: Annotated[Auth.types.MinimalUserDict, Depends(get_current_user)],
):
    """
    Mark onboarding as fully completed.

    This endpoint is called when the user completes the final step
    or explicitly dismisses the onboarding flow.
    """
    user_id = UUID(current_user["identity"])
    onboarding = await OnboardingService.complete_onboarding(db, user_id)
    logger.info(f"[Onboarding] User {user_id} completed onboarding")
    return onboarding


@router.post("/reset", response_model=OnboardingResponse, status_code=status.HTTP_200_OK)
@require_permissions("user.update", workspace_scoped=False)
@db_transaction_handler("reset onboarding", auto_commit=True)
async def reset_onboarding(
    reset_data: OnboardingReset,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    current_user: Annotated[Auth.types.MinimalUserDict, Depends(get_current_user)],
):
    """
    Reset onboarding to start from beginning.

    This allows users to replay the onboarding flow if they want
    to review the initial setup steps.
    """
    if not reset_data.confirm:
        raise RextValidationException(
            message="Confirmation required to reset onboarding",
            validation_errors={"confirm": "Must be true"}
        )

    user_id = UUID(current_user["identity"])
    onboarding = await OnboardingService.reset_onboarding(db, user_id)
    logger.info(f"[Onboarding] User {user_id} reset onboarding")
    return onboarding


@router.get("/should-show", status_code=status.HTTP_200_OK)
@db_transaction_handler("check should show onboarding", auto_commit=False)
async def should_show_onboarding(
    db: Annotated[AsyncSession, Depends(get_async_db)],
    current_user: Annotated[Auth.types.MinimalUserDict | None, Depends(get_current_user_optional)],
):
    """
    Check if onboarding should be shown to the current user.

    Returns a boolean indicating whether the onboarding flow
    should be displayed. Returns false if not authenticated.
    Only shows onboarding to organic signups (not invited users or admins).
    """
    # Return false if not authenticated (graceful degradation)
    if not current_user:
        return {"should_show": False}

    user_id = current_user.get("identity")
    should_show = await OnboardingService.should_show_onboarding(db, user_id)
    return {"should_show": should_show}


@router.post("/marketing", response_model=OnboardingResponse, status_code=status.HTTP_200_OK)
@require_permissions("user.update", workspace_scoped=False)
@db_transaction_handler("update marketing data", auto_commit=True)
async def update_marketing_data(
    marketing_data: OnboardingMarketingData,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    current_user: Annotated[Auth.types.MinimalUserDict, Depends(get_current_user)],
):
    """
    Update marketing data collected during onboarding.

    Saves user's industry, role, goal, and acquisition channel.
    """
    user_id = UUID(current_user["identity"])
    onboarding = await OnboardingService.update_marketing_data(
        db,
        user_id,
        user_industry=marketing_data.user_industry,
        user_role=marketing_data.user_role,
        user_goal=marketing_data.user_goal,
        heard_from=marketing_data.heard_from,
    )
    logger.info(f"[Onboarding] Marketing data updated for user {user_id}")
    return onboarding


