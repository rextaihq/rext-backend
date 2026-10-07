"""
Password Changed Confirmation Template

Sent after a user successfully changes their password.
This is a security notification email.
"""

from typing import Optional

from emails.components import primary_button, simple_footer, simple_header
from emails.site_links import SITE_CONTACT_URL
from emails.utils.renderer import compose_email


def render_password_changed_email(
    user_name: str,
    changed_at: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """
    Render password changed confirmation email template.

    Sent after successful password change as a security notification.

    Args:
        user_name: User's first name or display name
        changed_at: Timestamp when password was changed (e.g., "Oct 15, 2025 3:45 PM UTC")
        ip_address: IP address from which the change was made (optional)
        user_agent: Browser/device info (optional)
        frontend_url: Base frontend URL for branding

    Returns:
        Complete HTML email string

    Example:
        >>> html = render_password_changed_email(
        ...     user_name="John",
        ...     changed_at="Oct 15, 2025 3:45 PM UTC",
        ...     ip_address="192.168.1.1"
        ... )
    """
    # Build security details section
    security_details = ""
    if ip_address or user_agent:
        details = []
        if changed_at:
            details.append(f"""
                <tr>
                    <td style="color: #737373; font-size: 13px; padding: 6px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Time
                    </td>
                    <td style="color: #171717; font-size: 13px; padding: 6px 0; text-align: right; font-weight: 500; font-family: 'Courier New', monospace;">
                        {changed_at}
                    </td>
                </tr>
            """)
        if ip_address:
            details.append(f"""
                <tr>
                    <td style="color: #737373; font-size: 13px; padding: 6px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        IP Address
                    </td>
                    <td style="color: #171717; font-size: 13px; padding: 6px 0; text-align: right; font-weight: 500; font-family: 'Courier New', monospace;">
                        {ip_address}
                    </td>
                </tr>
            """)
        if user_agent:
            details.append(f"""
                <tr>
                    <td style="color: #737373; font-size: 13px; padding: 6px 0; vertical-align: top; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Device
                    </td>
                    <td style="color: #171717; font-size: 13px; padding: 6px 0; text-align: right; font-weight: 500; font-family: 'Courier New', monospace; word-break: break-word;">
                        {user_agent[:80]}...
                    </td>
                </tr>
            """)

        security_details = f"""
        <div style="margin: 24px 0; padding: 20px; background-color: #f5f5f5; border-radius: 6px;">
            <p style="color: #171717; font-size: 14px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Change Details:
            </p>
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                {"".join(details)}
            </table>
        </div>
        """

    account_url = f"{frontend_url}/settings/security"
    support_url = SITE_CONTACT_URL

    email_html = compose_email(
        [
            simple_header(),
            """
        <h1 style="color: #171717; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Password Changed Successfully
        </h1>
        """,
            f"""
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            This is a confirmation that your password was successfully changed for your Rext AI account.
        </p>
        """,
            """
        <div style="margin: 32px 0; padding: 20px; background-color: #ecfdf5; border-left: 4px solid #111a17; border-radius: 4px;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                    <td style="padding-right: 16px; vertical-align: top;">
                        <div style="font-size: 24px;">✅</div>
                    </td>
                    <td>
                        <p style="color: #065f46; font-size: 15px; line-height: 22px; margin: 0 0 8px 0; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            Your account is secure
                        </p>
                        <p style="color: #065f46; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            For your security, you've been logged out of all other devices and sessions. You'll need to log in again with your new password.
                        </p>
                    </td>
                </tr>
            </table>
        </div>
        """,
            security_details,
            """
        <div style="margin: 32px 0; padding: 20px; background-color: #fef2f2; border-left: 4px solid #ef4444; border-radius: 4px;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                    <td style="padding-right: 16px; vertical-align: top;">
                        <div style="font-size: 24px;">⚠️</div>
                    </td>
                    <td>
                        <p style="color: #991b1b; font-size: 15px; line-height: 22px; margin: 0 0 8px 0; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            Didn't make this change?
                        </p>
                        <p style="color: #991b1b; font-size: 14px; line-height: 20px; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            If you did not change your password, your account may be compromised. Please secure your account immediately by resetting your password and reviewing your account activity.
                        </p>
        """,
            primary_button("Secure My Account", account_url),
            """
                    </td>
                </tr>
            </table>
        </div>
        """,
            f"""
        <div style="margin-top: 32px; border-top: 1px solid #e5e5e5; padding-top: 24px;">
            <p style="color: #404040; font-size: 15px; line-height: 22px; margin: 0 0 16px 0; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Need Help?
            </p>
            <p style="color: #737373; font-size: 14px; line-height: 20px; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                If you have any questions or concerns about your account security, please contact our support team immediately.
            </p>
            <p style="margin: 0;">
                <a href="{support_url}" style="color: #171717; text-decoration: underline; font-size: 14px; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                    Contact Support →
                </a>
            </p>
        </div>
        """,
            """
        <div style="margin-top: 32px; padding: 16px; background-color: #fffbeb; border-radius: 6px;">
            <p style="color: #92400e; font-size: 13px; line-height: 19px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>Security Tip:</strong> Never share your password with anyone, and use a unique password for your Rext AI account. Consider using a password manager to keep your credentials secure.
            </p>
        </div>
        """,
            simple_footer(),
        ],
        preview_text=f"Your password was changed on {changed_at}",
    )

    return email_html


# Convenience function for use with EmailService
def create_password_changed_email(
    user_name: str,
    changed_at: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    frontend_url: str = "https://app.rext.ai",
    unsubscribe_token: Optional[str] = None,
) -> str:
    """
    Create password changed confirmation email.

    Args:
        user_name: User's first name or display name
        changed_at: Timestamp when password was changed
        ip_address: IP address from which the change was made (optional)
        user_agent: Browser/device info (optional)
        frontend_url: Base frontend URL
        unsubscribe_token: Optional unsubscribe token for user preferences

    Returns:
        Complete HTML email string
    """
    # Build security details section
    security_details = ""
    if ip_address or user_agent:
        details = []
        if changed_at:
            details.append(f"""
                <tr>
                    <td style="color: #737373; font-size: 13px; padding: 6px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Time
                    </td>
                    <td style="color: #171717; font-size: 13px; padding: 6px 0; text-align: right; font-weight: 500; font-family: 'Courier New', monospace;">
                        {changed_at}
                    </td>
                </tr>
            """)
        if ip_address:
            details.append(f"""
                <tr>
                    <td style="color: #737373; font-size: 13px; padding: 6px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        IP Address
                    </td>
                    <td style="color: #171717; font-size: 13px; padding: 6px 0; text-align: right; font-weight: 500; font-family: 'Courier New', monospace;">
                        {ip_address}
                    </td>
                </tr>
            """)
        if user_agent:
            # Truncate user agent to 80 chars if too long
            ua_display = user_agent[:80] + "..." if len(user_agent) > 80 else user_agent
            details.append(f"""
                <tr>
                    <td style="color: #737373; font-size: 13px; padding: 6px 0; vertical-align: top; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Device
                    </td>
                    <td style="color: #171717; font-size: 13px; padding: 6px 0; text-align: right; font-weight: 500; font-family: 'Courier New', monospace; word-break: break-word;">
                        {ua_display}
                    </td>
                </tr>
            """)

        security_details = f"""
        <div style="margin: 24px 0; padding: 20px; background-color: #f5f5f5; border-radius: 6px;">
            <p style="color: #171717; font-size: 14px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Change Details:
            </p>
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                {"".join(details)}
            </table>
        </div>
        """

    account_url = f"{frontend_url}/settings/security"
    support_url = SITE_CONTACT_URL

    # Build unsubscribe footer (Note: Security emails typically should NOT be unsubscribable)
    unsubscribe_html = ""
    if unsubscribe_token:
        _unsubscribe_url = f"{frontend_url}/unsubscribe?token={unsubscribe_token}"
        unsubscribe_html = """
        <div style="margin-top: 32px; padding: 20px; text-align: center; background-color: #fafafa; border-radius: 6px;">
            <p style="margin: 0; font-size: 12px; color: #737373; line-height: 18px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Note: This is a security notification and cannot be disabled.
            </p>
        </div>
        """

    email_html = compose_email(
        [
            simple_header(),
            """
        <h1 style="color: #171717; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Password Changed Successfully
        </h1>
        """,
            f"""
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            This is a confirmation that your password was successfully changed for your Rext AI account.
        </p>
        """,
            """
        <div style="margin: 32px 0; padding: 20px; background-color: #ecfdf5; border-left: 4px solid #111a17; border-radius: 4px;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                    <td style="padding-right: 16px; vertical-align: top;">
                        <div style="font-size: 24px;">✅</div>
                    </td>
                    <td>
                        <p style="color: #065f46; font-size: 15px; line-height: 22px; margin: 0 0 8px 0; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            Your account is secure
                        </p>
                        <p style="color: #065f46; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            For your security, you've been logged out of all other devices and sessions. You'll need to log in again with your new password.
                        </p>
                    </td>
                </tr>
            </table>
        </div>
        """,
            security_details,
            """
        <div style="margin: 32px 0; padding: 20px; background-color: #fef2f2; border-left: 4px solid #ef4444; border-radius: 4px;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                    <td style="padding-right: 16px; vertical-align: top;">
                        <div style="font-size: 24px;">⚠️</div>
                    </td>
                    <td>
                        <p style="color: #991b1b; font-size: 15px; line-height: 22px; margin: 0 0 8px 0; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            Didn't make this change?
                        </p>
                        <p style="color: #991b1b; font-size: 14px; line-height: 20px; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            If you did not change your password, your account may be compromised. Please secure your account immediately by resetting your password and reviewing your account activity.
                        </p>
        """,
            primary_button("Secure My Account", account_url),
            """
                    </td>
                </tr>
            </table>
        </div>
        """,
            f"""
        <div style="margin-top: 32px; border-top: 1px solid #e5e5e5; padding-top: 24px;">
            <p style="color: #404040; font-size: 15px; line-height: 22px; margin: 0 0 16px 0; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Need Help?
            </p>
            <p style="color: #737373; font-size: 14px; line-height: 20px; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                If you have any questions or concerns about your account security, please contact our support team immediately.
            </p>
            <p style="margin: 0;">
                <a href="{support_url}" style="color: #171717; text-decoration: underline; font-size: 14px; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                    Contact Support →
                </a>
            </p>
        </div>
        """,
            """
        <div style="margin-top: 32px; padding: 16px; background-color: #fffbeb; border-radius: 6px;">
            <p style="color: #92400e; font-size: 13px; line-height: 19px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>Security Tip:</strong> Never share your password with anyone, and use a unique password for your Rext AI account. Consider using a password manager to keep your credentials secure.
            </p>
        </div>
        """,
            unsubscribe_html,
            simple_footer(),
        ],
        preview_text=f"Your password was changed on {changed_at}",
    )

    return email_html
