"""
Email Verification Template

Sent when a user registers and needs to verify their email address.
"""
from typing import Optional
from emails.components import simple_header, primary_button, simple_footer
from emails.utils.renderer import compose_email


def render_verification_email(
    user_name: str,
    verification_url: str,
    frontend_url: str = "https://app.rext.ai"
) -> str:
    """
    Render email verification template.

    Args:
        user_name: User's first name or display name
        verification_url: Complete URL with verification token
        frontend_url: Base frontend URL for branding

    Returns:
        Complete HTML email string

    Example:
        >>> html = render_verification_email(
        ...     user_name="John",
        ...     verification_url="https://app.rext.ai/verify-email?token=abc123"
        ... )
    """
    email_html = compose_email([
        simple_header(),
        f"""
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Welcome to REXT, {user_name}!
        </h1>
        """,
        """
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Thanks for signing up! We're excited to have you on board.
        </p>
        """,
        """
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            To complete your registration and start using REXT, please verify your email address by clicking the button below:
        </p>
        """,
        primary_button("Verify Email Address", verification_url),
        """
        <div style="margin-top: 32px; padding: 16px; background-color: #f9fafb; border-radius: 6px; border-left: 4px solid #fbbf24;">
            <p style="color: #92400e; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>⏱️ This link will expire in 24 hours.</strong> If the link expires, you can request a new verification email from the login page.
            </p>
        </div>
        """,
        """
        <div style="margin-top: 24px; padding: 16px; background-color: #f3f4f6; border-radius: 6px;">
            <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>If the button doesn't work, copy and paste this link into your browser:</strong>
            </p>
            <p style="color: #3b82f6; font-size: 13px; line-height: 20px; margin: 0; font-family: 'Courier New', monospace; word-break: break-all;">
                {verification_url}
            </p>
        </div>
        """.format(verification_url=verification_url),
        """
        <div style="margin-top: 32px; border-top: 1px solid #e5e7eb; padding-top: 24px;">
            <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                If you didn't create an account with REXT, you can safely ignore this email.
            </p>
        </div>
        """,
        simple_footer()
    ], preview_text=f"Welcome to REXT, {user_name}! Verify your email to get started.")

    return email_html


# Convenience function for use with EmailService
def create_verification_email(
    user_name: str,
    verification_token: str,
    frontend_url: str = "https://app.rext.ai",
    unsubscribe_token: Optional[str] = None
) -> str:
    """
    Create verification email with token.

    Builds the verification URL from token and renders the email.

    Args:
        user_name: User's first name or display name
        verification_token: JWT verification token
        frontend_url: Base frontend URL
        unsubscribe_token: Optional unsubscribe token for user preferences

    Returns:
        Complete HTML email string
    """
    verification_url = f"{frontend_url}/verify-email?token={verification_token}"

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

    email_html = compose_email([
        simple_header(),
        f"""
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Welcome to REXT, {user_name}!
        </h1>
        """,
        """
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Thanks for signing up! We're excited to have you on board.
        </p>
        """,
        """
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            To complete your registration and start using REXT, please verify your email address by clicking the button below:
        </p>
        """,
        primary_button("Verify Email Address", verification_url),
        """
        <div style="margin-top: 32px; padding: 16px; background-color: #f9fafb; border-radius: 6px; border-left: 4px solid #fbbf24;">
            <p style="color: #92400e; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>⏱️ This link will expire in 24 hours.</strong> If the link expires, you can request a new verification email from the login page.
            </p>
        </div>
        """,
        f"""
        <div style="margin-top: 24px; padding: 16px; background-color: #f3f4f6; border-radius: 6px;">
            <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>If the button doesn't work, copy and paste this link into your browser:</strong>
            </p>
            <p style="color: #3b82f6; font-size: 13px; line-height: 20px; margin: 0; font-family: 'Courier New', monospace; word-break: break-all;">
                {verification_url}
            </p>
        </div>
        """,
        """
        <div style="margin-top: 32px; border-top: 1px solid #e5e7eb; padding-top: 24px;">
            <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                If you didn't create an account with REXT, you can safely ignore this email.
            </p>
        </div>
        """,
        unsubscribe_html,
        simple_footer()
    ], preview_text=f"Welcome to REXT, {user_name}! Verify your email to get started.")

    return email_html
