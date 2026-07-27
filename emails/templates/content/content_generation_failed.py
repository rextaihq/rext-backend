"""
Content Generation Failed Email Template

Sent when AI content generation fails.
"""
from emails.components import simple_header, primary_button, secondary_button, simple_footer
from emails.utils.renderer import compose_email


def render_content_generation_failed_email(
    user_name: str,
    content_title: str,
    error_message: str,
    retry_url: str,
    support_url: str = "https://app.rext.ai/support",
    frontend_url: str = "https://app.rext.ai"
) -> str:
    """
    Render content generation failed email template.

    Sent when content generation encounters an error.

    Args:
        user_name: User's first name or display name
        content_title: Title of the content that failed
        error_message: User-friendly error message
        retry_url: URL to retry generation
        support_url: URL to contact support
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    email_html = compose_email([
        simple_header(),
        f"""
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Content Generation Failed
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            We encountered an issue generating your content "<strong>{content_title}</strong>".
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
        f"""
        <div style="margin: 24px 0; padding: 20px; background-color: #f0fdf4; border-left: 4px solid #22c55e; border-radius: 4px;">
            <p style="color: #166534; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>Good news:</strong> This didn't count against your API quota. You can try again at no additional cost.
            </p>
        </div>
        """,
        f"""
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin: 32px 0;">
            <tr>
                <td style="padding-right: 8px;">
                    {primary_button("Try Again", retry_url)}
                </td>
                <td>
                    {secondary_button("Contact Support", support_url)}
                </td>
            </tr>
        </table>
        """,
        f"""
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 24px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            If this problem persists, our support team is here to help.
        </p>
        """,
        simple_footer()
    ])

    return email_html
