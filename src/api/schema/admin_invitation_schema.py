"""
Admin Invitation Schemas

Pydantic schemas for request/response validation of platform admin invitations.
Separate from workspace invitation schemas for clarity and type safety.
"""
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from uuid import UUID
from src.utils.invitation_utils import MIN_EXPIRY_DAYS, MAX_EXPIRY_DAYS


class CreateAdminInvitationRequest(BaseModel):
    """
    Schema for creating a new platform admin invitation.

    Only super_admin can create admin invitations.
    """
    email: EmailStr = Field(
        ...,
        description="Email address of the person to invite as admin"
    )
    admin_role: str = Field(
        ...,
        description="Admin role to assign: super_admin, support_admin, platform_admin"
    )
    message: Optional[str] = Field(
        None,
        max_length=1000,
        description="Optional personalized message to include in invitation email"
    )
    permissions: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional: Additional permissions beyond standard role (JSONB)"
    )
    expiry_days: Optional[int] = Field(
        7,
        ge=MIN_EXPIRY_DAYS,
        le=MAX_EXPIRY_DAYS,
        description=f"Days until invitation expires ({MIN_EXPIRY_DAYS}-{MAX_EXPIRY_DAYS}, default 7)"
    )

    @field_validator('admin_role')
    @classmethod
    def validate_admin_role(cls, v: str) -> str:
        """Validate admin role is one of allowed values."""
        allowed_roles = ['super_admin', 'support_admin', 'platform_admin']
        if v not in allowed_roles:
            raise ValueError(
                f"admin_role must be one of: {', '.join(allowed_roles)}"
            )
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "newadmin@example.com",
                "admin_role": "support_admin",
                "message": "Welcome to the team! We're excited to have you as a support admin.",
                "expiry_days": 7
            }
        }
    }


class AcceptAdminInvitationRequest(BaseModel):
    """
    Schema for accepting an admin invitation.

    Public endpoint - no auth required (token validates identity).
    """
    token: str = Field(
        ...,
        description="Admin invitation token from email"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "token": "abc123def456..."
            }
        }
    }


class DeclineAdminInvitationRequest(BaseModel):
    """Schema for declining an admin invitation."""
    reason: Optional[str] = Field(
        None,
        max_length=500,
        description="Optional reason for declining"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "reason": "Thank you for the opportunity, but I'm not available at this time."
            }
        }
    }


class RevokeAdminInvitationRequest(BaseModel):
    """Schema for revoking an admin invitation (super_admin only)."""
    reason: Optional[str] = Field(
        None,
        max_length=500,
        description="Reason for revoking the invitation"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "reason": "Position filled by another candidate"
            }
        }
    }


class ResendAdminInvitationRequest(BaseModel):
    """Schema for resending an admin invitation (super_admin only)."""
    expiry_days: Optional[int] = Field(
        7,
        ge=MIN_EXPIRY_DAYS,
        le=MAX_EXPIRY_DAYS,
        description=f"Days until new invitation expires ({MIN_EXPIRY_DAYS}-{MAX_EXPIRY_DAYS}, default 7)"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "expiry_days": 7
            }
        }
    }


class AdminInvitationResponse(BaseModel):
    """
    Schema for admin invitation response.

    Returned when creating, viewing, or listing admin invitations.
    """
    id: UUID = Field(..., description="Invitation UUID")
    email: str = Field(..., description="Invitee email address")
    admin_role: str = Field(..., description="Admin role being offered")
    status: str = Field(
        ...,
        description="Invitation status: pending, accepted, revoked, expired, declined"
    )
    message: Optional[str] = Field(None, description="Personalized message from inviter")
    permissions: Optional[Dict[str, Any]] = Field(None, description="Additional permissions (JSONB)")

    # Inviter info
    invited_by_admin_id: Optional[UUID] = Field(None, description="Admin who sent invitation")
    invited_by_name: Optional[str] = Field(None, description="Name of inviter")
    invited_by_email: Optional[str] = Field(None, description="Email of inviter")

    # Timestamps
    created_at: datetime = Field(..., description="When invitation was created")
    expires_at: datetime = Field(..., description="When invitation expires")
    accepted_at: Optional[datetime] = Field(None, description="When invitation was accepted")
    declined_at: Optional[datetime] = Field(None, description="When invitation was declined")
    revoked_at: Optional[datetime] = Field(None, description="When invitation was revoked")

    # Acceptance info
    accepted_by_user_id: Optional[UUID] = Field(None, description="User who accepted invitation")
    accepted_by_name: Optional[str] = Field(None, description="Name of accepter")

    # Decline info
    declined_reason: Optional[str] = Field(None, description="Reason for declining")

    # Revoke info
    revoked_by_admin_id: Optional[UUID] = Field(None, description="Admin who revoked invitation")
    revoked_by_name: Optional[str] = Field(None, description="Name of revoker")
    revoked_reason: Optional[str] = Field(None, description="Reason for revoking")

    # Computed fields
    is_expired: bool = Field(..., description="Whether invitation has expired")
    can_be_accepted: bool = Field(..., description="Whether invitation can be accepted")
    days_until_expiry: Optional[int] = Field(None, description="Days until expiration (if pending)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "email": "newadmin@example.com",
                "admin_role": "support_admin",
                "status": "pending",
                "message": "Welcome to the team!",
                "invited_by_admin_id": "987e6543-e21b-54d3-a654-426614174111",
                "invited_by_name": "Super Admin",
                "invited_by_email": "admin@example.com",
                "created_at": "2025-10-23T10:00:00Z",
                "expires_at": "2025-10-30T10:00:00Z",
                "is_expired": False,
                "can_be_accepted": True,
                "days_until_expiry": 7
            }
        }
    }


