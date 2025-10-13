"""
Email Preferences API Routes

Manage user email notification preferences and unsubscribe functionality.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import List, Optional

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.services.email_preferences_service import EmailPreferencesService
from src.utils.response_utils import success
from src.utils.logger import logger
from uuid import UUID


router = APIRouter(
    prefix="/user/email-preferences",
    tags=["Email Preferences"]
)


class UpdatePreferencesRequest(BaseModel):
    """Request model for updating email preferences."""
    # Workspace notifications
    workspace_invitation: Optional[bool] = None
    invitation_accepted: Optional[bool] = None
    role_changed: Optional[bool] = None
    member_removed: Optional[bool] = None

    # Content generation
    content_generation_started: Optional[bool] = None
    content_generation_completed: Optional[bool] = None
    content_generation_failed: Optional[bool] = None
    content_published: Optional[bool] = None

    # Billing
    payment_succeeded: Optional[bool] = None
    payment_failed: Optional[bool] = None
    subscription_cancelled: Optional[bool] = None
    subscription_expiring_soon: Optional[bool] = None
    trial_ending_soon: Optional[bool] = None
    usage_limit_warning: Optional[bool] = None
    usage_limit_exceeded: Optional[bool] = None

    # Knowledge base
    kb_processing_completed: Optional[bool] = None
    kb_processing_failed: Optional[bool] = None

    # Digest
    digest_enabled: Optional[bool] = None
    digest_frequency: Optional[str] = None

    # Marketing
    marketing: Optional[bool] = None


class UnsubscribeRequest(BaseModel):
    """Request model for unsubscribing via token."""
    token: str
    email_types: Optional[List[str]] = []


@router.get("/")
async def get_preferences(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get user's email preferences.

    Returns the current email notification settings for the authenticated user.
    """
    try:
        user_id = UUID(current_user["identity"])
        service = EmailPreferencesService(db)
        prefs = await service.get_or_create_preferences(user_id, db)

        return success(
            data=prefs.to_dict(),
            message="Email preferences retrieved successfully"
        )
    except Exception as e:
        logger.error(f"Failed to get email preferences: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve email preferences")


@router.put("/")
async def update_preferences(
    request: UpdatePreferencesRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Update user's email preferences.

    Allows users to control which email notifications they receive.
    Only provided fields will be updated.
    """
    try:
        user_id = UUID(current_user["identity"])
        service = EmailPreferencesService(db)

        # Build update dict from non-None fields
        updates = {k: v for k, v in request.dict().items() if v is not None}

        if not updates:
            return success(
                data={},
                message="No preferences to update"
            )

        prefs = await service.update_preferences(user_id, updates, db)
        await db.commit()

        return success(
            data=prefs.to_dict(),
            message="Email preferences updated successfully"
        )
    except Exception as e:
        logger.error(f"Failed to update email preferences: {str(e)}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update email preferences")


@router.post("/unsubscribe")
async def unsubscribe(
    request: UnsubscribeRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Unsubscribe from emails using token from email link.

    This endpoint does not require authentication - it uses the unique
    unsubscribe token from the email footer link.

    If email_types is empty, unsubscribes from all emails.
    """
    try:
        service = EmailPreferencesService(db)
        success_result = await service.unsubscribe(
            request.token,
            request.email_types or [],
            db
        )

        if not success_result:
            raise HTTPException(status_code=404, detail="Invalid unsubscribe token")

        email_types_str = ", ".join(request.email_types) if request.email_types else "all emails"

        return success(
            data={"unsubscribed_from": email_types_str},
            message=f"Successfully unsubscribed from {email_types_str}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to unsubscribe: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process unsubscribe request")
