from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, Literal, List, Dict, Any
from datetime import datetime
from uuid import UUID

class UserResponse(BaseModel):
    """Refined user response schema with ID and metadata"""
    id: UUID = Field(..., description="User UUID")
    email: EmailStr = Field(..., description="User email")
    full_name: Optional[str] = Field(None, description="Full name")
    display_name: Optional[str] = Field(None, description="Display name")
    avatar_url: Optional[str] = Field(None, description="Profile avatar URL")
    language: str = Field("en", description="Language preference")
    timezone: str = Field("UTC", description="Timezone preference")
    status: str = Field(..., description="Account status")
    email_verified: bool = Field(..., description="Whether email is verified")
    last_login_at: Optional[datetime] = Field(None, description="Last login timestamp")
    login_count: int = Field(0, description="Total login count")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    """Schema for successful login response"""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field("bearer", description="Token type")
    expires_in: int = Field(..., description="Access token lifetime in seconds")
    user: UserResponse = Field(..., description="User profile details")
    roles: List[str] = Field(default=[], description="List of user roles")
    permissions: List[str] = Field(default=[], description="List of user permissions")

    class Config:
        from_attributes = True

class RegisterUser(BaseModel):
    full_name: str = Field(..., description="Full name of the user")
    email: EmailStr = Field(..., description="Email address of the user")
    password: str = Field(..., min_length=8, description="Password for the user account")


class RegisterWithInvitation(BaseModel):
    """
    Schema for user registration via workspace invitation.
    """
    full_name: str = Field(..., description="Full name of the user")
    email: EmailStr = Field(..., description="Email address (must match invitation email)")
    password: str = Field(..., min_length=8, description="Password for the user account")
    invitation_token: str = Field(..., description="Invitation token from email link")


class LoginUser(BaseModel):
    email: EmailStr = Field(..., description="email of the user")
    password: str = Field(..., min_length=8, description="Password for the user account")


class LoginWithInvitation(BaseModel):
    """
    Schema for user login with invitation acceptance.
    
    This endpoint handles the flow for existing users who:
    1. Already have an account (login with email/password)
    2. Have been invited to a workspace (via invitation token)
    3. Want to login and accept the invitation in one step
    
    The invitation is automatically accepted after successful authentication.
    """
    email: EmailStr = Field(..., description="Email address of the user")
    password: str = Field(..., min_length=8, description="Password for the user account")
    invitation_token: str = Field(..., description="Invitation token from email link")


class UpdateUser(BaseModel):
    email: Optional[EmailStr] = Field(None, description="User email")
    full_name: Optional[str] = Field(None, description="Full name")
    display_name: Optional[str] = Field(None, description="Display name")
    password: Optional[str] = Field(None, description="Password (will be hashed)")
    avatar_url: Optional[str] = Field(None, description="Profile avatar URL")
    language: Optional[str] = Field(None, description="User language")
    timezone: Optional[str] = Field(None, description="User timezone")


class ResetPassword(BaseModel):
    token: str
    new_password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(..., description="Email address to send password reset link")


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, description="Current password for verification")
    new_password: str = Field(..., min_length=8, description="New password (min 8 characters)")
    confirm_password: str = Field(..., min_length=8, description="Confirm new password")

    @field_validator('confirm_password')
    @classmethod
    def passwords_match(cls, v, info):
        if 'new_password' in info.data and v != info.data['new_password']:
            raise ValueError('Passwords do not match')
        return v


# NEW: For password.py
class VerifyPasswordRequest(BaseModel):
    """Schema for password verification request"""
    password: str = Field(..., min_length=1, description="User's current password to verify")


# NEW: For auth.py
class RefreshTokenRequest(BaseModel):
    """Schema for token refresh request"""
    refresh_token: str = Field(..., description="Refresh token to exchange for new access token")


class ResendVerificationRequest(BaseModel):
    """Schema for resending verification email"""
    email: EmailStr = Field(..., description="Email address to resend verification to")


