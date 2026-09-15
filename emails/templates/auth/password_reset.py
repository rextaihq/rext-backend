"""
Password Reset Template

Sent when a user requests to reset their password.
"""

from typing import Optional

from emails.components import primary_button, simple_footer, simple_header
from emails.utils.renderer import compose_email


def render_password_reset_email(
    user_name: str,
    reset_url: str,
    user_email: Optional[str] = None,
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """
    Render password reset email template.

    Args:
        user_name: User's first name or display name
        reset_url: Complete URL with reset token
        user_email: User's email (optional, for security info)
        frontend_url: Base frontend URL for branding

    Returns:
        Complete HTML email string

    Example:
        >>> html = render_password_reset_email(
        ...     user_name="John",
        ...     reset_url="https://app.rext.ai/reset-password?token=xyz789",
        ...     user_email="john@example.com"
        ... )
    """
    email_info = ""
    if user_email:
        email_info = f"""
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            This request was made for the account: <strong>{user_email}</strong>
        </p>
        """

    email_html = compose_email(
        [
            simple_header(),
            """
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Reset Your Password
        </h1>
        """,
            f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        """,
            """
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            We received a request to reset the password for your Rext AI account.
        </p>
        """,
            email_info,
            """
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Click the button below to create a new password:
        </p>
        """,
            primary_button("Reset Password", reset_url),
            """
        <div style="margin-top: 32px; padding: 16px; background-color: #fef2f2; border-radius: 6px; border-left: 4px solid #ef4444;">
            <p style="color: #991b1b; font-size: 14px; line-height: 20px; margin: 0 0 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>⚠️ Security Notice</strong>
            </p>
            <p style="color: #991b1b; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                This password reset link will expire in 1 hour. If you didn't request this, please ignore this email and your password will remain unchanged.
            </p>
        </div>
        """,
            """
        <div style="margin-top: 24px; padding: 16px; background-color: #f3f4f6; border-radius: 6px;">
            <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>If the button doesn't work, copy and paste this link into your browser:</strong>
            </p>
            <p style="color: #3b82f6; font-size: 13px; line-height: 20px; margin: 0; font-family: 'Courier New', monospace; word-break: break-all;">
                {reset_url}
            </p>
        </div>
        """.format(reset_url=reset_url),
            """
        <div style="margin-top: 32px; border-top: 1px solid #e5e7eb; padding-top: 24px;">
            <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>Did you request this password reset?</strong>
            </p>
            <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                If you didn't make this request, someone may be trying to access your account. We recommend that you change your password immediately after logging in. If you need help, please contact our support team.
            </p>
        </div>
        """,
            simple_footer(),
        ],
        preview_text="Reset your Rext AI password",
    )

    return email_html


# Convenience function for use with EmailService
def create_password_reset_email(
    user_name: str,
    reset_token: str,
    user_email: Optional[str] = None,
    frontend_url: str = "https://app.rext.ai",
    unsubscribe_token: Optional[str] = None,
) -> str:
    """
    Create password reset email with token.

    Builds the reset URL from token and renders the email.

    Args:
        user_name: User's first name or display name
        reset_token: JWT reset token
        user_email: User's email (optional)
        frontend_url: Base frontend URL
        unsubscribe_token: Optional unsubscribe token for user preferences

    Returns:
        Complete HTML email string
    """
    reset_url = f"{frontend_url}/reset-password?token={reset_token}"

    # Build unsubscribe footer
    unsubscribe_html = ""
    if unsubscribe_token:
        unsubscribe_url = f"{frontend_url}/unsubscribe?token={unsubscribe_token}"
        unsubscribe_html = f"""
        <div style="margin-top: 32px; padding: 20px; text-align: center; background-color: #f9fafb; border-radius: 6px;">
            <p style="margin: 0; font-size: 12px; color: #6b7280; line-height: 18px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Don't want to receive these emails?
                <a href="{unsubscribe_url}" style="color: #6b7280; text-decoration: underline;">Unsubscribe</a>
            </p>
        </div>
        """

    email_info = ""
    if user_email:
        email_info = f"""
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            This request was made for the account: <strong>{user_email}</strong>
        </p>
        """

    email_html = compose_email(
        [
            simple_header(),
            """
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Reset Your Password
        </h1>
        """,
            f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        """,
            """
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            We received a request to reset the password for your Rext AI account.
        </p>
        """,
            email_info,
            """
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Click the button below to create a new password:
        </p>
        """,
            primary_button("Reset Password", reset_url),
            """
        <div style="margin-top: 32px; padding: 16px; background-color: #fef2f2; border-radius: 6px; border-left: 4px solid #ef4444;">
            <p style="color: #991b1b; font-size: 14px; line-height: 20px; margin: 0 0 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>⚠️ Security Notice</strong>
            </p>
            <p style="color: #991b1b; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                This password reset link will expire in 1 hour. If you didn't request this, please ignore this email and your password will remain unchanged.
            </p>
        </div>
        """,
            f"""
        <div style="margin-top: 24px; padding: 16px; background-color: #f3f4f6; border-radius: 6px;">
            <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>If the button doesn't work, copy and paste this link into your browser:</strong>
            </p>
            <p style="color: #3b82f6; font-size: 13px; line-height: 20px; margin: 0; font-family: 'Courier New', monospace; word-break: break-all;">
                {reset_url}
            </p>
        </div>
        """,
            """
        <div style="margin-top: 32px; border-top: 1px solid #e5e7eb; padding-top: 24px;">
            <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>Did you request this password reset?</strong>
            </p>
            <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                If you didn't make this request, someone may be trying to access your account. We recommend that you change your password immediately after logging in. If you need help, please contact our support team.
            </p>
        </div>
        """,
            unsubscribe_html,
            simple_footer(),
        ],
        preview_text="Reset your Rext AI password",
    )

    return email_html
