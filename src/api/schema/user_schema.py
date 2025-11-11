from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, Literal

class RegisterUser(BaseModel):
    first_name: str = Field(..., description="First name of the user")
    last_name:  str = Field(..., description="Last name of the user")
    username:  str = Field(..., description="Name of the user")
    email: EmailStr = Field(..., description="Email address of the user")
    password: str = Field(..., min_length=8, description="Password for the user account")


class RegisterWithInvitation(BaseModel):
    """
    Schema for user registration via workspace invitation.

    This endpoint handles the complete flow of:
    1. Creating a new user account
    2. Validating the invitation token
    3. Auto-accepting the invitation
    4. Creating workspace membership

    The email is pre-filled and read-only on the frontend, but we validate
    that it matches the invitation email for security.
    """
    first_name: str = Field(..., description="First name of the user")
    last_name: str = Field(..., description="Last name of the user")
    username: str = Field(..., description="Username for the account")
    email: EmailStr = Field(..., description="Email address (must match invitation email)")
    password: str = Field(..., min_length=8, description="Password for the user account")
    invitation_token: str = Field(..., description="Invitation token from email link")


class LoginUser(BaseModel):
    email: EmailStr = Field(..., description="email of the user")
    password: str = Field(..., min_length=8, description="Password for the user account")


class UpdateUser(BaseModel):
    email: Optional[EmailStr] = Field(None, description="User email")
    username: Optional[str] = Field(None, description="Username")
    first_name: Optional[str] = Field(None, description="First name")
    last_name: Optional[str] = Field(None, description="Last name")
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

class UpdateProfileRequest(BaseModel):
    """Schema for users to update their own profile (self-service)"""
    first_name: Optional[str] = Field(None, min_length=1, max_length=100, description="First name")
    last_name: Optional[str] = Field(None, min_length=1, max_length=100, description="Last name")
    display_name: Optional[str] = Field(None, min_length=1, max_length=200, description="Display name")
    bio: Optional[str] = Field(None, max_length=500, description="User bio (max 500 characters)")
    language: Optional[str] = Field(None, min_length=2, max_length=10, description="Language preference (e.g., 'en', 'es')")
    timezone: Optional[str] = Field(None, min_length=1, max_length=50, description="Timezone (e.g., 'UTC', 'America/New_York')")

class ProfileResponse(BaseModel):
    """Schema for profile response"""
    id: str
    email: str
    username: str
    first_name: Optional[str]
    last_name: Optional[str]
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
    username: str
    email: str
    old_status: str
    new_status: str
    changed_by: str
    reason: Optional[str]
    changed_at: str

class DeactivateAccountRequest(BaseModel):
    """Schema for account deactivation request"""
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