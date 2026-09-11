from datetime import datetime
from typing import List
from uuid import UUID

from pydantic import BaseModel

from src.api.schema.user_schema import ProfileResponse, UserResponse


class UpdateProfileResponse(BaseModel):
    profile: UserResponse
    updated_fields: List[str]


class NotificationPreferencesResponse(BaseModel):
    id: UUID
    user_id: UUID
    in_app_notifications: bool
    email_notifications: bool
    push_notifications: bool
    ws_invite_received: bool
    ws_invite_accepted: bool
    security_alerts: bool
    marketing_emails: bool
    created_at: datetime
    updated_at: datetime


class ProfileResponseDetailed(ProfileResponse):
    """Extended profile for the authenticated user with RBAC visibility."""

    role: str
    permissions: List[str]
    two_factor_enabled: bool = False
