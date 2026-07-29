"""
Content Publish Failed Email Template

Sent when a scheduled publish exhausts its retries without reaching the site.
"""
from emails.components import simple_header, primary_button, simple_footer
from emails.utils.renderer import compose_email


def render_content_publish_failed_email(
    user_name: str,
    content_title: str,
    site_url: str,
    error_message: str,
    retry_url: str,
    frontend_url: str = "https://app.rext.ai"
) -> str:
    """
    Render the scheduled-publish-failed email template.

    Args:
        user_name: Recipient's first name or display name
        content_title: Title of the content that failed to publish
        site_url: The destination site the post was scheduled for
        error_message: User-friendly error message from the last attempt
        retry_url: URL to manually retry publishing
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    email_html = compose_email([
        simple_header(),
        f"""
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Scheduled Publish Failed
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            We tried to publish "<strong>{content_title}</strong>" to <strong>{site_url}</strong> at its scheduled time, but every attempt failed. The post has been marked as failed and will not be retried automatically again.
        </p>
        """,
        f"""
        <div style="margin: 32px 0; padding: 20px; background-color: #fef2f2; border-left: 4px solid #dc2626; border-radius: 4px;">
            <p style="color: #991b1b; font-size: 14px; font-weight: 600; margin: 0 0 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Last error:
            </p>
            <p style="color: #7f1d1d; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                {error_message}
            </p>
        </div>
        """,
        primary_button("Review & Retry", retry_url),
        f"""
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 24px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            This is usually caused by a temporary connectivity issue with your site or an expired credential. Check the connection under Integrations, then retry.
        </p>
        """,
        simple_footer()
    ])

    return email_html
