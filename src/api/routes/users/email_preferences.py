"""
Email Preferences API Routes

Manage user email notification preferences and unsubscribe functionality.
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.services.email_preferences_service import EmailPreferencesService
from src.utils.route_decorators import db_transaction_handler
from src.api.middleware.exceptions import ResourceNotFoundException
from src.utils.logger import logger


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
@db_transaction_handler("get email preferences", auto_commit=False)
async def get_preferences(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get user's email preferences.

    Returns the current email notification settings for the authenticated user.
    """
    user_id = UUID(current_user["identity"])
    service = EmailPreferencesService(db)
    prefs = await service.get_or_create_preferences(user_id)

    return {"preferences": prefs.to_dict()}


@router.put("/")
@db_transaction_handler("update email preferences", auto_commit=True)
async def update_preferences(
    request: Request,
    preferences_update: UpdatePreferencesRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Update user's email preferences.

    Allows users to control which email notifications they receive.
    Only provided fields will be updated.
    """
    user_id = UUID(current_user["identity"])
    service = EmailPreferencesService(db)

    # Task 080: Use .model_dump() instead of .model_dump()
    updates = preferences_update.model_dump(exclude_none=True)

    if not updates:
        return {"message": "No preferences to update"}

    prefs = await service.update_preferences(user_id, updates)

    return {"preferences": prefs.to_dict()}


@router.post("/unsubscribe")
@db_transaction_handler("unsubscribe from emails", auto_commit=True)
async def unsubscribe(
    request: Request,
    unsubscribe_data: UnsubscribeRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Unsubscribe from emails using token from email link.

    This endpoint does not require authentication - it uses the unique
    unsubscribe token from the email footer link.

    If email_types is empty, unsubscribes from all emails.
    """
    service = EmailPreferencesService(db)
    success_result = await service.unsubscribe(
        unsubscribe_data.token,
        unsubscribe_data.email_types or []
    )

    if not success_result:
        raise ResourceNotFoundException(
            message="Invalid unsubscribe token"
        )

    email_types_str = ", ".join(unsubscribe_data.email_types) if unsubscribe_data.email_types else "all emails"

    return {
        "unsubscribed_from": email_types_str,
        "message": f"Successfully unsubscribed from {email_types_str}"
    }
