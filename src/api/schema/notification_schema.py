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
    email_enabled: Optional[bool] = Field(None, description="Enable/disable all email notifications")
    in_app_enabled: Optional[bool] = Field(None, description="Enable/disable all in-app notifications")
    digest_enabled: Optional[bool] = Field(None, description="Enable/disable notification digests")
    digest_frequency: Optional[Literal["daily", "weekly", "monthly"]] = Field(None, description="Digest frequency")
    categories: Optional[NotificationCategories] = Field(None, description="Category-specific preferences")

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
