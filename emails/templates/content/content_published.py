"""
Content Published Email Template

Sent to workspace members when new content is published.
"""

from emails.components import primary_button, simple_footer, simple_header
from emails.utils.renderer import compose_email


def render_content_published_email(
    user_name: str,
    publisher_name: str,
    content_title: str,
    content_excerpt: str,
    content_url: str,
    workspace_name: str,
    published_at: str,
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """
    Render content published email template.

    Sent to workspace members (except publisher) when content is published.

    Args:
        user_name: Recipient's first name or display name
        publisher_name: Name of the user who published the content
        content_title: Title of the published content
        content_excerpt: First ~200 characters of content
        content_url: URL to view the content
        workspace_name: Name of the workspace
        published_at: Timestamp of publication (e.g., "Oct 12, 2025 3:45 PM")
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    email_html = compose_email(
        [
            simple_header(),
            """
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            New Content Published
        </h1>
        """,
            f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <strong>{publisher_name}</strong> published new content in <strong>{workspace_name}</strong>.
        </p>
        """,
            f"""
        <div style="margin: 32px 0; padding: 24px; background-color: #ffffff; border: 2px solid #e5e7eb; border-radius: 8px;">
            <h2 style="color: #111827; font-size: 20px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                {content_title}
            </h2>
            <p style="color: #4b5563; font-size: 14px; line-height: 22px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                {content_excerpt}...
            </p>
        </div>
        """,
            primary_button("View Content", content_url),
            f"""
        <div style="margin: 32px 0 0 0; padding: 16px; background-color: #f9fafb; border-radius: 6px;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                    <td style="color: #6b7280; font-size: 13px; padding: 4px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Published by
                    </td>
                    <td style="color: #111827; font-size: 13px; padding: 4px 0; text-align: right; font-weight: 500; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {publisher_name}
                    </td>
                </tr>
                <tr>
                    <td style="color: #6b7280; font-size: 13px; padding: 4px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Workspace
                    </td>
                    <td style="color: #111827; font-size: 13px; padding: 4px 0; text-align: right; font-weight: 500; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {workspace_name}
                    </td>
                </tr>
                <tr>
                    <td style="color: #6b7280; font-size: 13px; padding: 4px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Published
                    </td>
                    <td style="color: #111827; font-size: 13px; padding: 4px 0; text-align: right; font-weight: 500; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {published_at}
                    </td>
                </tr>
            </table>
        </div>
        """,
            simple_footer(),
        ]
    )

    return email_html
