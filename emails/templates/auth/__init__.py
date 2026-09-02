"""
Authentication Email Templates

Templates for user authentication flows:
- Email verification
- Password reset
- Password changed confirmation
- Welcome email
- Account recovery
"""
from .verification import render_verification_email, create_verification_email
from .password_reset import render_password_reset_email, create_password_reset_email
from .password_changed import render_password_changed_email, create_password_changed_email
from .welcome import render_welcome_email, create_welcome_email
from .account_recovery import (
    render_account_recovery_email,
    create_account_recovery_email,
    render_account_deactivated_email,
    create_account_deactivated_email,
)

__all__ = [
    # Verification
    "render_verification_email",
    "create_verification_email",
    # Password Reset
    "render_password_reset_email",
    "create_password_reset_email",
    # Password Changed
    "render_password_changed_email",
    "create_password_changed_email",
    # Welcome
    "render_welcome_email",
    "create_welcome_email",
    # Account Recovery
    "render_account_recovery_email",
    "create_account_recovery_email",
    # Account Deactivation
    "render_account_deactivated_email",
    "create_account_deactivated_email",
]
