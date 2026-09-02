from typing import List, Optional

from pydantic import BaseModel

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


class OAuthAccountResponse(BaseModel):
    id: str
    provider: str
    provider_email: Optional[str] = None
    provider_username: Optional[str] = None
    provider_avatar_url: Optional[str] = None
    created_at: str


class OAuthAccountsResponse(BaseModel):
    accounts: List[OAuthAccountResponse]
    total_count: int
