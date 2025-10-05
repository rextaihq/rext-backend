from pydantic import BaseModel, Field
from typing import Literal


class NotificationPreferencesResponse(BaseModel):
    """Response schema for notification preferences."""
    emailNotifications: bool
    emailDigestFrequency: Literal["instant", "daily", "weekly", "never"]
    emailWorkspaceInvites: bool
    emailComments: bool
    emailMentions: bool
    emailUpdates: bool
    inAppNotifications: bool
    inAppWorkspaceInvites: bool
    inAppComments: bool
    inAppMentions: bool
    inAppUpdates: bool

    class Config:
        json_schema_extra = {
            "example": {
                "emailNotifications": True,
                "emailDigestFrequency": "daily",
                "emailWorkspaceInvites": True,
                "emailComments": True,
                "emailMentions": True,
                "emailUpdates": False,
                "inAppNotifications": True,
                "inAppWorkspaceInvites": True,
                "inAppComments": True,
                "inAppMentions": True,
                "inAppUpdates": False,
            }
        }


class UpdateNotificationPreferencesRequest(BaseModel):
    """Request schema for updating notification preferences."""
    emailNotifications: bool = Field(..., description="Enable/disable all email notifications")
    emailDigestFrequency: Literal["instant", "daily", "weekly", "never"] = Field(..., description="Email digest frequency")
    emailWorkspaceInvites: bool = Field(..., description="Email notifications for workspace invites")
    emailComments: bool = Field(..., description="Email notifications for comments")
    emailMentions: bool = Field(..., description="Email notifications for mentions")
    emailUpdates: bool = Field(..., description="Email notifications for updates")
    inAppNotifications: bool = Field(..., description="Enable/disable all in-app notifications")
    inAppWorkspaceInvites: bool = Field(..., description="In-app notifications for workspace invites")
    inAppComments: bool = Field(..., description="In-app notifications for comments")
    inAppMentions: bool = Field(..., description="In-app notifications for mentions")
    inAppUpdates: bool = Field(..., description="In-app notifications for updates")

    class Config:
        json_schema_extra = {
            "example": {
                "emailNotifications": True,
                "emailDigestFrequency": "daily",
                "emailWorkspaceInvites": True,
                "emailComments": True,
                "emailMentions": True,
                "emailUpdates": False,
                "inAppNotifications": True,
                "inAppWorkspaceInvites": True,
                "inAppComments": True,
                "inAppMentions": True,
                "inAppUpdates": False,
            }
        }
