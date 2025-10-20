"""Onboarding routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from langgraph_sdk import Auth

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user, get_current_user_optional
from src.api.schema.onboarding_schemas import (
    OnboardingReset,
    OnboardingResponse,
    OnboardingStepUpdate,
)
from src.services.onboarding_service import OnboardingService
from src.utils.logger import logger

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("", response_model=OnboardingResponse, status_code=status.HTTP_200_OK)
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    try:
        user_id = current_user.get("identity")
        onboarding = await OnboardingService.get_or_create_onboarding(db, user_id)
        return onboarding
    except ValueError as e:
        # User doesn't exist - likely invalid/stale token
        logger.error(f"[Onboarding] User not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or has been deleted",
        )
    except Exception as e:
        logger.error(f"[Onboarding] Failed to get status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve onboarding status",
        )


@router.post("/update", response_model=OnboardingResponse, status_code=status.HTTP_200_OK)
async def update_onboarding_step(
    step_update: OnboardingStepUpdate,
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
    try:
        user_id = UUID(current_user["identity"])

        if step_update.action == "complete":
            onboarding = await OnboardingService.complete_step(db, user_id, step_update.step)
        elif step_update.action == "skip":
            onboarding = await OnboardingService.skip_step(db, user_id, step_update.step)
        elif step_update.action == "set_current":
            onboarding = await OnboardingService.set_current_step(db, user_id, step_update.step)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid action: {step_update.action}. Must be 'complete', 'skip', or 'set_current'",
            )

        return onboarding
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"[Onboarding] Failed to update step: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update onboarding step",
        )


@router.post("/complete", response_model=OnboardingResponse, status_code=status.HTTP_200_OK)
async def complete_onboarding(
    db: Annotated[AsyncSession, Depends(get_async_db)],
    current_user: Annotated[Auth.types.MinimalUserDict, Depends(get_current_user)],
):
    """
    Mark onboarding as fully completed.

    This endpoint is called when the user completes the final step
    or explicitly dismisses the onboarding flow.
    """
    try:
        user_id = UUID(current_user["identity"])
        onboarding = await OnboardingService.complete_onboarding(db, user_id)
        logger.info(f"[Onboarding] User {user_id} completed onboarding")
        return onboarding
    except Exception as e:
        logger.error(f"[Onboarding] Failed to complete: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete onboarding",
        )


@router.post("/reset", response_model=OnboardingResponse, status_code=status.HTTP_200_OK)
async def reset_onboarding(
    reset_data: OnboardingReset,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    current_user: Annotated[Auth.types.MinimalUserDict, Depends(get_current_user)],
):
    """
    Reset onboarding to start from beginning.

    This allows users to replay the onboarding flow if they want
    to review the initial setup steps.
    """
    try:
        if not reset_data.confirm:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Confirmation required to reset onboarding",
            )

        user_id = UUID(current_user["identity"])
        onboarding = await OnboardingService.reset_onboarding(db, user_id)
        logger.info(f"[Onboarding] User {user_id} reset onboarding")
        return onboarding
    except Exception as e:
        logger.error(f"[Onboarding] Failed to reset: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset onboarding",
        )


@router.get("/should-show", status_code=status.HTTP_200_OK)
async def should_show_onboarding(
    db: Annotated[AsyncSession, Depends(get_async_db)],
    current_user: Annotated[Auth.types.MinimalUserDict | None, Depends(get_current_user_optional)],
):
    """
    Check if onboarding should be shown to the current user.

    Returns a boolean indicating whether the onboarding flow
    should be displayed. Returns false if not authenticated.
    """
    # Return false if not authenticated (graceful degradation)
    if not current_user:
        return {"should_show": False}

    try:
        user_id = current_user.get("identity")
        should_show = await OnboardingService.should_show_onboarding(db, user_id)
        return {"should_show": should_show}
    except Exception as e:
        logger.error(f"[Onboarding] Failed to check should show: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check onboarding status",
        )
