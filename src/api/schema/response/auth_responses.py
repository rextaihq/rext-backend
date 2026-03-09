from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from src.api.schema.user_schema import UserResponse

class RegisterResponse(BaseModel):
    user: UserResponse

class AuthTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    user: UserResponse
    roles: List[str] = []
    permissions: List[str] = []

class VerifyEmailResponse(BaseModel):
    id: str
    message: str

class RegisterWithInvitationResponse(BaseModel):
    user: UserResponse
    invitation_accepted: bool

class UnlinkOAuthResponse(BaseModel):
    provider: str
    status: str
