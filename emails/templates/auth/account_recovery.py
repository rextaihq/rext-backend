"""
Account Recovery Template

Sent when an account is soft-deleted (by the user or an admin) so the owner can
restore it before the retention period ends and the data is purged.
"""

from typing import Optional

from emails.components import primary_button, simple_footer, simple_header
from emails.utils.renderer import compose_email

# Matches create_recovery_token()'s default expiry in
# src/api/security/token_utils.py — keep the two in step.
RECOVERY_LINK_VALID_MINUTES = 30

_P = (
    "color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 16px 0; "
    "font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, "
    "'Helvetica Neue', Arial, sans-serif;"
)
_MUTED = (
    "color: #6b7280; font-size: 14px; line-height: 20px; margin: 0; "
    "font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, "
    "'Helvetica Neue', Arial, sans-serif;"
)


def render_account_recovery_email(
    user_name: str,
    recovery_url: str,
    user_email: Optional[str] = None,
    retention_days: int = 14,
    unsubscribe_html: str = "",
) -> str:
    """
    Render the account recovery email.

    Args:
        user_name: User's first name or display name
        recovery_url: Complete URL with the recovery token
        user_email: Account's email address (optional, shown for clarity)
        retention_days: Days before the account is permanently deleted
        unsubscribe_html: Optional unsubscribe block appended before the footer

    Returns:
        Complete HTML email string
    """
    account_info = ""
    if user_email:
        account_info = (
            f'<p style="{_MUTED} margin-bottom: 16px;">Account: <strong>{user_email}</strong></p>'
        )

    return compose_email(
        [
            simple_header(),
            """
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your Account Is Scheduled for Deletion
        </h1>
        """,
            f'<p style="{_P}">Hi {user_name},</p>',
            f'<p style="{_P}">Your Rext AI account has been deactivated and is scheduled for permanent deletion. '
            f"Until then you can restore it and pick up exactly where you left off.</p>",
            account_info,
            f'<p style="{_P}">Click the button below to restore your account:</p>',
            primary_button("Restore My Account", recovery_url),
            f"""
        <div style="margin-top: 32px; padding: 16px; background-color: #fffbeb; border-radius: 6px; border-left: 4px solid #f59e0b;">
            <p style="color: #92400e; font-size: 14px; line-height: 20px; margin: 0 0 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>⏳ This link expires in {RECOVERY_LINK_VALID_MINUTES} minutes</strong>
            </p>
            <p style="color: #92400e; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                It can only be used once. If it expires, you can request a new one for up to {retention_days} days
                after deactivation — after that the account and its data are permanently deleted and cannot be recovered.
            </p>
        </div>
        """,
            f"""
        <div style="margin-top: 24px; padding: 16px; background-color: #f3f4f6; border-radius: 6px;">
            <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>If the button doesn't work, copy and paste this link into your browser:</strong>
            </p>
            <p style="color: #3b82f6; font-size: 13px; line-height: 20px; margin: 0; font-family: 'Courier New', monospace; word-break: break-all;">
                {recovery_url}
            </p>
        </div>
        """,
            f"""
        <div style="margin-top: 32px; border-top: 1px solid #e5e7eb; padding-top: 24px;">
            <p style="{_MUTED}">
                If you meant to close this account, no action is needed — it will be deleted automatically.
                If you didn't expect this, contact our support team right away.
            </p>
        </div>
        """,
            unsubscribe_html,
            simple_footer(),
        ],
        preview_text="Restore your Rext AI account before it's permanently deleted",
    )


# Convenience function for use with EmailService
def create_account_recovery_email(
    user_name: str,
    recovery_token: str,
    user_email: Optional[str] = None,
    frontend_url: str = "https://app.rext.ai",
    unsubscribe_token: Optional[str] = None,
    retention_days: int = 14,
) -> str:
    """
    Create the account recovery email with a token.

    Builds the recovery URL from the token and renders the email.

    Args:
        user_name: User's first name or display name
        recovery_token: JWT recovery token
        user_email: Account's email address (optional)
        frontend_url: Base frontend URL
        unsubscribe_token: Optional unsubscribe token for user preferences
        retention_days: Days before permanent deletion

    Returns:
        Complete HTML email string
    """
    recovery_url = f"{frontend_url}/account-recovery?token={recovery_token}"

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

    return render_account_recovery_email(
        user_name=user_name,
        recovery_url=recovery_url,
        user_email=user_email,
        retention_days=retention_days,
        unsubscribe_html=unsubscribe_html,
    )


