from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from src.api.schema.user_schema import UserResponse

class UpdateProfileResponse(BaseModel):
    profile: UserResponse
    updated_fields: List[str]

class NotificationPreferencesResponse(BaseModel):
    id: str
    user_id: str
    in_app_notifications: bool
    email_notifications: bool
    push_notifications: bool
    ws_invite_received: bool
    ws_invite_accepted: bool
    security_alerts: bool
    marketing_emails: bool
    created_at: str
    updated_at: str
