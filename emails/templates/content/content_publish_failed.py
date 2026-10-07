"""
Scheduled Publish Failed Email Template

Sent when a scheduled content publish fails due to a network/server error.
"""

from typing import Optional

from emails.components import primary_button, secondary_button, simple_footer, simple_header
from emails.site_links import SITE_CONTACT_URL
from emails.utils.renderer import compose_email


def render_content_publish_failed_email(
    user_name: str,
    content_title: str,
    site_url: str,
    error_message: str,
    will_retry: bool,
    attempt_number: int,
    max_retries: int,
    retry_url: str,
    reschedule_url: str,
    next_retry_at: Optional[str] = None,
    support_url: str = SITE_CONTACT_URL,
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """
    Render scheduled-publish-failed email template.

    Args:
        user_name: User's first name or display name
        content_title: Title of the content that failed to publish
        site_url: URL of the WordPress site the content was being published to
        error_message: User-friendly error message
        will_retry: True if the system will automatically retry, False if attempts are exhausted
        attempt_number: The attempt number that just failed
        max_retries: Maximum number of attempts configured
        retry_url: URL to retry publishing immediately
        reschedule_url: URL to pick a new publish time
        next_retry_at: When the automatic retry will run (only used if will_retry=True)
        support_url: URL to contact support
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    if will_retry:
        heading = "Scheduled Publish Delayed"
        intro = (
            f'We hit an issue publishing "<strong>{content_title}</strong>" to '
            f"<strong>{site_url}</strong>. This is attempt {attempt_number} of {max_retries}."
        )
        status_box = f"""
        <div style="margin: 24px 0; padding: 20px; background-color: #fffbeb; border-left: 4px solid #d97706; border-radius: 4px;">
            <p style="color: #92400e; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>Good news:</strong> We'll automatically retry at <strong>{next_retry_at}</strong>. No action is required, but you can also retry right now.
            </p>
        </div>
        """
        buttons = f"""
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin: 32px 0;">
            <tr>
                <td>
                    {primary_button("Retry Now", retry_url)}
                </td>
            </tr>
        </table>
        """
    else:
        heading = "Scheduled Publish Failed"
        intro = (
            f'We tried {max_retries} times but couldn\'t publish "<strong>{content_title}</strong>" '
            f"to <strong>{site_url}</strong>."
        )
        status_box = ""
        buttons = f"""
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin: 32px 0;">
            <tr>
                <td style="padding-right: 8px;">
                    {primary_button("Retry Now", retry_url)}
                </td>
                <td>
                    {secondary_button("Reschedule", reschedule_url)}
                </td>
            </tr>
        </table>
        """

    email_html = compose_email(
        [
            simple_header(),
            f"""
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            {heading}
        </h1>
        """,
            f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            {intro}
        </p>
        """,
            f"""
        <div style="margin: 32px 0; padding: 20px; background-color: #fef2f2; border-left: 4px solid #dc2626; border-radius: 4px;">
            <p style="color: #991b1b; font-size: 14px; font-weight: 600; margin: 0 0 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Error Details:
            </p>
            <p style="color: #7f1d1d; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                {error_message}
            </p>
        </div>
        """,
            status_box,
            buttons,
            f"""
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 24px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            If this problem persists, our <a href="{support_url}" style="color: #2563eb;">support team</a> is here to help.
        </p>
        """,
            simple_footer(),
        ]
    )

    return email_html