def render_account_deactivated_email(
    user_name: str,
    login_url: str,
    retention_days: int = 14,
    unsubscribe_html: str = "",
    plan_ends_on: Optional[str] = None,
) -> str:
    """
    Render the self-deactivation confirmation email.

    Deactivation is not deletion: `deleted_at` stays NULL and the account can be
    brought back within the retention window. Reactivation is confirmed by
    email (see AuthService.login's deactivated branch), so this email points at
    the login page, which is where that emailed link is requested.

    Args:
        user_name: User's first name or display name
        login_url: URL of the login page
        retention_days: Days before the account is permanently deleted
        unsubscribe_html: Optional unsubscribe block appended before the footer
        plan_ends_on: When the cancelled plan's paid period ends, if there was a plan

    Returns:
        Complete HTML email string
    """
    return compose_email(
        [
            simple_header(),
            """
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your Account Has Been Deactivated
        </h1>
        """,
            f'<p style="{_P}">Hi {user_name},</p>',
            f'<p style="{_P}">Your Rext AI account has been deactivated, as you requested. '
            f"You have been signed out on every device.</p>",
            (
                f'<p style="{_P}">Your plan won\'t renew. It stays active until '
                f"<strong>{plan_ends_on}</strong>, the end of the period you paid for.</p>"
                if plan_ends_on
                else ""
            ),
            f'<p style="{_P}">Changed your mind? Start logging in and we will email you a link '
            f"to confirm it is you. Opening that link reactivates the account with nothing lost.</p>",
            primary_button("Reactivate My Account", login_url),
            f"""
        <div style="margin-top: 32px; padding: 16px; background-color: #fffbeb; border-radius: 6px; border-left: 4px solid #f59e0b;">
            <p style="color: #92400e; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>You have {retention_days} days.</strong> If you don't log back in before then,
                the account and all of its data are permanently deleted and cannot be recovered.
            </p>
        </div>
        """,
            f"""
        <div style="margin-top: 24px; padding: 16px; background-color: #f3f4f6; border-radius: 6px;">
            <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>If the button doesn't work, copy and paste this link into your browser:</strong>
            </p>
            <p style="color: #3b82f6; font-size: 13px; line-height: 20px; margin: 0; font-family: 'Courier New', monospace; word-break: break-all;">
                {login_url}
            </p>
        </div>
        """,
            f"""
        <div style="margin-top: 32px; border-top: 1px solid #e5e7eb; padding-top: 24px;">
            <p style="{_MUTED}">
                Didn't deactivate your account? Log in to reactivate it immediately and
                contact our support team — someone else may have access to your password.
            </p>
        </div>
        """,
            unsubscribe_html,
            simple_footer(),
        ],
        preview_text="Your Rext AI account is deactivated — log in any time to bring it back",
    )


def create_account_deactivated_email(
    user_name: str,
    frontend_url: str = "https://app.rext.ai",
    unsubscribe_token: Optional[str] = None,
    retention_days: int = 14,
    plan_ends_on: Optional[str] = None,
) -> str:
    """
    Create the self-deactivation email.

    Args:
        user_name: User's first name or display name
        frontend_url: Base frontend URL
        unsubscribe_token: Optional unsubscribe token for user preferences
        retention_days: Days before permanent deletion
        plan_ends_on: When the cancelled plan's paid period ends, if there was a plan

    Returns:
        Complete HTML email string
    """
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

    return render_account_deactivated_email(
        user_name=user_name,
        login_url=f"{frontend_url}/login",
        retention_days=retention_days,
        unsubscribe_html=unsubscribe_html,
        plan_ends_on=plan_ends_on,
    )
