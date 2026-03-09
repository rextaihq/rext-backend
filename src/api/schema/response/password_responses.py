from pydantic import BaseModel
from datetime import datetime

class ResetPasswordResponse(BaseModel):
    user_id: str
    sessions_revoked: bool

class ChangePasswordResponse(BaseModel):
    user_id: str
    password_changed_at: datetime
    sessions_revoked: bool

class VerifyPasswordResponse(BaseModel):
    verified: bool
