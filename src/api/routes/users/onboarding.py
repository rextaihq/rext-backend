"""Onboarding routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import RextAuthenticationException, RextValidationException
from src.api.schema.onboarding_schemas import (
    OnboardingMarketingData,
    OnboardingReset,
    OnboardingResponse,
    OnboardingStepUpdate,
)
from src.api.schema.response.onboarding_responses import (
    ShouldShowOnboardingResponse,
    UserOnboardingResponse,
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user, get_current_user_optional
from src.services.onboarding_service import OnboardingService
from src.utils.logger import logger
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler

# No permission gates in this module: every route manages the caller's own
# onboarding state, so authentication (get_current_user) is sufficient. The
# former user.update gates were redundant — every account held them via the
# platform-floor 'user' role, which has been removed.
router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get(
    "", response_model=SuccessResponse[UserOnboardingResponse], status_code=status.HTTP_200_OK
)
@db_transaction_handler("get onboarding status", auto_commit=False)
async def get_onboarding_status(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    current_user: Annotated[dict | None, Depends(get_current_user_optional)],
):
    """
    Get current user's onboarding status.

    Returns the user's onboarding progress including current step,
    completed steps, and skipped steps.
    Requires authentication.
    """
    if not current_user:
        raise RextAuthenticationException(message="Authentication required")

    user_id = UUID(current_user["identity"])
    onboarding = await OnboardingService.get_or_create_onboarding(db, user_id)
    return success(
        data=OnboardingResponse.model_validate(onboarding).model_dump(),
        request=request,
        message="Onboarding status retrieved successfully",
    )


@router.post(
    "/update",
    response_model=SuccessResponse[UserOnboardingResponse],
    status_code=status.HTTP_200_OK,
)
@db_transaction_handler("update onboarding step", auto_commit=True)
async def update_onboarding_step(
    step_update: OnboardingStepUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
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
            validation_errors={"action": "Invalid action value"},
        )

    return success(
        data=OnboardingResponse.model_validate(onboarding).model_dump(),
        request=request,
        message="Onboarding step updated successfully",
    )


@router.post(
    "/complete",
    response_model=SuccessResponse[UserOnboardingResponse],
    status_code=status.HTTP_200_OK,
)
@db_transaction_handler("complete onboarding", auto_commit=True)
async def complete_onboarding(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """
    Mark onboarding as fully completed.

    This endpoint is called when the user completes the final step
    or explicitly dismisses the onboarding flow.
    """
    user_id = UUID(current_user["identity"])
    onboarding = await OnboardingService.complete_onboarding(db, user_id)
    logger.info(f"[Onboarding] User {user_id} completed onboarding")
    return success(
        data=OnboardingResponse.model_validate(onboarding).model_dump(),
        request=request,
        message="Onboarding completed successfully",
    )


@router.post(
    "/reset", response_model=SuccessResponse[UserOnboardingResponse], status_code=status.HTTP_200_OK
)
@db_transaction_handler("reset onboarding", auto_commit=True)
async def reset_onboarding(
    reset_data: OnboardingReset,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """
    Reset onboarding to start from beginning.

    This allows users to replay the onboarding flow if they want
    to review the initial setup steps.
    """
    if not reset_data.confirm:
        raise RextValidationException(
            message="Confirmation required to reset onboarding",
            validation_errors={"confirm": "Must be true"},
        )

    user_id = UUID(current_user["identity"])
    onboarding = await OnboardingService.reset_onboarding(db, user_id)
    logger.info(f"[Onboarding] User {user_id} reset onboarding")
    return success(
        data=OnboardingResponse.model_validate(onboarding).model_dump(),
        request=request,
        message="Onboarding reset successfully",
    )


@router.get(
    "/should-show",
    response_model=SuccessResponse[ShouldShowOnboardingResponse],
    status_code=status.HTTP_200_OK,
)
@db_transaction_handler("check should show onboarding", auto_commit=False)
async def should_show_onboarding(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    current_user: Annotated[dict | None, Depends(get_current_user_optional)],
):
    """
    Check if onboarding should be shown to the current user.

    Returns a boolean indicating whether the onboarding flow
    should be displayed. Returns false if not authenticated.
    Only shows onboarding to organic signups (not invited users or admins).
    """
    # Return false if not authenticated (graceful degradation)
    if not current_user:
        return success(
            data={"should_show": False}, request=request, message="Onboarding show status retrieved"
        )

    user_id = UUID(current_user["identity"])
    should_show = await OnboardingService.should_show_onboarding(db, user_id)
    return success(
        data={"should_show": should_show},
        request=request,
        message="Onboarding show status retrieved",
    )


@router.post(
    "/marketing",
    response_model=SuccessResponse[UserOnboardingResponse],
    status_code=status.HTTP_200_OK,
)
@db_transaction_handler("update marketing data", auto_commit=True)
async def update_marketing_data(
    marketing_data: OnboardingMarketingData,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
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
    return success(
        data=OnboardingResponse.model_validate(onboarding).model_dump(),
        request=request,
        message="Marketing data updated successfully",
    )
