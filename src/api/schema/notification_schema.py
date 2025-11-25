from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict


class NotificationCategories(BaseModel):
    """Category-specific notification preferences."""
    mentions: Optional[bool] = None
    workspace_invites: Optional[bool] = None
    content_updates: Optional[bool] = None
    comments: Optional[bool] = None
    team_activity: Optional[bool] = None
    security_alerts: Optional[bool] = None
    billing_updates: Optional[bool] = None
    product_updates: Optional[bool] = None


class NotificationPreferencesResponse(BaseModel):
    """Response schema for notification preferences matching API spec."""
    email_enabled: bool
    in_app_enabled: bool
    digest_enabled: bool
    digest_frequency: Literal["daily", "weekly", "monthly"]
    categories: Dict[str, bool]

    class Config:
        json_schema_extra = {
            "example": {
                "email_enabled": True,
                "in_app_enabled": True,
                "digest_enabled": True,
                "digest_frequency": "daily",
                "categories": {
                    "mentions": True,
                    "workspace_invites": True,
                    "content_updates": True,
                    "comments": True,
                    "team_activity": True,
                    "security_alerts": True,
                    "billing_updates": True,
                    "product_updates": False
                }
            }
        }


class UpdateNotificationPreferencesRequest(BaseModel):
    """Request schema for updating notification preferences.

    Supports partial updates - all fields are optional.
    When a category is set, it applies to both email and in-app channels.
    """
    # GLOBAL
    email_notifications: Optional[bool] = None
    in_app_notifications: Optional[bool] = None

    # WORKSPACE
    ws_invite_received: Optional[bool] = None
    ws_invite_accepted: Optional[bool] = None
    ws_role_changed: Optional[bool] = None
    ws_member_removed: Optional[bool] = None

    # CONTENT GENERATION
    gen_started: Optional[bool] = None
    gen_completed: Optional[bool] = None
    gen_failed: Optional[bool] = None
    gen_published: Optional[bool] = None

    # BILLING
    billing_payment_success: Optional[bool] = None
    billing_payment_failed: Optional[bool] = None
    billing_subscription_cancelled: Optional[bool] = None
    billing_subscription_expiring: Optional[bool] = None
    billing_trial_ending: Optional[bool] = None
    billing_usage_limit_warning: Optional[bool] = None
    billing_usage_limit_exceeded: Optional[bool] = None

    # KNOWLEDGE BASE
    kb_processing_completed: Optional[bool] = None
    kb_processing_failed: Optional[bool] = None

    # DIGEST
    digest_enabled: Optional[bool] = None
    digest_frequency: Optional[Literal["daily", "weekly", "monthly"]] = None

    # MARKETING
    marketing_updates: Optional[bool] = None

    class Config:
        from_attributes = True