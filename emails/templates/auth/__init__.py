"""
Authentication Email Templates

Templates for user authentication flows:
- Email verification
- Password reset
- Welcome email
"""
from .verification import render_verification_email, create_verification_email
from .password_reset import render_password_reset_email, create_password_reset_email
from .welcome import render_welcome_email, create_welcome_email

__all__ = [
    # Verification
    "render_verification_email",
    "create_verification_email",
    # Password Reset
    "render_password_reset_email",
    "create_password_reset_email",
    # Welcome
    "render_welcome_email",
    "create_welcome_email",
]