class OAuthLoginRequest(BaseModel):
    """Schema for OAuth login/register request"""
    provider: str = Field(..., description="OAuth provider (google, github, etc.)")
    provider_account_id: str = Field(..., description="Provider's account ID")
    provider_email: EmailStr = Field(..., description="Email from OAuth provider")
    provider_name: str = Field(default="", description="User's name from provider")
    provider_avatar_url: Optional[str] = Field(None, description="Avatar URL from provider")
    provider_username: Optional[str] = Field(None, description="Username from provider")
    access_token: Optional[str] = Field(None, description="OAuth access token")
    refresh_token: Optional[str] = Field(None, description="OAuth refresh token")
    token_expires_at: Optional[str] = Field(None, description="Token expiration timestamp (ISO format)")


class OAuthLinkRequest(BaseModel):
    """Schema for linking OAuth account"""
    provider: str = Field(..., description="OAuth provider (google, github, etc.)")
    provider_account_id: str = Field(..., description="Provider's account ID")
    provider_email: EmailStr = Field(..., description="Email from OAuth provider")
    provider_username: Optional[str] = Field(None, description="Username from provider")
    provider_avatar_url: Optional[str] = Field(None, description="Avatar URL from provider")
    access_token: Optional[str] = Field(None, description="OAuth access token")
    refresh_token: Optional[str] = Field(None, description="OAuth refresh token")
    token_expires_at: Optional[str] = Field(None, description="Token expiration timestamp (ISO format)")


# NEW: For invitations.py
class DeclineInvitationRequest(BaseModel):
    """Schema for declining an invitation"""
    reason: Optional[str] = Field(None, description="Optional reason for declining (e.g., 'Not interested', 'Wrong email', 'Other')")


class UpdateProfileRequest(BaseModel):
    """Schema for users to update their own profile (self-service)"""
    full_name: Optional[str] = Field(None, min_length=1, max_length=200, description="Full name")
    display_name: Optional[str] = Field(None, min_length=1, max_length=200, description="Display name")
    bio: Optional[str] = Field(None, max_length=500, description="User bio (max 500 characters)")
    language: Optional[str] = Field(None, min_length=2, max_length=10, description="Language preference (e.g., 'en', 'es')")
    timezone: Optional[str] = Field(None, min_length=1, max_length=50, description="Timezone (e.g., 'UTC', 'America/New_York')")


class ProfileResponse(BaseModel):
    """Schema for profile response"""
    id: str
    email: str
    full_name: Optional[str]
    display_name: Optional[str]
    language: str
    timezone: str
    status: str
    email_verified: bool
    created_at: str
    updated_at: Optional[str]


class UserStatusRequest(BaseModel):
    """Schema for changing user status (admin only)"""
    reason: Optional[str] = Field(None, max_length=500, description="Reason for status change")


class UserStatusResponse(BaseModel):
    """Schema for user status response"""
    user_id: str
    full_name: str
    email: str
    old_status: str
    new_status: str
    changed_by: str
    reason: Optional[str]
    changed_at: str


class DeactivateAccountRequest(BaseModel):
    """Schema for account deactivation request"""
    password: str = Field(..., min_length=1, description="Current password for verification")
    reason: Optional[str] = Field(None, max_length=500, description="Reason for deactivation")
    confirm: bool = Field(..., description="User must confirm deactivation")
    cancel_subscriptions: bool = Field(False, description="Automatically cancel active subscriptions")

    @field_validator('confirm')
    @classmethod
    def must_confirm(cls, v):
        if not v:
            raise ValueError('You must confirm account deactivation')
        return v


class DeactivateAccountResponse(BaseModel):
    """Schema for account deactivation response"""
    user_id: str
    email: str
    status: str
    deactivated_at: str
    scheduled_deletion_at: str
    message: str


class DataExportRequest(BaseModel):
    """Schema for data export request"""
    include_profile: bool = Field(True, description="Include profile data")
    include_roles: bool = Field(True, description="Include role assignments")
    include_workspaces: bool = Field(True, description="Include workspace memberships")
    include_activity: bool = Field(True, description="Include activity logs")
    include_billing: bool = Field(True, description="Include subscription and billing data")
    include_usage: bool = Field(True, description="Include usage metrics and statistics")


class DataExportResponse(BaseModel):
    """Schema for data export response"""
    export_id: str
    user_id: str
    status: str
    requested_at: str
    message: str