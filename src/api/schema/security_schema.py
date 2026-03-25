"""
Security monitoring schemas for request validation and response serialization.

This module defines Pydantic models for security-related API operations.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone


# ============================================================================
# SECURITY EVENT SCHEMAS
# ============================================================================

class SecurityEventType(str):
    """Security event types."""
    FAILED_LOGIN = "failed_login"
    SUCCESSFUL_LOGIN = "successful_login"
    ACCOUNT_LOCKED = "account_locked"
    PASSWORD_RESET = "password_reset"
    PASSWORD_CHANGED = "password_changed"
    EMAIL_VERIFIED = "email_verified"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"


class FailedLoginResponse(BaseModel):
    """Schema for failed login attempt."""
    id: str = Field(..., description="User UUID")
    email: str = Field(..., description="User email")
    full_name: str = Field(..., description="Full name")
    failed_attempts: int = Field(..., description="Number of failed attempts")
    locked_until: Optional[str] = Field(None, description="Account locked until (ISO 8601)")
    last_failed_at: Optional[str] = Field(None, description="Last failed login attempt")
    is_locked: bool = Field(..., description="Whether account is currently locked")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "email": "user@example.com",
                "full_name": "john_doe",
                "failed_attempts": 2,
                "locked_until": None,
                "last_failed_at": "2025-10-02T18:30:00Z",
                "is_locked": False
            }
        }


class LockedAccountResponse(BaseModel):
    """Schema for locked account."""
    id: str = Field(..., description="User UUID")
    email: str = Field(..., description="User email")
    full_name: str = Field(..., description="Full name")
    locked_until: str = Field(..., description="Locked until (ISO 8601)")
    failed_attempts: int = Field(..., description="Failed login attempts")
    remaining_lock_time_minutes: int = Field(..., description="Minutes until unlock")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "email": "user@example.com",
                "username": "john_doe",
                "locked_until": "2025-10-02T19:30:00Z",
                "failed_attempts": 3,
                "remaining_lock_time_minutes": 45
            }
        }


class SecurityStatsResponse(BaseModel):
    """Schema for security statistics dashboard."""
    # Grouped stats
    failed_logins: Dict[str, int] = Field(..., description="Failed login metrics")
    locked_accounts: Dict[str, int] = Field(..., description="Locked account metrics")
    password_activity: Dict[str, int] = Field(..., description="Password activity metrics")
    new_accounts: Dict[str, int] = Field(..., description="New account metrics")

    # Top offenders
    top_failed_login_ips: List[Dict[str, Any]] = Field(..., description="Top IPs with failed logins")
    top_failed_login_users: List[Dict[str, Any]] = Field(..., description="Users with most failed logins")

    # Legacy fields (optional/deprecated but kept for compatibility)
    failed_logins_last_24h: Optional[int] = None
    failed_logins_last_7d: Optional[int] = None
    failed_logins_last_30d: Optional[int] = None
    currently_locked_accounts: Optional[int] = None
    locked_accounts_last_24h: Optional[int] = None
    password_resets_last_24h: Optional[int] = None
    password_changes_last_24h: Optional[int] = None
    new_registrations_last_24h: Optional[int] = None
    email_verifications_last_24h: Optional[int] = None

    class Config:
        json_schema_extra = {
            "example": {
                "failed_logins": {
                    "last_24h": 156,
                    "in_7_days": 892,
                    "in_30_days": 3421
                },
                "locked_accounts": {
                    "currently": 5,
                    "locked_today": 12
                },
                "password_activity": {
                    "resets": 8,
                    "changes": 23,
                    "last_24_hours": 31
                },
                "new_accounts": {
                    "today": 45,
                    "verified": 38
                },
                "top_failed_login_ips": [
                    {"ip": "192.168.1.100", "count": 45},
                    {"ip": "10.0.0.50", "count": 32}
                ],
                "top_failed_login_users": [
                    {"email": "user1@example.com", "count": 8},
                    {"email": "user2@example.com", "count": 5}
                ]
            }
        }


class LoginHistoryResponse(BaseModel):
    """Schema for user login history."""
    user_id: str = Field(..., description="User UUID")
    full_name: str = Field(..., description="Full name")
    email: str = Field(..., description="User email")
    total_logins: int = Field(..., description="Total login count")
    last_login_at: Optional[str] = Field(None, description="Last successful login")
    failed_login_attempts: int = Field(..., description="Current failed attempts")
    login_history: List[Dict[str, Any]] = Field(..., description="Recent login events from audit log")

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "username": "john_doe",
                "email": "john@example.com",
                "total_logins": 245,
                "last_login_at": "2025-10-02T18:30:00Z",
                "failed_login_attempts": 0,
                "login_history": [
                    {
                        "timestamp": "2025-10-02T18:30:00Z",
                        "ip_address": "192.168.1.100",
                        "user_agent": "Mozilla/5.0...",
                        "status": "success"
                    },
                    {
                        "timestamp": "2025-10-02T10:15:00Z",
                        "ip_address": "192.168.1.100",
                        "user_agent": "Mozilla/5.0...",
                        "status": "success"
                    }
                ]
            }
        }


class SuspiciousActivityResponse(BaseModel):
    """Schema for suspicious activity detection."""
    user_id: str = Field(..., description="User UUID")
    email: str = Field(..., description="User email")
    full_name: str = Field(..., description="Full name")
    risk_score: int = Field(..., description="Risk score (0-100)")
    risk_factors: List[str] = Field(..., description="List of risk factors")
    recent_events: List[Dict[str, Any]] = Field(..., description="Recent suspicious events")

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "email": "user@example.com",
                "username": "suspicious_user",
                "risk_score": 75,
                "risk_factors": [
                    "Multiple failed login attempts",
                    "Login from new location",
                    "Rapid password resets"
                ],
                "recent_events": [
                    {
                        "type": "failed_login",
                        "timestamp": "2025-10-02T18:30:00Z",
                        "ip": "203.0.113.45"
                    }
                ]
            }
        }


# ============================================================================
# SECURITY ACTION SCHEMAS
# ============================================================================

class UnlockAccountRequest(BaseModel):
    """Schema for manually unlocking an account."""
    reason: Optional[str] = Field(None, max_length=500, description="Reason for unlocking")

    class Config:
        json_schema_extra = {
            "example": {
                "reason": "User verified their identity via support ticket"
            }
        }


class ResetFailedAttemptsRequest(BaseModel):
    """Schema for resetting failed login attempts."""
    reason: Optional[str] = Field(None, max_length=500, description="Reason for reset")

    class Config:
        json_schema_extra = {
            "example": {
                "reason": "False positive - user was testing from different devices"
            }
        }
