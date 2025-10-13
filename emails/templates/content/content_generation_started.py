"""
Content Generation Started Email Template

Sent when AI content generation begins (optional notification).
"""
from emails.components import simple_header, primary_button, simple_footer
from emails.utils.renderer import compose_email


def render_content_generation_started_email(
    user_name: str,
    content_title: str,
    content_type: str,
    workspace_name: str,
    content_url: str,
    frontend_url: str = "https://app.wrext.com"
) -> str:
    """
    Render content generation started email template.

    Sent when content generation begins (typically for longer generations).

    Args:
        user_name: User's first name or display name
        content_title: Title of the content being generated
        content_type: Type of content (e.g., "Blog Post", "Article")
        workspace_name: Name of the workspace
        content_url: URL to view generation progress
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    email_html = compose_email([
        simple_header(),
        f"""
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Content Generation Started
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your content generation for "<strong>{content_title}</strong>" has started. We'll notify you when it's complete.
        </p>
        """,
        f"""
        <div style="margin: 32px 0; padding: 24px; background-color: #f0f9ff; border: 2px solid #bfdbfe; border-radius: 8px;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                    <td style="color: #1e40af; font-size: 14px; padding: 4px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        <strong>Content Type:</strong> {content_type}
                    </td>
                </tr>
                <tr>
                    <td style="color: #1e40af; font-size: 14px; padding: 4px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        <strong>Workspace:</strong> {workspace_name}
                    </td>
                </tr>
                <tr>
                    <td style="color: #1e40af; font-size: 14px; padding: 8px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        <strong>Estimated Time:</strong> 2-5 minutes
                    </td>
                </tr>
            </table>
        </div>
        """,
        primary_button("View Progress", content_url),
        f"""
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 24px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            You'll receive another email when your content is ready.
        </p>
        """,
        simple_footer(frontend_url)
    ])

    return email_html
