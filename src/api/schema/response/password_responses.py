from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ResetPasswordResponse(BaseModel):
    user_id: UUID
    sessions_revoked: bool


class ChangePasswordResponse(BaseModel):
    user_id: UUID
    password_changed_at: datetime
    sessions_revoked: bool


class VerifyPasswordResponse(BaseModel):
    verified: bool
