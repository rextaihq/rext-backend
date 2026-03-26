from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
import secrets

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.services.email_preferences_service import EmailPreferencesService
from src.services.notification_preferences_service import NotificationPreferencesService
from src.utils.route_decorators import db_transaction_handler
from src.api.middleware.exceptions import ResourceNotFoundException
from src.api.models.user_models.notification_preferences import NotificationPreferences
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.response.email_preference_responses import (
    EmailPreferencesResponse,
    UnsubscribeResponse
)
from src.utils.response_utils import success
from src.utils.logger import logger
from src.utils.audit_helper import create_audit_log

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

@router.get("/", response_model=SuccessResponse[EmailPreferencesResponse])
@db_transaction_handler("get email preferences", auto_commit=False)
async def get_preferences(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get user's email preferences.
    """
    user_id = UUID(current_user["identity"])
    
    # Get or create preferences using service
    pref_service = NotificationPreferencesService(db)
    prefs = await pref_service.get_or_create(user_id)

    return success(
        data=prefs.to_dict(),
        request=request,
        message="Email preferences retrieved successfully"
    )

@router.put("/", response_model=SuccessResponse[EmailPreferencesResponse])
@db_transaction_handler("update email preferences", auto_commit=True)
async def update_preferences(
    request: Request,
    preferences_update: UpdatePreferencesRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Update user's email preferences.
    """
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
        "subscription_cancelled": "billing_subscription_canceled",
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

    # Use model_dump(exclude_unset=True) instead of .dict() as per Task 080
    update_data = preferences_update.model_dump(exclude_unset=True)
    
    if not update_data:
        return success(data={}, request=request, message="No preferences to update")

    # Get or create preferences using service
    pref_service = NotificationPreferencesService(db)
    prefs = await pref_service.get_or_create(user_id)

    # Track changes for audit log
    old_values = {}
    new_values = {}

    # Apply updates
    for field, value in update_data.items():
        mapped_field = field_mapping.get(field, field)
        if hasattr(prefs, mapped_field):
            current_value = getattr(prefs, mapped_field)
            if current_value != value:
                old_values[mapped_field] = current_value
                new_values[mapped_field] = value
                setattr(prefs, mapped_field, value)

    await db.flush()

    # Create audit log if values changed
    if old_values:
        await create_audit_log(
            db=db,
            user_id=user_id,
            action="email_preferences.update",
            resource_type="notification_preferences",
            resource_id=str(prefs.id),
            old_values=old_values,
            new_values=new_values,
            request=request,
            metadata={
                "fields_changed": list(new_values.keys()),
                "total_changes": len(new_values),
                "source": "email_preferences_endpoint",
            },
        )

    return success(
        data=prefs.to_dict(),
        request=request,
        message="Email preferences updated successfully"
    )

@router.post("/unsubscribe", response_model=SuccessResponse[UnsubscribeResponse])
@db_transaction_handler("unsubscribe from emails", auto_commit=True)
async def unsubscribe(
    request: Request,
    unsubscribe_data: UnsubscribeRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Unsubscribe from emails using token from email link.
    """
    # Find user by unsubscribe token
    result = await db.execute(
        select(NotificationPreferences).where(
            NotificationPreferences.unsubscribe_token == unsubscribe_data.token
        )
    )
    prefs = result.scalar_one_or_none()

    if not prefs:
        raise HTTPException(status_code=404, detail="Invalid unsubscribe token")

    # Track changes for audit log
    old_values = {}
    new_values = {}

    # If no specific email types provided, disable all email notifications
    if not unsubscribe_data.email_types:
        if prefs.email_notifications is not False:
            old_values["email_notifications"] = prefs.email_notifications
            new_values["email_notifications"] = False
            prefs.email_notifications = False
    else:
        # Map email types to NotificationPreferences preference keys
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

        _COLUMN_FIELDS = {"marketing_updates"}

        # Disable specified email types
        for email_type in unsubscribe_data.email_types:
            if email_type in type_mapping:
                field_name = type_mapping[email_type]
                if hasattr(prefs, field_name):
                    current_value = getattr(prefs, field_name)
                    if current_value is not False:
                        old_values[field_name] = current_value
                        new_values[field_name] = False
                        setattr(prefs, field_name, False)

    await db.flush()

    # Create audit log if values changed
    if old_values:
        await create_audit_log(
            db=db,
            user_id=prefs.user_id,
            action="email_preferences.unsubscribe",
            resource_type="notification_preferences",
            resource_id=str(prefs.id),
            old_values=old_values,
            new_values=new_values,
            request=request,
            metadata={
                "fields_changed": list(new_values.keys()),
                "total_changes": len(new_values),
                "is_unsubscribe": True,
                "token_used": unsubscribe_data.token[:8] + "...", # Mask token
            },
        )

    email_types_str = ", ".join(unsubscribe_data.email_types) if unsubscribe_data.email_types else "all emails"

    return success(
        data={"unsubscribed_from": email_types_str},
        request=request,
        message=f"Successfully unsubscribed from {email_types_str}"
    )
