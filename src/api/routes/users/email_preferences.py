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
from src.api.models.user_models.notification_preferences import NotificationPreferences
from src.utils.response_utils import success
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
    try:
        user_id = UUID(current_user["identity"])
        
        # Get or create preferences
        result = await db.execute(
            select(NotificationPreferences).where(
                NotificationPreferences.user_id == user_id
            )
        )
        prefs = result.scalar_one_or_none()

        if not prefs:
            # Create default preferences
            prefs = NotificationPreferences(
                user_id=user_id,
                unsubscribe_token=secrets.token_urlsafe(32)
            )
            db.add(prefs)
            await db.flush()
            await db.refresh(prefs)
            logger.info(f"Created default notification preferences for user {user_id}")

        return success(
            data=prefs.to_dict(),
            message="Email preferences retrieved successfully"
        )
    except Exception as e:
        logger.error(f"Failed to get email preferences: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve email preferences")


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
    try:
        user_id = UUID(current_user["identity"])

        # Build update dict mapping request fields to NotificationPreferences columns
        field_mapping = {
            "workspace_invitation": "ws_invite_received",
            "invitation_accepted": "ws_invite_accepted",
            "role_changed": "ws_role_changed",
            "member_removed": "ws_member_removed",
            "content_generation_started": "gen_started",
            "content_generation_completed": "gen_completed",
            "content_generation_failed": "gen_failed",
            "content_published": "gen_published",
            "payment_succeeded": "billing_payment_success",
            "payment_failed": "billing_payment_failed",
            "subscription_cancelled": "billing_subscription_cancelled",
            "subscription_expiring_soon": "billing_subscription_expiring",
            "trial_ending_soon": "billing_trial_ending",
            "usage_limit_warning": "billing_usage_limit_warning",
            "usage_limit_exceeded": "billing_usage_limit_exceeded",
            "kb_processing_completed": "kb_processing_completed",
            "kb_processing_failed": "kb_processing_failed",
            "digest_enabled": "digest_enabled",
            "digest_frequency": "digest_frequency",
            "marketing": "marketing_updates",
        }

        # Build update dict from non-None fields, applying the mapping
        updates = {}
        for request_field, value in request.dict().items():
            if value is not None:
                mapped_field = field_mapping.get(request_field, request_field)
                updates[mapped_field] = value

    if not updates:
        return {"message": "No preferences to update"}

        # Get or create preferences
        result = await db.execute(
            select(NotificationPreferences).where(
                NotificationPreferences.user_id == user_id
            )
        )
        prefs = result.scalar_one_or_none()

        if not prefs:
            prefs = NotificationPreferences(
                user_id=user_id,
                unsubscribe_token=secrets.token_urlsafe(32)
            )
            db.add(prefs)
            await db.flush()

        # Apply updates
        for field, value in updates.items():
            if hasattr(prefs, field):
                setattr(prefs, field, value)

        await db.flush()
        await db.refresh(prefs)

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
    try:
        # Find user by unsubscribe token
        result = await db.execute(
            select(NotificationPreferences).where(
                NotificationPreferences.unsubscribe_token == request.token
            )
        )
        prefs = result.scalar_one_or_none()

v        if not prefs:
            raise HTTPException(status_code=404, detail="Invalid unsubscribe token")

        # If no specific email types provided, disable all email notifications
        if not request.email_types:
            prefs.email_notifications = False
        else:
            # Map email types to NotificationPreferences columns
            type_mapping = {
                "workspace_invitation": "ws_invite_received",
                "invitation_accepted": "ws_invite_accepted",
                "role_changed": "ws_role_changed",
                "member_removed": "ws_member_removed",
                "content_generation_started": "gen_started",
                "content_generation_completed": "gen_completed",
                "content_generation_failed": "gen_failed",
                "content_published": "gen_published",
                "payment_succeeded": "billing_payment_success",
                "payment_failed": "billing_payment_failed",
                "subscription_cancelled": "billing_subscription_cancelled",
                "subscription_expiring_soon": "billing_subscription_expiring",
                "trial_ending_soon": "billing_trial_ending",
                "usage_limit_warning": "billing_usage_limit_warning",
                "usage_limit_exceeded": "billing_usage_limit_exceeded",
                "kb_processing_completed": "kb_processing_completed",
                "kb_processing_failed": "kb_processing_failed",
                "marketing": "marketing_updates",
            }

            # Disable specified email types
            for email_type in request.email_types:
                if email_type in type_mapping:
                    field_name = type_mapping[email_type]
                    if hasattr(prefs, field_name):
                        setattr(prefs, field_name, False)

        await db.flush()
        await db.refresh(prefs)

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