class AdminInvitationListResponse(BaseModel):
    """Schema for list of admin invitations."""
    invitations: List[AdminInvitationResponse] = Field(
        ...,
        description="List of admin invitations"
    )
    total_count: int = Field(..., description="Total number of invitations")
    status_filter: Optional[str] = Field(None, description="Status filter applied (if any)")
    limit: int = Field(..., description="Results per page")
    offset: int = Field(..., description="Number of results skipped")

    model_config = {
        "json_schema_extra": {
            "example": {
                "invitations": [
                    {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "email": "newadmin@example.com",
                        "admin_role": "support_admin",
                        "status": "pending",
                        "created_at": "2025-10-23T10:00:00Z",
                        "expires_at": "2025-10-30T10:00:00Z",
                        "is_expired": False,
                        "can_be_accepted": True
                    }
                ],
                "total_count": 1,
                "status_filter": "pending",
                "limit": 50,
                "offset": 0
            }
        }
    }


class ValidateAdminInvitationResponse(BaseModel):
    """
    Schema for validating an admin invitation token.

    Public endpoint - used before signup/acceptance to show invitation details.
    """
    valid: bool = Field(..., description="Whether token is valid")
    invitation_id: Optional[UUID] = Field(None, description="Invitation UUID (if valid)")
    email: str = Field(..., description="Email this invitation is for")
    admin_role: str = Field(..., description="Admin role being offered")
    message: Optional[str] = Field(None, description="Personalized message from inviter")
    invited_by_name: Optional[str] = Field(None, description="Name of inviter")
    expires_at: datetime = Field(..., description="When invitation expires")
    is_expired: bool = Field(..., description="Whether invitation has expired")
    status: str = Field(..., description="Invitation status")
    error_message: Optional[str] = Field(None, description="Error message if invalid")

    model_config = {
        "json_schema_extra": {
            "example": {
                "valid": True,
                "invitation_id": "123e4567-e89b-12d3-a456-426614174000",
                "email": "newadmin@example.com",
                "admin_role": "support_admin",
                "message": "Welcome to the team!",
                "invited_by_name": "Super Admin",
                "expires_at": "2025-10-30T10:00:00Z",
                "is_expired": False,
                "status": "pending"
            }
        }
    }


class AdminInvitationStatsResponse(BaseModel):
    """Schema for admin invitation statistics (super_admin dashboard)."""
    total_invitations: int = Field(..., description="Total invitations sent")
    pending_invitations: int = Field(..., description="Currently pending invitations")
    accepted_invitations: int = Field(..., description="Accepted invitations")
    declined_invitations: int = Field(..., description="Declined invitations")
    revoked_invitations: int = Field(..., description="Revoked invitations")
    expired_invitations: int = Field(..., description="Expired invitations")
    acceptance_rate: float = Field(..., description="Percentage of invitations accepted")
    average_acceptance_time_hours: Optional[float] = Field(
        None,
        description="Average time to accept in hours"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "total_invitations": 10,
                "pending_invitations": 2,
                "accepted_invitations": 6,
                "declined_invitations": 1,
                "revoked_invitations": 0,
                "expired_invitations": 1,
                "acceptance_rate": 75.0,
                "average_acceptance_time_hours": 36.5
            }
        }
    }
