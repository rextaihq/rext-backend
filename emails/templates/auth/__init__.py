"""
Authentication Email Templates

Templates for user authentication flows:
- Email verification
- Password reset
- Password changed confirmation
- Welcome email
- Account recovery
"""

from .account_recovery import (
    create_account_deactivated_email,
    create_account_recovery_email,
    render_account_deactivated_email,
    render_account_recovery_email,
)
from .account_recovery_review import (
    create_account_deleted_email,
    create_account_recovery_approved_email,
    create_account_recovery_received_email,
    create_account_recovery_rejected_email,
)
from .password_changed import create_password_changed_email, render_password_changed_email
from .password_reset import create_password_reset_email, render_password_reset_email
from .verification import create_verification_email, render_verification_email
from .welcome import create_welcome_email, render_welcome_email

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
    # Account Recovery Review (admin-approved workflow)
    "create_account_deleted_email",
    "create_account_recovery_received_email",
    "create_account_recovery_approved_email",
    "create_account_recovery_rejected_email",
]
