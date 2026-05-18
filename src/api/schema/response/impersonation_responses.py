from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from uuid import UUID

class ImpersonationStartResponse(BaseModel):
    original_user_id: UUID
    impersonated_user_id: UUID
    impersonated_user_email: str
    impersonated_user_name: str
    roles: List[str]
    permissions: List[str]
    access_token: str
    refresh_token: str
    started_at: datetime
    session_id: UUID

class ImpersonationStopResponse(BaseModel):
    message: str
    admin_user_id: UUID
    impersonation_stopped_at: datetime
    access_token: str
    refresh_token: str
    roles: List[str]
    permissions: List[str]
